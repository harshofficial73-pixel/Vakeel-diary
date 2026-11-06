"""How does elegalix serve order PDFs? Record what a plain request gets back (no captcha solving)."""
import json, re, requests
U = "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile Safari/537.36"
links = {
  "judgment": "https://elegalix.allahabadhighcourt.in/elegalix/WebDownloadJudgmentDocument.do?judgmentID=13741695",
  "order_sheet": "https://elegalix.allahabadhighcourt.in/elegalix/WebDownloadOrderSheet.do?h=A&t=BAIL&n=16404&y=2026&m=C",
}
rep = {}
for name, url in links.items():
    for mode in ("plain", "referer"):
        h = {"User-Agent": U}
        if mode == "referer": h["Referer"] = "https://www.allahabadhighcourt.in/apps/status_ccms/index.php/case-number"
        r = requests.get(url, headers=h, timeout=60, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        txt = "" if r.content[:4] == b"%PDF" else re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:500]
        rep[f"{name}_{mode}"] = {"status": r.status_code, "final_url": r.url, "type": ct, "bytes": len(r.content),
                                 "is_pdf": r.content[:4] == b"%PDF", "captcha_in_page": "captcha" in r.text.lower() if not txt == "" else False, "text": txt}
print(json.dumps(rep, indent=1))
open("../selftest/pdf.json", "w").write(json.dumps(rep, indent=1))
