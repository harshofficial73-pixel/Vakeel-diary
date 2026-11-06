// Vakeel Diary relay (Cloudflare Worker, free plan).
// The court sites don't allow browsers on other sites to read them directly, so the app asks this
// relay instead. It does two things:
//   GET  /board        live Court View display board for Allahabad, as JSON (cached 20 s)
//   GET  /roll/start   opens the court's "Advocate's Cases – Roll No wise" page and returns its captcha
//   POST /roll/search  submits roll number + year + the captcha *you typed* and returns your cases
//   POST /roll/case    full details of one case from that search (same court session)
//   GET  /orders?case=BAIL/16404/2026   order dates and PDF links (court's order-sheet page, no captcha)
// Nothing is stored here.

const HC = "https://www.allahabadhighcourt.in/apps/status_ccms/index.php/";
const BOARD = "https://courtview2.allahabadhighcourt.in/courtview/CourtViewAllahabad.do";
// Only your app may use this relay. Add more origins (comma-separated) in the Worker's ALLOWED_ORIGINS variable.
const DEFAULT_ORIGINS = "https://harshofficial73-pixel.github.io";
const UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36 VakeelDiary";

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || DEFAULT_ORIGINS).split(",").map(s => s.trim()).filter(Boolean);
    const okOrigin = !allowed.length || allowed.includes(origin);
    const cors = {
      "Access-Control-Allow-Origin": okOrigin ? (origin || "*") : allowed[0],
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (url.pathname === "/") return json({ ok: true, message: "Vakeel Diary relay is running. Paste this address into the app under My cases → Settings." }, 200, cors);
    if (!okOrigin) return json({ error: "This relay only answers your Vakeel Diary app." }, 403, cors);
    try {
      if (url.pathname === "/board") return await board(req, ctx, cors);
      if (url.pathname === "/roll/start") return await rollStart(cors);
      if (url.pathname === "/roll/search" && req.method === "POST") return await rollSearch(await req.json(), cors);
      if (url.pathname === "/roll/case" && req.method === "POST") return await rollCase(await req.json(), cors);
      if (url.pathname === "/orders") return await orders(url.searchParams.get("case") || "", cors);
      if (url.pathname === "/") return json({ ok: true, app: "Vakeel Diary relay" }, 200, cors);
      return json({ error: "Not found" }, 404, cors);
    } catch (e) {
      return json({ error: "The court site didn't respond. Try again in a minute.", detail: String(e) }, 502, cors);
    }
  },
};

function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...headers } });
}

// ---------- display board ----------
async function board(req, ctx, cors) {
  const cache = caches.default;
  const key = new Request(BOARD + "#json");
  let hit = await cache.match(key);
  if (!hit) {
    const r = await fetch(BOARD, { headers: { "User-Agent": UA } });
    const html = await r.text();
    hit = json({ fetched_at: new Date().toISOString(), courts: parseBoard(html) }, 200, { "Cache-Control": "max-age=20" });
    ctx.waitUntil(cache.put(key, hit.clone()));
  }
  const res = new Response(hit.body, hit);
  for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
  return res;
}

const strip = s => s.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ")
  .replace(/&amp;/g, "&").replace(/&#39;|&rsquo;/g, "'").replace(/[ \t]+/g, " ").replace(/\n\s+/g, "\n").trim();

export function parseBoard(html) {
  const out = [];
  const rows = html.split(/<tr[\s>]/i).slice(1);
  for (const row of rows) {
    const cells = [...row.matchAll(/<td([^>]*)>([\s\S]*?)<\/td>/gi)].map(m => ({ attrs: m[1], text: strip(m[2]) }));
    if (cells.length < 2 || !/#0181c5/i.test(cells[0].attrs) || /class="head"/.test(cells[0].attrs)) continue;
    const court = cells[0].text;
    if (/colspan/i.test(cells[1].attrs)) {
      out.push({ court, in_session: false, note: cells[1].text, info: cells[2]?.text || "" });
      continue;
    }
    const [, serial, list, progress, details, info] = cells.map(c => c.text);
    const d = (details || "").replace(/\n/g, " ");
    const pick = re => (d.match(re)?.[1] || "").trim();
    out.push({
      court, in_session: true, serial, list, progress, info: info || "",
      case: pick(/Case Details\s*-\s*(\S+)/),
      title: pick(/Title\s*:\s*(.*?)\s*Petitioner's Counsels?/i).replace(/-\s+/g, ""),
      petitioner_counsel: pick(/Petitioner's Counsels?\s*-\s*(.*?)\s*Respondent's Counsel/i),
      respondent_counsel: pick(/Respondent's Counsels?\s*-\s*(.*)$/i),
    });
  }
  return out;
}

// ---------- roll-number case search (you solve the court's captcha) ----------
function cookiesFrom(res) {
  const all = res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get("Set-Cookie") || ""];
  return all.map(c => c.split(";")[0]).filter(Boolean).join("; ");
}

async function rollStart(cors) {
  const page = await fetch(HC + "advocate-cases-roll-wise", { headers: { "User-Agent": UA } });
  const cookie = cookiesFrom(page);
  const html = await page.text();
  const captchaId = html.match(/name="captcha_id" value="([^"]+)"/)?.[1];
  if (!captchaId) return json({ error: "The court page has changed. Open it directly for now." }, 502, cors);
  const img = await fetch(HC + "secureimage/securimage?captcha_id=" + captchaId, {
    headers: { "User-Agent": UA, Cookie: cookie, Referer: HC + "advocate-cases-roll-wise" },
  });
  const cookie2 = [cookie, cookiesFrom(img)].filter(Boolean).join("; ");
  const buf = new Uint8Array(await img.arrayBuffer());
  let bin = ""; for (const b of buf) bin += String.fromCharCode(b);
  const type = img.headers.get("Content-Type") || "image/png";
  const session = btoa(JSON.stringify({ cookie: cookie2, captchaId }));
  return json({ session, image: `data:${type};base64,${btoa(bin)}` }, 200, cors);
}

async function rollSearch(body, cors) {
  const { session, year } = body || {};
  const roll = String(body?.roll || "").trim().toUpperCase().replace(/\s+/g, "");
  const captcha = String(body?.captcha || "").trim();
  const missing = [!roll && "roll number", !year && "case year", !captcha && "captcha", !session && "a fresh captcha (tap New captcha)"].filter(Boolean);
  if (missing.length) return json({ ok: false, error: "Missing " + missing.join(", ") + "." }, 400, cors);
  if (!/^[A-Z]{1,3}\/[A-Z]{0,3}\d{1,6}\/\d{4}$/.test(roll)) return json({ ok: false, error: "Roll number should look like A/X0000/2012." }, 400, cors);
  const { cookie, captchaId } = JSON.parse(atob(session));
  const form = new URLSearchParams({ adv_roll: roll, case_year: String(year), captcha_id: captchaId, captchacode: captcha });
  const r = await fetch(HC + "get_ListedCaseRoll", {
    method: "POST",
    headers: {
      "User-Agent": UA, Cookie: cookie, Referer: HC + "advocate-cases-roll-wise",
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest",
    },
    body: form,
  });
  const html = await r.text();
  return json(parseRollResult(html), 200, cors);
}

export function parseRollResult(html) {
  const text = strip(html);
  if (/captcha/i.test(text) && /(invalid|wrong|not match|incorrect)/i.test(text))
    return { ok: false, error: "The captcha didn't match. Try the new one." };
  const tables = [...html.matchAll(/<table[\s\S]*?<\/table>/gi)].map(m => m[0]);
  const rows = [];
  let headers = [];
  for (const t of tables) {
    for (const tr of t.split(/<tr[\s>]/i).slice(1)) {
      const ths = [...tr.matchAll(/<th[^>]*>([\s\S]*?)<\/th>/gi)].map(m => strip(m[1]));
      if (ths.length) { headers = ths; continue; }
      const tds = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map(m => strip(m[1]));
      const v = tr.match(/viewCaseData\(\s*['"]?([^'",)]+)['"]?\s*(?:,\s*['"]?([^'")]*))?/);
      if (tds.length >= 2) rows.push({ cells: tds, cino: v?.[1], source: v?.[2] || "" });
    }
  }
  return { ok: true, headers, rows, message: rows.length ? "" : text.slice(0, 300) };
}

// ---------- orders ----------
export function parseOrders(html) {
  const sheet = html.match(/href='([^']*WebDownloadOrderSheet[^']*)'/)?.[1]?.replace(/&amp;/g, "&") || "";
  const orders = [];
  for (const tr of html.split(/<tr[\s>]/i).slice(1)) {
    const tds = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map(m => m[1]);
    if (tds.length < 3) continue;
    const date = tds[1].replace(/<[^>]+>|\s/g, "");
    const link = tds[2].match(/href='([^']*WebDownloadJudgmentDocument[^']*)'/)?.[1] || "";
    if (/^\d{2}-\d{2}-\d{4}$/.test(date)) orders.push({ date, url: link });
  }
  return { sheet, orders };
}

async function orders(caseNo, cors) {
  const m = caseNo.trim().toUpperCase().match(/^([A-Z][A-Z0-9.\-()]*)\/(\d+)\/(\d{4})$/);
  if (!m) return json({ ok: false, error: "Case number should look like BAIL/16404/2026." }, 400, cors);
  const r = await fetch(HC + "get-order-sheets", {
    method: "POST",
    headers: { "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest" },
    body: new URLSearchParams({ ct: m[1], cn: m[2], cy: m[3] }),
  });
  return json({ ok: true, case: caseNo.toUpperCase(), ...parseOrders(await r.text()) }, 200, { ...cors, "Cache-Control": "max-age=600" });
}

// ---------- one case's full details (needs the session from a successful roll search) ----------
async function rollCase(body, cors) {
  const { session, cino } = body || {};
  if (!cino) return json({ ok: false, error: "This case has no court record id. Sync it from the court again." }, 400, cors);
  const ask = async cookie => {
    const r = await fetch(HC + "get_CaseDetails", {
      method: "POST",
      headers: { "User-Agent": UA, Cookie: cookie, Referer: HC + "advocate-cases-roll-wise",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest" },
      body: new URLSearchParams({ cino, source: body.source || "" }),
    });
    return r.text();
  };
  const usable = h => h && h.length > 200 && !/PHP Error/i.test(h) && /<table/i.test(h);
  // the saved session from your sync first; if it has expired, a fresh visit to the same court page
  let html = "";
  if (session) { try { html = await ask(JSON.parse(atob(session)).cookie); } catch (e) {} }
  if (!usable(html)) {
    const page = await fetch(HC + "advocate-cases-roll-wise", { headers: { "User-Agent": UA } });
    html = await ask(cookiesFrom(page));
  }
  if (!usable(html)) return json({ ok: false, error: "The court didn't return details for this case right now. Try again, or sync this year again." }, 200, cors);
  const sections = [];
  let title = "";
  for (const part of html.split(/(<h\d[^>]*>[\s\S]*?<\/h\d>)/i)) {
    if (/^<h\d/i.test(part)) { title = strip(part); continue; }
    for (const t of part.match(/<table[\s\S]*?<\/table>/gi) || []) {
      const rows = t.split(/<tr[\s>]/i).slice(1).map(tr => [...tr.matchAll(/<t[hd][^>]*>([\s\S]*?)<\/t[hd]>/gi)].map(m => strip(m[1]))).filter(r => r.some(Boolean));
      if (rows.length) sections.push({ title, rows });
      title = "";
    }
  }
  return json({ ok: true, sections }, 200, cors);
}
