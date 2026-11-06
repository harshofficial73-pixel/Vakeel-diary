"""Allahabad High Court cause list: download and parse the combined cause list PDF.

The court publishes the combined cause list (criteria "Court Wise", "Entire List") as one
PDF per listing date. No captcha is involved. Each entry has a serial number, case number,
parties and both sides' counsel, laid out in fixed columns.
"""
from __future__ import annotations
import re, io
import requests
import pymupdf

BASE = "https://www.allahabadhighcourt.in/causelist/"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36 VakeelDiary"
CASE_RE = re.compile(r"^([A-Z][A-Z0-9.\-()]*/)?\d+/\d{4}$")
SR_RE = re.compile(r"^\d+(\.\d+)?$")
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

LIST_TYPES = {"Z": "Combined Cause List", "U": "Additional Cause List", "S": "Supplementary Fresh Cases"}


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.get(BASE + "indexA.html", timeout=60)
    return s


def list_dates(s: requests.Session, list_type: str = "Z") -> list[str]:
    """Listing dates the court currently offers for this list type, newest first (dd-mm-yyyy)."""
    r = s.post(BASE + "input1A.jsp", data={"listType": list_type}, timeout=60)
    return re.findall(r"<option value=([\d-]+)", r.text)


def download_pdf(s: requests.Session, date: str, list_type: str = "Z", court: str = "-99") -> bytes | None:
    """Download the PDF for one listing date (court -99 = entire list). None if not published."""
    s.post(BASE + "input2A.jsp", data={"criteria": "court", "listType": list_type, "listDate": date}, timeout=60)
    r = s.post(BASE + "viewlistA.jsp",
               data={"courtNo": court, "location": "A", "listType": list_type, "listDate": date}, timeout=180)
    m = re.search(r'["\'](https?://[^"\']+\.pdf)["\']', r.text, re.I)
    if not m:
        return None
    pdf = s.get(m.group(1), timeout=600)
    if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
        return None
    return pdf.content


def _lines(page):
    """Group a page's words into lines: list of (y, [(x0, x1, text), ...])."""
    words = sorted(page.get_text("words"), key=lambda w: (round(w[1]), w[0]))
    lines: list[list] = []
    for x0, y0, x1, y1, t, *_ in words:
        if lines and abs(lines[-1][0] - y0) < 3:
            lines[-1][1].append((x0, x1, t))
        else:
            lines.append([y0, [(x0, x1, t)]])
    for ln in lines:
        ln[1].sort()
    return lines


def _text(ws):
    return " ".join(t for _, _, t in ws)


def parse(pdf_bytes: bytes) -> list[dict]:
    return parse_full(pdf_bytes)["entries"]


def parse_full(pdf_bytes: bytes) -> dict:
    """Entries plus, for every court, its sections with serial ranges and counts."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    entries: list[dict] = []
    cols = {"party": 230.0, "pet": 360.0, "resp": 470.0}
    court, judges, section, list_date, cur = "", [], "", "", None
    pending_judges: list[str] = []

    def close():
        nonlocal cur
        if cur:
            for k in ("parties", "detail"):
                cur[k] = re.sub(r"\s+", " ", " ".join(cur.pop("_" + k))).strip()
            for k in ("petitioner_counsel", "respondent_counsel"):
                cur[k] = ", ".join(x.strip() for x in cur.pop("_" + k) if x.strip())
            cur["parties"] = re.sub(r" VS ", " vs ", cur["parties"], flags=re.I)
            m = re.search(r"in case ([A-Z][A-Z0-9.()]*-\d+-\d{4})", cur["detail"])
            if m and cur["case"][0].isdigit():
                # an application listed in a main case: file it under the main case
                cur["application"] = cur["case"]
                cur["case"] = m.group(1).replace("-", "/")
                cur["application_in"] = cur["case"]
            if cur["tag"].startswith("With"):
                cur["connected_with"] = cur["sr"].split(".")[0]
            entries.append(cur)
        cur = None

    for page in doc:
        h = page.rect.height
        for y, ws in _lines(page):
            txt = _text(ws)
            # running footer / header carry date and court number
            m = re.search(r"Court No-\s*([A-Z0-9]+)", txt)
            if m and ("Page" in txt or len(ws) <= 4):
                if m.group(1) != court:
                    close()
                    court = m.group(1)
                    if pending_judges:
                        judges, pending_judges = pending_judges, []
                if DATE_RE.match(ws[0][2]):
                    list_date = ws[0][2]
                continue
            if "Page" in txt and " of " in txt:
                continue
            if txt.startswith(("HON", "HON’BLE", "HON'BLE")) and "JUSTICE" in txt:
                j = txt.replace("’", "'")
                if j in judges:   # repeated at the top of every page: the entry continues
                    continue
                close()
                if j not in pending_judges:
                    pending_judges.append(j)
                judges = pending_judges[:]  # same court continues if footer doesn't change
                continue
            if re.match(r"^\d{2}-\d{2}-\d{4} At", txt):
                list_date = txt[:10]
                pending_judges = []
                continue
            if ws[0][2] == "Sr.No.":
                for x0, _, t in ws:
                    if t == "Party": cols["party"] = x0 - 6
                    elif t.startswith("Petitioner"): cols["pet"] = x0 - 6
                    elif t.startswith("Respondent"): cols["resp"] = x0 - 6
                continue
            if "(From Sr.No." in txt:
                close()
                section = re.sub(r"\s*\(From Sr\.No\..*", "", txt).strip()
                continue
            mid = (ws[0][0] + ws[-1][1]) / 2
            starts_on_col = any(abs(ws[0][0] - (v + 6)) < 4 for v in cols.values())
            if (ws[0][0] > 150 and abs(mid - page.rect.width / 2) < 40 and not starts_on_col
                    and not txt.upper().startswith("VS") and re.fullmatch(r"[A-Z0-9 ,/&()\-.:']{3,80}", txt)):
                close()
                section = section.split(" — ")[0] + " — " + txt if section else txt
                continue
            if txt.startswith("-Details of Cases filed earlier"):
                close()
                continue
            # entry start: serial number then case number
            ci = next((i for i, w in enumerate(ws[:4]) if 90 < w[0] < 200 and CASE_RE.match(w[2].rstrip(","))), None)
            if ci and SR_RE.match(ws[0][2]) and ws[0][0] < 100:
                close()
                cur = {"date": list_date, "court": court, "judges": judges[:], "list": section,
                       "sr": ws[0][2], "case": ws[ci][2].rstrip(","), "tag": " ".join(w[2] for w in ws[1:ci]),
                       "_parties": [], "_petitioner_counsel": [], "_respondent_counsel": [], "_detail": []}
                ws = ws[ci + 1:]
            if cur is None:
                continue
            first = ws[0][2] if ws else ""
            is_note = ws and ws[0][0] < 100 and (first.startswith(("Crime", "-Details", "....", "District", "FIR", "Police"))
                                                  or "Title-" in txt or CASE_RE.match(first.rstrip(",")))
            if is_note:  # full-width note lines (Crime No, earlier cases) belong to detail only
                cur["_detail"].append(_text(ws))
                continue
            line = {"party": [], "pet": [], "resp": []}
            for x0, _, t in ws:
                if x0 >= cols["resp"]: line["resp"].append(t)
                elif x0 >= cols["pet"]: line["pet"].append(t)
                elif x0 >= cols["party"]: line["party"].append(t)
                else: cur["_detail"].append(t)
            cur["_parties"] += line["party"]
            if line["pet"]: cur["_petitioner_counsel"].append(" ".join(line["pet"]))
            if line["resp"]: cur["_respondent_counsel"].append(" ".join(line["resp"]))

    close()
    return {"entries": entries, "sections": summarize(entries)}


def summarize(entries: list[dict]) -> dict:
    """Per court, each main section (Fresh list, Daily cause list, Fresh misc. application) with its
    serial range and number of matters, worked out from the entries (connected .1/.2 items not counted)."""
    out: dict[str, dict] = {}
    for e in entries:
        top = e["list"].split(" — ")[0] or "LIST"
        d = out.setdefault(e["court"], {}).setdefault(top, {"section": top, "first": None, "last": None, "count": 0})
        if "." in e["sr"]:
            continue
        n = int(e["sr"])
        d["count"] += 1
        d["first"] = n if d["first"] is None else min(d["first"], n)
        d["last"] = n if d["last"] is None else max(d["last"], n)
    return {c: sorted(v.values(), key=lambda x: x["first"] or 0) for c, v in out.items()}


def norm(s: str) -> str:
    return " " + re.sub(r"[^A-Z0-9]+", " ", s.upper()).strip() + " "


def match(entries: list[dict], names: list[str]) -> list[dict]:
    """Entries where any of the names appears in either counsel column."""
    keys = [norm(n) for n in names if len(n.strip()) >= 4]
    hits, seen = [], set()
    for e in entries:
        k = (e["date"], e["court"], e["sr"], e["case"])
        if k in seen:
            continue
        for side, field in (("petitioner", "petitioner_counsel"), ("respondent", "respondent_counsel")):
            if any(k in norm(e[field]) for k in keys):
                hits.append({**e, "side": side})
                seen.add(k)
                break
    return hits


if __name__ == "__main__":
    import sys, json, time
    t = time.time()
    es = parse(open(sys.argv[1], "rb").read())
    print(f"{len(es)} entries in {time.time()-t:.1f}s", file=sys.stderr)
    if len(sys.argv) > 2:
        es = match(es, sys.argv[2:])
    print(json.dumps(es[:5] if len(sys.argv) <= 2 else es, indent=1, ensure_ascii=False))


# ---------- orders (High Court case status site, no captcha) ----------
ORDERS_URL = "https://www.allahabadhighcourt.in/apps/status_ccms/index.php/get-order-sheets"


def split_case(case: str):
    m = re.match(r"^([A-Z][A-Z0-9.\-()]*)/(\d+)/(\d{4})$", case.strip().upper())
    return (m.group(1), m.group(2), m.group(3)) if m else None


def parse_orders(html: str) -> dict:
    sheet = re.search(r"href='([^']*WebDownloadOrderSheet[^']*)'", html)
    orders = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 3:
            continue
        date = re.sub(r"<[^>]+>|\s", "", tds[1])
        link = re.search(r"href='([^']*WebDownloadJudgmentDocument[^']*)'", tds[2])
        if DATE_RE.match(date):
            orders.append({"date": date, "url": link.group(1) if link else ""})
    return {"sheet": sheet.group(1).replace("&amp;", "&") if sheet else "", "orders": orders}


def fetch_orders(s: requests.Session, case: str) -> dict | None:
    parts = split_case(case)
    if not parts:
        return None
    r = s.post(ORDERS_URL, data=dict(zip(("ct", "cn", "cy"), parts)),
               headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
    r.raise_for_status()
    return parse_orders(r.text)
