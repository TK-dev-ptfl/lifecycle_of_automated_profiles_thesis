// The server's promises to participants and to the analysis: no session
// without consent, no write without the session's token, deletion and
// withdrawal really delete, cohort labels cannot be self-assigned, and
// nothing outside public/ is served.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import zlib from 'node:zlib';
import { mkdtemp, rm, readdir, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createApp, config, CONSENT_VERSION } from '../server/server.mjs';

let server, base, dataDir;
before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), 'social-lab-test-'));
  const cfg = { ...config({}), dataDir, ipLookup: false, adminToken: 'admin-secret', cohortKey: 'cohort-secret', dev: false, maxSessionsPerIpDay: 1000 };
  server = http.createServer(createApp(cfg).handler);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => { server.close(); await rm(dataDir, { recursive: true, force: true }); });

const post = (p, body, headers = {}) => fetch(base + p, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: typeof body === 'string' || body instanceof Uint8Array ? body : JSON.stringify(body) });
const consent = extra => post('/api/session', { consent: true, adult: true, consentVersion: CONSENT_VERSION, ...extra });

test('no session without full consent and the current consent version', async () => {
  for (const body of [{}, { consent: true, consentVersion: CONSENT_VERSION }, { consent: true, adult: true, consentVersion: '0.1' }]) {
    assert.equal((await post('/api/session', body)).status, 400);
  }
  assert.equal((await consent()).status, 201);
});

test('the navigation headers are attached only when consent arrives, in order', async () => {
  const page = await fetch(base + '/', { headers: { 'Accept-Language': 'sk-SK' } });
  const cookie = page.headers.get('set-cookie').split(';')[0];
  const s = await (await consent()).json();
  const r = await post('/api/session', { consent: true, adult: true, consentVersion: CONSENT_VERSION }, { cookie });
  const s2 = await r.json();
  const meta = JSON.parse(await readFile(path.join(dataDir, 'sessions', s2.sessionId, 'meta.json'), 'utf8'));
  assert.equal(meta.network.navigation_headers.values['accept-language'], 'sk-SK');
  assert.ok(Array.isArray(meta.network.navigation_headers.order));
  const meta1 = JSON.parse(await readFile(path.join(dataDir, 'sessions', s.sessionId, 'meta.json'), 'utf8'));
  assert.equal(meta1.network.navigation_headers, null, 'no cookie, no navigation headers');
  assert.ok(!JSON.stringify(meta).includes('127.0.0.1'), 'the IP address is not stored');
});

test('writes need the session token; gzip batches are accepted', async () => {
  const s = await (await consent()).json();
  const url = `/api/session/${s.sessionId}/batch`;
  const batch = { seq: 0, sent: Date.now(), events: [['pm', 1, 2, 3, 0, 0, 0, 'm', 1, []]] };
  assert.equal((await post(url, batch)).status, 403);
  assert.equal((await post(url, batch, { 'x-session-token': 'wrong' })).status, 403);
  const gz = zlib.gzipSync(JSON.stringify(batch));
  const r = await post(url, gz, { 'x-session-token': s.writeToken, 'content-encoding': 'gzip' });
  assert.equal(r.status, 200);
  assert.ok(typeof (await r.json()).serverTime === 'number');
  const lines = (await readFile(path.join(dataDir, 'sessions', s.sessionId, 'events.ndjson'), 'utf8')).trim().split('\n');
  assert.deepEqual(JSON.parse(lines[0]).events, batch.events);
});

test('a cohort label other than human needs the cohort key', async () => {
  assert.equal((await consent({ cohort: 'bot-v1' })).status, 403);
  assert.equal((await consent({ cohort: 'bot-v1', cohortKey: 'nope' })).status, 403);
  const s = await (await consent({ cohort: 'bot-v1', cohortKey: 'cohort-secret' })).json();
  const meta = JSON.parse(await readFile(path.join(dataDir, 'sessions', s.sessionId, 'meta.json'), 'utf8'));
  assert.equal(meta.cohort, 'bot-v1');
});

test('withdrawal deletes the session immediately', async () => {
  const s = await (await consent()).json();
  assert.equal((await post(`/api/session/${s.sessionId}/withdraw`, {}, { 'x-session-token': s.writeToken })).status, 200);
  assert.ok(!(await readdir(path.join(dataDir, 'sessions'))).includes(s.sessionId));
});

test('the deletion code deletes the session later; only its hash is stored', async () => {
  const s = await (await consent()).json();
  const meta = await readFile(path.join(dataDir, 'sessions', s.sessionId, 'meta.json'), 'utf8');
  assert.ok(!meta.includes(s.deletionCode) && !meta.includes(s.writeToken));
  assert.equal((await post('/api/delete', { code: 'WRONG' })).status, 404);
  assert.equal((await post('/api/delete', { code: s.deletionCode.toLowerCase() })).status, 200);
  assert.ok(!(await readdir(path.join(dataDir, 'sessions'))).includes(s.sessionId));
});

test('nothing outside public/ is served', async () => {
  for (const p of ['/../server/server.mjs', '/%2e%2e/server/server.mjs', '/..%2f.env', '/../data/sessions']) {
    assert.equal((await fetch(base + p)).status, 404, p);
  }
  assert.equal((await fetch(base + '/js/main.js')).status, 200);
});

test('admin endpoints need the admin token', async () => {
  assert.equal((await fetch(base + '/admin/sessions')).status, 403);
  const r = await fetch(base + '/admin/sessions', { headers: { authorization: 'Bearer admin-secret' } });
  assert.equal(r.status, 200);
  assert.ok(Array.isArray(await r.json()));
});

test('the reCAPTCHA score is never returned to the page', async () => {
  const s = await (await consent()).json();
  const r = await post(`/api/session/${s.sessionId}/recaptcha`, { token: 'x', action: 'like' }, { 'x-session-token': s.writeToken });
  const text = await r.text();
  assert.ok(!/score/.test(text));
});

test('a finished session accepts no more events', async () => {
  const s = await (await consent()).json();
  const h = { 'x-session-token': s.writeToken };
  assert.equal((await post(`/api/session/${s.sessionId}/end`, { survey: {} }, h)).status, 200);
  assert.equal((await post(`/api/session/${s.sessionId}/batch`, { seq: 1, events: [] }, h)).status, 409);
});
