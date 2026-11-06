// Runs the relay's handlers under Node against the live court site (no Cloudflare needed).
import fs from 'fs';
globalThis.caches = { default: { match: async () => null, put: async () => {} } };
const w = (await import('./worker.js')).default;
const ctx = { waitUntil() {} }, env = {};
const call = async (path, init = {}) => {
  const r = await w.fetch(new Request('https://relay.test' + path, { headers: { Origin: 'https://harshofficial73-pixel.github.io' }, ...init }), env, ctx);
  return { status: r.status, body: await r.json() };
};
const board = await call('/board');
const start = await call('/roll/start');
const ord = await call('/orders?case=BAIL/16404/2026');
const bad = start.body.session ? await call('/roll/search', { method: 'POST', body: JSON.stringify({ session: start.body.session, roll: 'A/A0000/2012', year: 2024, captcha: '000000' }) }) : null;
const rep = {
  board: { status: board.status, courts: board.body.courts?.length, in_session: board.body.courts?.filter(c => c.in_session).length, first: board.body.courts?.[0] },
  roll_start: { status: start.status, has_session: !!start.body.session, image_prefix: start.body.image?.slice(0, 30), image_len: start.body.image?.length, error: start.body.error },
  roll_search_wrong_captcha: bad,
  orders: { status: ord.status, count: ord.body.orders?.length, sheet: !!ord.body.sheet },
  missing_fields: (await call('/roll/search', { method: 'POST', body: JSON.stringify({ session: start.body.session, roll: '', year: 2024, captcha: '' }) })).body,
};
console.log(JSON.stringify(rep, null, 1));
fs.writeFileSync('../selftest/relay.json', JSON.stringify(rep, null, 1));
