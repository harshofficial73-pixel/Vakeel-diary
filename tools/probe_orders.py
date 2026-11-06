"""Probe the case status site: menu, case-type codes, order sheets and case details without captcha."""
import re, json, pathlib, requests
out = pathlib.Path("../selftest/orders"); out.mkdir(parents=True, exist_ok=True)
H = "https://www.allahabadhighcourt.in/apps/status_ccms/index.php/"
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile Safari/537.36"
rep = {}
idx = s.get("https://www.allahabadhighcourt.in/apps/status_ccms/", timeout=60).text
(out/"index.html").write_text(idx)
links = sorted(set(re.findall(r'index\.php/([A-Za-z0-9_-]+)', idx))); rep["menu"] = links
# find a case-number search page and its case type options
for name in links:
    if "type" in name.lower() or "number" in name.lower() or "case-status" in name.lower() or "casestatus" in name.lower():
        t = s.get(H + name, timeout=60).text; (out/f"{name}.html").write_text(t)
        opts = re.findall(r'<option[^>]*value=["\']?([^"\' >]+)["\']?[^>]*>\s*([^<]{1,60})', t)
        rep[f"options_{name}"] = opts[:400]
        rep[f"scripts_{name}"] = sorted(set(re.findall(r'index\.php/([A-Za-z0-9_-]+)', t)))
json.dump(rep, open(out/"report.json", "w"), indent=1)
# try order sheets for a few cases using any case-type code that maps to BAIL / WRIC
codes = {}
for k, v in rep.items():
    if k.startswith("options_"):
        for val, lab in v:
            codes.setdefault(lab.strip().split()[0].upper().rstrip("-"), val)
rep["codes_sample"] = dict(list(codes.items())[:80])
tests = [("BAIL", "16404", "2026"), ("WRIC", "36983", "2025"), ("WRIC", "12891", "2026"), ("CRLP", "9437", "2026")]
for ct, cn, cy in tests:
    for code in {codes.get(ct), ct} - {None}:
        r = s.post(H + "get-order-sheets", data={"ct": code, "cn": cn, "cy": cy}, headers={"X-Requested-With": "XMLHttpRequest", "Referer": H + "advocate-cases-roll-wise"}, timeout=60)
        fn = f"orders_{ct}_{code}_{cn}_{cy}.html"; (out/fn).write_text(r.text)
        rep[fn] = {"status": r.status_code, "len": len(r.text), "pdf_links": re.findall(r'href=["\']?([^"\' >]+)', r.text)[:5], "text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:400]}
# case details without captcha (expect failure without a cino)
r = s.post(H + "get_CaseDetails", data={"cino": "UPHC010000002026", "source": "1"}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
rep["case_details_probe"] = {"status": r.status_code, "text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:400]}
json.dump(rep, open(out/"report.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in rep.items() if not k.startswith("options_")}, indent=1, ensure_ascii=False)[:6000])
