# Vakeel Diary

A free MyMunshi-style app for Allahabad High Court advocates.

- **Evening alert:** every day at 7 pm, 9:30 pm and 7 am (IST), GitHub downloads the High Court's published cause lists (combined, additional, supplementary), finds every case where your name appears as counsel, and sends you a Telegram message with the court, item number, case and parties for tomorrow and the next listing date.
- **App:** Listings (tomorrow / day after, with "court is on item X, yours is Y" on the day), the live **display board**, and every case of yours seen in a cause list.
- **All my cases:** pulls your cases from the court's "Advocate's Cases – Roll No wise" page. The court shows a captcha, and you type it in the app.

Your names, passphrase and Telegram details live in GitHub **secrets**. Results are saved encrypted (`data` branch), so nobody browsing this public repo can read your cases.

App: https://harshofficial73-pixel.github.io/Vakeel-diary/

## One-time setup

1. **Turn on the app page.** Repo → Settings → Pages → Source "Deploy from a branch" → Branch `main`, folder `/ (root)` → Save.
2. **Add secrets.** Repo → Settings → Secrets and variables → Actions → New repository secret:
   - `ADVOCATE_NAMES`: your name exactly as the cause list prints it, in capitals. Put variants on separate lines.
   - `VAULT_PASSPHRASE`: any passphrase of at least 8 characters. The app asks for it once on each device.
3. **Telegram (optional but recommended).**
   - In Telegram, open **@BotFather** → `/newbot` → pick a name. Copy the token into the secret `TELEGRAM_BOT_TOKEN`.
   - Open your new bot and press **Start**.
   - Open **@userinfobot** and copy the number it shows as your Id into the secret `TELEGRAM_CHAT_ID`.
4. **Display board relay (Cloudflare, free).** dash.cloudflare.com → sign up → Workers & Pages → Create → Create Worker → Deploy. Then click **Edit code**, replace everything with the contents of `worker/worker.js`, and click **Deploy**. Copy the worker's address (`https://….workers.dev`) into the app under My cases → Settings.
5. **First run.** Repo → Actions → "Check cause list" → Run workflow. After about 3 minutes, open the app and unlock it with your passphrase.

## How it works

| Piece | Where it runs | What it does |
|---|---|---|
| `tools/causelist.py` | GitHub Actions | Downloads the combined cause list PDF (no captcha) and parses each entry: court, judges, item, case, parties, counsel |
| `tools/run.py` | GitHub Actions, on a schedule | Matches your names, keeps 60 days of listings and a case history, encrypts it to `data/vault.json`, sends Telegram |
| `worker/worker.js` | Cloudflare Worker | Live Court View board as JSON; relays the roll-no case search, with the captcha typed by you |
| `index.html` | GitHub Pages | The app. Add it to your home screen from Safari or Chrome |

Matching is by counsel name, because the cause list prints names, not roll numbers. If the court prints your name differently in some lists, add that spelling to `ADVOCATE_NAMES`.
