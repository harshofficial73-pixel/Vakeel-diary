"""Fetch the court-wise combined cause list (entire list and one court) and save it."""
import re, pathlib, requests
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile Safari/537.36"
B = "https://www.allahabadhighcourt.in/causelist/"
log = open(out/"summary.txt","a")
def save(n, r):
    (out/n).write_bytes(r.content); l=f"{n} {r.status_code} {len(r.content)} {r.headers.get('content-type','')} {r.url}"; print(l); log.write(l+"\n")
s.get(B+"indexA.html")
r = s.post(B+"input1A.jsp", data={"listType":"Z"})
date = re.search(r'<option value=([\d-]+) selected', r.text).group(1)
s.post(B+"input2A.jsp", data={"criteria":"court","listType":"Z","listDate":date})
for court in ["-99", "64"]:
    r = s.post(B+"viewlistA.jsp", data={"courtNo":court,"location":"A","listType":"Z","listDate":date}, timeout=180)
    save(f"list_{court}.html", r)
    links = sorted(set(re.findall(r'(?:href|src|action)\s*=\s*["\']?([^"\' >]+)', r.text, re.I)))
    (out/f"list_{court}_links.txt").write_text("\n".join(links))
    for i,l in enumerate([l for l in links if l.lower().endswith(".pdf") or "pdf" in l.lower()][:2]):
        save(f"list_{court}_doc{i}.pdf", s.get(requests.compat.urljoin(r.url,l), timeout=180))
