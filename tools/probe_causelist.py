"""Step through the combined cause list's roll-no / counsel / court options and save each page."""
import re, pathlib, requests
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14) Chrome/124 Mobile Safari/537.36"
B = "https://www.allahabadhighcourt.in/causelist/"
log = open(out/"summary.txt","a")
def save(n, r):
    (out/n).write_bytes(r.content); l=f"{n} {r.status_code} {len(r.content)} {r.url}"; print(l); log.write(l+"\n")
s.get(B+"indexA.html")
r = s.post(B+"input1A.jsp", data={"listType":"Z"})
date = re.search(r'<option value=([\d-]+) selected', r.text).group(1)
for crit in ["rollno","counsel","court"]:
    r = s.post(B+"input2A.jsp", data={"criteria":crit,"listType":"Z","listDate":date}); save(f"step2_{crit}.html", r)
    forms = re.findall(r'<form.*?</form>', r.text, re.I|re.S)
    imgs = re.findall(r'<img[^>]+>', r.text, re.I)
    scripts = re.findall(r'<script(?![^>]*src).*?</script>', r.text, re.I|re.S)
    (out/f"step2_{crit}_forms.txt").write_text("\n\n".join(forms)+"\n\nIMGS\n"+"\n".join(imgs)+"\n\nSCRIPTS\n"+"\n\n".join(scripts))
# court-wise: pick the first court option and submit, to see what an actual list page looks like
r = s.post(B+"input2A.jsp", data={"criteria":"court","listType":"Z","listDate":date})
f = re.search(r'<form[^>]*action=["\']?([^"\' >]+).*?</form>', r.text, re.I|re.S)
if f:
    data = {m.group(1): (m.group(2) or "") for m in re.finditer(r'<input[^>]*name=["\']?([^"\' >]+)[^>]*?value=["\']?([^"\'>]*)', f.group(0), re.I)}
    for m in re.finditer(r'<select[^>]*name=["\']?([^"\' >]+).*?</select>', f.group(0), re.I|re.S):
        opts = re.findall(r'<option[^>]*value=["\']?([^"\' >]+)', m.group(0), re.I)
        if opts: data[m.group(1)] = opts[min(1,len(opts)-1)]
    log.write(f"COURT FORM {f.group(1)} {data}\n")
    save("step3_court.html", s.post(requests.compat.urljoin(r.url, f.group(1)), data=data, timeout=90))
