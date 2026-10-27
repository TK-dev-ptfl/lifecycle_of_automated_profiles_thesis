// Off-server storage: encryption, the GitHub sink, and the server's upload,
// deletion and abandoned-session handling - against an in-memory imitation of
// GitHub's contents API, so no real repository is touched.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, rm, readdir, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { seal, open, generateKeys } from '../server/seal.mjs';
import { GitHubSink } from '../server/github-sink.mjs';
import { createApp, config, CONSENT_VERSION } from '../server/server.mjs';
import { hashCode } from '../server/store.mjs';
import { decryptAll } from '../analysis/decrypt.mjs';

const keys = generateKeys();

function fakeGitHub({ private: isPrivate = true, failPut = false } = {}) {
  const files = new Map();
  const calls = [];
  let n = 0;
  const fetch = async (url, init = {}) => {
    const method = init.method || 'GET';
    calls.push(method);
    const reply = (status, json) => ({ status, json: async () => json });
    const u = new URL(url);
    if (u.pathname === '/repos/me/data') return reply(200, { private: isPrivate, permissions: { push: true } });
    const p = decodeURIComponent(u.pathname.replace('/repos/me/data/contents/', ''));
    const body = init.body ? JSON.parse(init.body) : null;
    if (method === 'GET') return files.has(p) ? reply(200, { sha: files.get(p).sha }) : reply(404, { message: 'Not Found' });
    if (method === 'PUT') {
      if (failPut) return reply(500, { message: 'boom' });
      if (files.has(p) && body.sha !== files.get(p).sha) return reply(409, { message: 'sha mismatch' });
      files.set(p, { sha: 's' + ++n, content: Buffer.from(body.content, 'base64') });
      return reply(201, {});
    }
    if (method === 'DELETE') {
      if (!files.has(p) || files.get(p).sha !== body.sha) return reply(409, {});
      files.delete(p); return reply(200, {});
    }
    return reply(400, {});
  };
  return { files, calls, fetch };
}

test('seal and open round-trip; tampering and the wrong key both fail', () => {
  const msg = Buffer.from('{"events":[1,2,3]}');
  const s = seal(msg, keys.publicKey);
  assert.ok(!s.includes(msg), 'ciphertext does not contain the plaintext');
  assert.deepEqual(open(s, keys.privateKey), msg);
  const bad = Buffer.from(s); bad[bad.length - 1] ^= 1;
  assert.throws(() => open(bad, keys.privateKey));
  assert.throws(() => open(s, generateKeys().privateKey));
});

test('the sink refuses to run without encryption, and refuses a public repository', async () => {
  assert.throws(() => new GitHubSink({ repo: 'me/data', token: 't' }), /never uploaded unencrypted/);
  const gh = fakeGitHub({ private: false });
  await assert.rejects(new GitHubSink({ repo: 'me/data', token: 't', publicKey: keys.publicKey, fetch: gh.fetch }).check(), /public/);
});

// --- the server with a sink ---

let dataDir, server, base, gh, app;
before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), 'social-lab-storage-'));
  gh = fakeGitHub();
  const sink = new GitHubSink({ repo: 'me/data', token: 't', publicKey: keys.publicKey, fetch: gh.fetch, log: () => {} });
  app = createApp({ ...config({}), dataDir, ipLookup: false, maxSessionsPerIpDay: 1000, idleMs: 60_000 }, { sink });
  server = http.createServer(app.handler);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => { server.close(); await rm(dataDir, { recursive: true, force: true }); });

const post = (p, body, headers = {}) => fetch(base + p, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body) });
const startSession = async () => (await post('/api/session', { consent: true, adult: true, consentVersion: CONSENT_VERSION })).json();
const until = async (cond, ms = 3000) => { const t = Date.now(); while (!(await cond())) { if (Date.now() - t > ms) throw new Error('timeout'); await new Promise(r => setTimeout(r, 20)); } };
const local = async () => readdir(path.join(dataDir, 'sessions'));

test('a finished session is sealed, uploaded under its code hash, and removed locally', async () => {
  const s = await startSession();
  const h = { 'x-session-token': s.writeToken };
  await post(`/api/session/${s.sessionId}/batch`, { seq: 0, events: [['pm', 1, 2, 3, 0, 0, 0, 'm', 1, []]] }, h);
  await post(`/api/session/${s.sessionId}/end`, { survey: { device: 'mouse' } }, h);
  const key = GitHubSink.pathFor(hashCode(s.deletionCode));
  await until(() => gh.files.has(key));
  await until(async () => !(await local()).includes(s.sessionId));
  const stored = gh.files.get(key).content;
  assert.ok(!stored.toString('latin1').includes('consent_version'), 'the repository holds ciphertext only');
  const bundle = JSON.parse(zlib.gunzipSync(open(stored, keys.privateKey)));
  assert.equal(bundle.id, s.sessionId);
  assert.deepEqual(Object.keys(bundle.files).sort(), ['end.json', 'events.ndjson', 'meta.json']);
  assert.equal(JSON.parse(bundle.files['meta.json']).ended_reason, 'finished');
});

test('the deletion code deletes the uploaded session from the repository', async () => {
  const s = await startSession();
  await post(`/api/session/${s.sessionId}/end`, {}, { 'x-session-token': s.writeToken });
  const key = GitHubSink.pathFor(hashCode(s.deletionCode));
  await until(() => gh.files.has(key));
  const r = await post('/api/delete', { code: s.deletionCode.toLowerCase() });
  assert.equal(r.status, 200);
  assert.ok(!gh.files.has(key));
  assert.equal((await post('/api/delete', { code: s.deletionCode })).status, 404);
});

test('an abandoned session is uploaded by the sweep; shutdown uploads the rest', async () => {
  const idle = await startSession();
  const busy = await startSession();
  app.store.lastActivity = async id => (id === idle.sessionId ? Date.now() - 61_000 : Date.now());
  assert.equal(await app.sweep(), 1);
  assert.ok(gh.files.has(GitHubSink.pathFor(hashCode(idle.deletionCode))));
  assert.ok((await local()).includes(busy.sessionId), 'an active session is left alone');
  await app.sweep(true);
  const bundle = JSON.parse(zlib.gunzipSync(open(gh.files.get(GitHubSink.pathFor(hashCode(busy.deletionCode))).content, keys.privateKey)));
  assert.equal(JSON.parse(bundle.files['meta.json']).ended_reason, 'shutdown');
  delete app.store.lastActivity;
});

test('a failed upload keeps the session on disk for the next sweep', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'social-lab-fail-'));
  const failing = fakeGitHub({ failPut: true });
  const a = createApp({ ...config({}), dataDir: dir, ipLookup: false }, { sink: new GitHubSink({ repo: 'me/data', token: 't', publicKey: keys.publicKey, fetch: failing.fetch }) });
  const { id } = await a.store.create({ cohort: 'human' });
  const err = console.error; console.error = () => {};
  assert.equal(await a.upload(id, 'ended'), false);
  console.error = err;
  assert.ok(await a.store.exists(id));
  await rm(dir, { recursive: true, force: true });
});

test('decrypt rebuilds session folders from a repository clone, dropping deleted ones', async () => {
  const repo = await mkdtemp(path.join(tmpdir(), 'social-lab-repo-'));
  const out = await mkdtemp(path.join(tmpdir(), 'social-lab-out-'));
  await mkdir(path.join(repo, 'sessions', 'ab'), { recursive: true });
  const bundle = { format: 'social-lab-session-1', id: 'a'.repeat(32), files: { 'meta.json': '{"cohort":"human"}', '../evil': 'x' } };
  await writeFile(path.join(repo, 'sessions', 'ab', 'x.sle'), seal(zlib.gzipSync(JSON.stringify(bundle)), keys.publicKey));
  await mkdir(path.join(out, 'sessions', 'b'.repeat(32)), { recursive: true });   // stale: no longer in the repo
  const r = await decryptAll(repo, out, keys.privateKey);
  assert.equal(r.ok, 1);
  assert.deepEqual(await readdir(path.join(out, 'sessions')), ['a'.repeat(32)]);
  assert.deepEqual(await readdir(path.join(out, 'sessions', 'a'.repeat(32))), ['meta.json'], 'no path traversal from a bundle');
  await rm(repo, { recursive: true, force: true }); await rm(out, { recursive: true, force: true });
});

test('the consent page is told where data is stored', async () => {
  assert.equal((await (await fetch(base + '/api/config')).json()).storage, 'github');
});

test('on Railway the server listens publicly and trusts X-Real-IP', () => {
  const c = config({ RAILWAY_ENVIRONMENT_NAME: 'production' });
  assert.equal(c.host, '0.0.0.0');
  assert.equal(c.trustProxy, true);
  assert.equal(config({}).trustProxy, false);
});
