"""Evening job: find the advocate's cases in upcoming Allahabad HC cause lists.

Reads settings from environment variables (GitHub secrets):
  ADVOCATE_NAMES      names as printed in the cause list, one per line or comma-separated
  VAULT_PASSPHRASE    passphrase used to encrypt the results file (the app asks for it once)
  TELEGRAM_BOT_TOKEN  optional, bot token from @BotFather
  TELEGRAM_CHAT_ID    optional, your chat id (the job prints it if you leave it empty and message the bot)

Writes data/vault.json (encrypted) which the app downloads.
"""
from __future__ import annotations
import base64, datetime as dt, hashlib, json, os, pathlib, re, sys, traceback
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import causelist as cl

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ITER = 250_000
LISTS = ["Z", "U", "S"]  # combined, additional, supplementary fresh


# ---------- encryption (matches WebCrypto in the app: PBKDF2-SHA256 -> AES-256-GCM) ----------
def _key(passphrase: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(passphrase.encode())


def seal(obj, passphrase: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(passphrase, salt)).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITER, "salt": b(salt), "iv": b(iv), "data": b(ct)}


def unseal(box: dict, passphrase: str):
    d = lambda k: base64.b64decode(box[k])
    pt = AESGCM(_key(passphrase, d("salt"))).decrypt(d("iv"), d("data"), None)
    return json.loads(pt)


# ---------- telegram ----------
def tg(token: str, method: str, **params):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=30)
    return r.json()


def fmt_date(d: str) -> str:
    x = dt.datetime.strptime(d, "%d-%m-%Y")
    return x.strftime("%a, %d %b")


def message(by_date: dict, today: dt.date) -> str:
    out = []
    for d in sorted(by_date, key=lambda s: dt.datetime.strptime(s, "%d-%m-%Y"))[:2]:
        hits = by_date[d]
        days = (dt.datetime.strptime(d, "%d-%m-%Y").date() - today).days
        label = "Tomorrow" if days == 1 else "Today" if days == 0 else fmt_date(d)
        out.append(f"<b>{label} · {fmt_date(d)}</b> — {len(hits)} case{'s' if len(hits) != 1 else ''}")
        for h in sorted(hits, key=lambda h: (len(h["court"]), h["court"], float(h["sr"]))):
            parties = h["parties"][:70]
            out.append(f"• Court {h['court']} · Item {h['sr']} · {h['case']}\n   {parties} <i>({h['side']})</i>")
        if not hits:
            out.append("No cases found in the list.")
        out.append("")
    return "\n".join(out).strip()


def main():
    names = [n.strip() for n in re.split(r"[,\n]", os.environ.get("ADVOCATE_NAMES", "")) if n.strip()]
    passphrase = os.environ.get("VAULT_PASSPHRASE", "")
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not names or len(passphrase) < 8:
        sys.exit("Set the ADVOCATE_NAMES and VAULT_PASSPHRASE (8+ characters) secrets first.")

    VAULT = pathlib.Path(os.environ.get("VAULT_PATH", "data/vault.json"))
    now = dt.datetime.now(IST)
    today = now.date()
    state = {"listings": {}, "cases": {}, "notified": {}, "runs": []}
    if VAULT.exists():
        try:
            state.update(unseal(json.loads(VAULT.read_text()), passphrase))
        except Exception:
            print("Could not open the previous vault (passphrase changed?). Starting fresh.")

    names_key = hashlib.sha1("|".join(sorted(n.upper() for n in names)).encode()).hexdigest()[:12]
    names_changed = state.get("names_key") != names_key
    state["names_key"] = names_key
    s = cl.session()
    log = {"at": now.isoformat(timespec="minutes"), "checked": [], "errors": []}
    for lt in LISTS:
        try:
            dates = cl.list_dates(s, lt)
        except Exception as e:
            log["errors"].append(f"{lt}: dates: {e}"); continue
        upcoming = [d for d in dates if dt.datetime.strptime(d, "%d-%m-%Y").date() >= today][-3:]
        # past lists never change: fetch each one once (the court keeps about 10 listing dates online)
        past = [d for d in dates if dt.datetime.strptime(d, "%d-%m-%Y").date() < today
                and (f"{d}|{lt}" not in state["listings"] or names_changed)]
        for d in upcoming + past:
            key = f"{d}|{lt}"
            try:
                pdf = cl.download_pdf(s, d, lt)
                if not pdf:
                    log["checked"].append({"date": d, "list": lt, "status": "not published"}); continue
                fp = hashlib.sha1(pdf).hexdigest()[:12]
                parsed = cl.parse_full(pdf)
                entries = parsed["entries"]
                hits = cl.match(entries, names)
                for h in hits:
                    h["list_type"] = cl.LIST_TYPES.get(lt, lt)
                my_courts = {h["court"] for h in hits}
                state["listings"][key] = {"date": d, "list": lt, "fingerprint": fp, "entries": len(entries), "hits": hits,
                                          "sections": {c: v for c, v in parsed["sections"].items() if c in my_courts}}
                log["checked"].append({"date": d, "list": lt, "entries": len(entries), "hits": len(hits)})
                print(f"{d} {lt}: {len(entries)} entries, {len(hits)} yours")
            except Exception as e:
                traceback.print_exc()
                log["errors"].append(f"{d} {lt}: {e}")

    # keep a year of listings; case history below is kept for good
    cutoff = today - dt.timedelta(days=400)
    state["listings"] = {k: v for k, v in state["listings"].items()
                         if dt.datetime.strptime(v["date"], "%d-%m-%Y").date() >= cutoff}
    for v in state["listings"].values():
        for h in v["hits"]:
            c = state["cases"].setdefault(h["case"], {"case": h["case"], "parties": h["parties"], "side": h["side"], "hearings": {}})
            c["parties"], c["side"] = h["parties"], h["side"]
            c["hearings"][h["date"]] = {"court": h["court"], "sr": h["sr"], "list": h["list"], "judges": h["judges"],
                                        "list_type": h.get("list_type", ""), "tag": h.get("tag", ""),
                                        "application": h.get("application", "")}
            for k in ("petitioner_counsel", "respondent_counsel", "application_in"):
                if h.get(k): c[k] = h[k]

    # orders: refresh cases listed in the last 30 days or upcoming on every run, everything else weekly
    import time
    fetched = 0
    for c in state["cases"].values():
        target = c["case"] if cl.split_case(c["case"]) else c.get("application_in", "")
        if not target or fetched >= 250:
            continue
        last = max((dt.datetime.strptime(d, "%d-%m-%Y").date() for d in c["hearings"]), default=today)
        active = (today - last).days <= 30
        checked = c.get("orders_checked", "")
        stale = not checked or (dt.date.fromisoformat(checked[:10]) < today - dt.timedelta(days=7))
        if not (active and checked[:10] != today.isoformat() or stale):
            continue
        try:
            o = cl.fetch_orders(s, target)
            fetched += 1
            if o is not None:
                new = {x["date"] for x in o["orders"]} - {x["date"] for x in c.get("orders", [])}
                if c.get("orders_checked") and new:
                    c["new_orders"] = sorted(new, key=lambda d: dt.datetime.strptime(d, "%d-%m-%Y"))
                c["orders"], c["order_sheet"] = o["orders"], o["sheet"]
                c["orders_for"] = target
            c["orders_checked"] = now.isoformat(timespec="minutes")
            time.sleep(0.3)
        except Exception as e:
            log["errors"].append(f"orders {target}: {e}")
    log["orders_fetched"] = fetched
    print(f"Orders refreshed for {fetched} cases")

    # telegram: tomorrow and the next listing date after it
    by_date: dict[str, list] = {}
    for v in state["listings"].values():
        if dt.datetime.strptime(v["date"], "%d-%m-%Y").date() > today:
            by_date.setdefault(v["date"], [])
            have = {(h["court"], h["sr"], h["case"]) for h in by_date[v["date"]]}
            by_date[v["date"]] += [h for h in v["hits"] if (h["court"], h["sr"], h["case"]) not in have]
    if token:
        if not chat:
            ups = tg(token, "getUpdates").get("result", [])
            ids = {u["message"]["chat"]["id"] for u in ups if "message" in u}
            print("TELEGRAM_CHAT_ID not set. Chats that messaged the bot:", ids or "none — send /start to your bot first")
        elif by_date:
            text = message(by_date, today)
            fresh = [c for c in state["cases"].values() if c.get("new_orders")]
            if fresh:
                text += "\n\n<b>New orders uploaded</b>\n" + "\n".join(
                    f"• {c['case']} — order of {', '.join(c['new_orders'])}" for c in fresh[:15])
            digest = hashlib.sha1(text.encode()).hexdigest()
            evening = now.hour >= 18
            first_today = state["notified"].get("day") != today.isoformat() and evening
            if digest != state["notified"].get("digest") or first_today:
                r = tg(token, "sendMessage", chat_id=chat, text="⚖️ <b>Vakeel Diary</b>\n\n" + text, parse_mode="HTML",
                       disable_web_page_preview=True)
                print("Telegram:", "sent" if r.get("ok") else r)
                if r.get("ok"):
                    for c in fresh:
                        c.pop("new_orders", None)
                    state["notified"] = {"digest": digest, "day": today.isoformat() if evening else state["notified"].get("day")}

    state["runs"] = ([log] + state.get("runs", []))[:20]
    state["updated"] = now.isoformat(timespec="minutes")
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    VAULT.write_text(json.dumps(seal(state, passphrase)))
    print("Saved", VAULT)


if __name__ == "__main__":
    main()
