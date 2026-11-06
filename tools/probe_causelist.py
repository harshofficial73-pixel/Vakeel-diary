"""Follow the Allahabad HC cause list pages a few steps and save what comes back."""
import re, sys, pathlib, urllib.parse, requests
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile Safari/537.36"
BASE = "https://www.allahabadhighcourt.in/causelist/"
log = open(out/"summary.txt","a")
def save(name, r):
    (out/name).write_bytes(r.content)
    line = f"{name} {r.status_code} {len(r.content)} {r.headers.get('content-type','')} {r.url}"
    print(line); log.write(line+"\n")
r = s.get(BASE+"indexA.html"); 
for lt in ["Z","F","U"]:
    r = s.post(BASE+"input1A.jsp", data={"listType": lt}); save(f"cl_{lt}_1.html", r)
    if lt != "Z": continue
    html = r.text
    links = re.findall(r'(?:href|action)\s*=\s*["\']([^"\'#]+)', html, re.I)
    onclick = re.findall(r"location\.href\s*=\s*['\"]([^'\"]+)", html)
    forms = re.findall(r'<form.*?</form>', html, re.I|re.S)
    (out/"cl_Z_links.txt").write_text("\n".join(links+onclick) + "\n\nFORMS:\n" + "\n\n".join(forms))
    seen = 0
    for l in links + onclick:
        u = urllib.parse.urljoin(r.url, l)
        if "allahabadhighcourt.in" not in u or u.endswith((".css",".js",".gif",".png",".jpg",".ico")): continue
        seen += 1
        if seen > 6: break
        try: save(f"cl_Z_2_{seen}" + (".pdf" if u.lower().endswith(".pdf") else ".html"), s.get(u, timeout=60))
        except Exception as e: log.write(f"ERR {u} {e}\n")
    # submit the first form on the page with its first option for each select
    for i, f in enumerate(forms[:2]):
        act = re.search(r'action\s*=\s*["\']?([^"\' >]+)', f, re.I)
        data = {}
        for m in re.finditer(r'<input[^>]*name=["\']?([^"\' >]+)[^>]*?(?:value=["\']?([^"\'>]*))?', f, re.I): data[m.group(1)] = m.group(2) or ""
        for m in re.finditer(r'<select[^>]*name=["\']?([^"\' >]+).*?</select>', f, re.I|re.S):
            opts = re.findall(r'<option[^>]*value=["\']?([^"\' >]+)', m.group(0), re.I)
            if opts: data[m.group(1)] = opts[0]
        u = urllib.parse.urljoin(r.url, act.group(1)) if act else r.url
        log.write(f"FORM{i} POST {u} {data}\n")
        try: save(f"cl_Z_form{i}.html", s.post(u, data=data, timeout=60))
        except Exception as e: log.write(f"ERR form {e}\n")
