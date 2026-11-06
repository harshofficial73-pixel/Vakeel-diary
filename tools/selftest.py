"""Self-test against the live court site: download the next list, parse it, report counts. No secrets needed."""
import json, time, causelist as cl
t = time.time(); s = cl.session(); dates = cl.list_dates(s, "Z")
rep = {"dates": dates[:4]}
pdf = cl.download_pdf(s, dates[0], "Z")
rep["pdf_mb"] = round(len(pdf) / 1e6, 1) if pdf else None
es = cl.parse(pdf) if pdf else []
rep["entries"] = len(es); rep["courts"] = len({e["court"] for e in es})
rep["sample"] = es[:2]; rep["seconds"] = round(time.time() - t)
rep["orders_sample"] = {e["case"]: cl.fetch_orders(s, e["case"]) for e in es[:3]}
rep["applications"] = [{k: e[k] for k in ("case", "application", "sr", "court")} for e in es if e.get("application")][:3]
for lt in ["U", "S"]:
    try: rep[f"dates_{lt}"] = cl.list_dates(s, lt)[:3]
    except Exception as e: rep[f"dates_{lt}"] = str(e)
print(json.dumps(rep, indent=1, ensure_ascii=False))
open("../selftest/causelist.json", "w").write(json.dumps(rep, indent=1, ensure_ascii=False))
