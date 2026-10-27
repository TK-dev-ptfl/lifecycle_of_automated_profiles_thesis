// Social Lab server. Node 24, no dependencies.
//
//   node server/server.mjs            (reads .env next to package.json)
//
// Serves the study site from public/, accepts the data the page records after
// consent, verifies reCAPTCHA tokens, and records network signals about each
// session. With TLS_CERT / TLS_KEY set it terminates TLS itself, which is the
// only way to see the TLS ClientHello (JA4/JA3); behind a reverse proxy those
// are unavailable. See README.md.
//
// With DATA_REPO set (hosts without a persistent disk, e.g. Railway), finished
// sessions are sealed with DATA_PUBLIC_KEY and moved to that private GitHub
// repository; see server/github-sink.mjs and deploy/DEPLOY_RAILWAY.md.

import http from 'node:http';
import net from 'node:net';
import tls from 'node:tls';
import { Duplex } from 'node:stream';
import zlib from 'node:zlib';
import { readFile } from 'node:fs/promises';
import { readFileSync, existsSync } from 'node:fs';
import { randomBytes, timingSafeEqual, createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { Store, hashCode } from './store.mjs';
import { GitHubSink } from './github-sink.mjs';
import { readKey, checkPublicKey } from './seal.mjs';
import { extractClientHello, fingerprintHello } from './tls-fingerprint.mjs';
import { headerSignals, clientIp, dailyIpHash, lookupNetwork, webrtcMatches } from './network.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PUBLIC = path.join(ROOT, 'public');

// Must change whenever the consent text or what is collected changes, so every
// session records which version its participant agreed to.
export const STUDY_VERSION = '1.1.0';
// 1.1: sessions may be stored encrypted in a private GitHub repository.
export const CONSENT_VERSION = '1.1';

function loadEnv(file) {
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (value.length > 1 && value[0] === value.at(-1) && `"'`.includes(value[0])) value = value.slice(1, -1);
    if (!(key in process.env)) process.env[key] = value;
  }
}

export function config(env = process.env) {
  // Railway sets RAILWAY_ENVIRONMENT_NAME. There the app must listen on all
  // interfaces and sits behind Railway's proxy, which reports the client in
  // X-Real-IP.
  const railway = !!env.RAILWAY_ENVIRONMENT_NAME;
  return {
    host: env.HOST || (railway ? '0.0.0.0' : '127.0.0.1'),
    port: Number(env.PORT || 8090),
    dataDir: path.resolve(ROOT, env.DATA_DIR || 'data'),
    tlsCert: env.TLS_CERT || '', tlsKey: env.TLS_KEY || '',
    httpRedirectPort: Number(env.HTTP_REDIRECT_PORT || 0),
    trustProxy: env.TRUST_PROXY ? env.TRUST_PROXY === '1' : railway,
    recaptchaSiteKey: env.RECAPTCHA_SITE_KEY || '', recaptchaSecret: env.RECAPTCHA_SECRET || '',
    adminToken: env.ADMIN_TOKEN || '',
    cohortKey: env.COHORT_KEY || '',
    contact: env.STUDY_CONTACT || '', researcher: env.STUDY_RESEARCHER || '', institution: env.STUDY_INSTITUTION || '',
    webrtc: env.WEBRTC_CHECK === '1',
    ipLookup: env.IP_LOOKUP !== '0',
    dev: env.DEV === '1',
    maxSessionBytes: Number(env.MAX_SESSION_MB || 60) * 1024 * 1024,
    maxSessionsPerIpDay: Number(env.MAX_SESSIONS_PER_IP_DAY || 10),
    dataRepo: env.DATA_REPO || '', dataRepoToken: env.DATA_REPO_TOKEN || '', dataRepoBranch: env.DATA_REPO_BRANCH || 'main',
    // GitHub Enterprise, or a stand-in for testing.
    dataRepoApi: env.DATA_REPO_API || 'https://api.github.com',
    dataPublicKey: readKey(env.DATA_PUBLIC_KEY),
    // A session with no writes for this long is treated as abandoned and uploaded.
    idleMs: Number(env.IDLE_MINUTES || 30) * 60_000,
  };
}

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8' };

const send = (res, code, body, headers = {}) => {
  const data = typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  res.writeHead(code, { 'content-type': typeof body === 'object' && !Buffer.isBuffer(body) ? 'application/json' : 'text/plain; charset=utf-8',
    'cache-control': 'no-store', ...headers });
  res.end(data);
};

async function readBody(req, limit) {
  const chunks = []; let size = 0;
  for await (const c of req) { size += c.length; if (size > limit) throw Object.assign(new Error('body too large'), { status: 413 }); chunks.push(c); }
  let buf = Buffer.concat(chunks);
  if (req.headers['content-encoding'] === 'gzip') buf = zlib.gunzipSync(buf, { maxOutputLength: limit * 8 });
  return buf.length ? JSON.parse(buf.toString('utf8')) : {};
}

function securityHeaders(cfg) {
  const google = 'https://www.google.com https://www.gstatic.com https://www.recaptcha.net';
  return {
    'content-security-policy': [
      "default-src 'self'", `script-src 'self' ${google}`, `frame-src ${google}`, "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:", "connect-src 'self'","worker-src 'self' blob:", "object-src 'none'", "base-uri 'none'",
    ].join('; '),
    'referrer-policy': 'no-referrer', 'x-content-type-options': 'nosniff', 'permissions-policy': 'interest-cohort=()',
    ...(cfg.tlsCert ? { 'strict-transport-security': 'max-age=31536000' } : {}),
  };
}

export function createApp(cfg, { sink } = {}) {
  const store = new Store(cfg.dataDir);
  const ready = store.init();
  if (sink === undefined && cfg.dataRepo) {
    if (!cfg.dataPublicKey) throw new Error('DATA_REPO is set but DATA_PUBLIC_KEY is not: sessions are never uploaded unencrypted. Run: npm run keygen');
    try { checkPublicKey(cfg.dataPublicKey); } catch (e) { throw new Error('DATA_PUBLIC_KEY is not a valid RSA public key (' + e.message + '). Paste the line printed by npm run keygen.'); }
    sink = new GitHubSink({ repo: cfg.dataRepo, token: cfg.dataRepoToken, branch: cfg.dataRepoBranch, api: cfg.dataRepoApi, publicKey: cfg.dataPublicKey });
  }
  const uploading = new Set();

  /** Seals the session, uploads it, and removes the local copy. A failed
   *  upload keeps the local copy for the next sweep to retry. */
  async function upload(id, reason) {
    if (!sink || uploading.has(id) || !(await store.exists(id))) return false;
    uploading.add(id);
    try {
      let meta = await store.meta(id);
      if (!meta.ended_at) {
        meta = { ...meta, ended_at: new Date().toISOString(), ended_reason: reason, bytes: await store.size(id) };
        await store.writeJSON(id, 'meta.json', meta);
      }
      await sink.upload(meta.deletion_code_sha256, await store.bundle(id));
      await store.remove(id);
      console.log(`[social-lab] session uploaded (${reason})`);
      return true;
    } catch (e) {
      console.error(`[social-lab] upload failed, kept locally: ${e.message}`);
      return false;
    } finally { uploading.delete(id); }
  }

  /** Uploads sessions that ended, or have been idle longer than idleMs.
   *  With all=true (shutdown), uploads every session still on disk. */
  async function sweep(all = false) {
    await ready;
    let n = 0;
    for (const id of await store.list()) {
      try {
        const meta = await store.meta(id);
        const idle = Date.now() - (await store.lastActivity(id)) > cfg.idleMs;
        const reason = meta.ended_at ? 'ended' : idle ? 'abandoned' : 'shutdown';
        if (all || meta.ended_at || idle) n += (await upload(id, reason)) ? 1 : 0;
      } catch { /* half-written session: next sweep */ }
    }
    return n;
  }
  // Headers of the page navigation, held until consent (then stored) or for
  // 30 minutes (then dropped). Keyed by a random cookie, not by the person.
  const navByCookie = new Map();
  const sessionsPerIpDay = new Map();
  const sec = securityHeaders(cfg);

  async function serveStatic(req, res, url) {
    let rel = decodeURIComponent(url.pathname);
    if (rel === '/') rel = '/index.html';
    const file = path.resolve(PUBLIC, '.' + rel);
    if (!file.startsWith(PUBLIC + path.sep) || !existsSync(file)) return send(res, 404, 'Not found', sec);
    const headers = { 'content-type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'cache-control': 'no-store', ...sec };
    if (rel === '/index.html') {
      const id = randomBytes(12).toString('base64url');
      navByCookie.set(id, { at: Date.now(), headers: headerSignals(req) });
      for (const [k, v] of navByCookie) if (v.at < Date.now() - 1800_000) navByCookie.delete(k);
      headers['set-cookie'] = `sl_nav=${id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=1800${cfg.tlsCert ? '; Secure' : ''}`;
    }
    res.writeHead(200, headers);
    res.end(await readFile(file));
  }

  async function authed(req, id) {
    return store.checkToken(id, req.headers['x-session-token']);
  }

  async function handle(req, res) {
    await ready;
    const url = new URL(req.url, 'http://x');
    const p = url.pathname;
    const m = p.match(/^\/api\/session\/([a-f0-9]{32})\/(\w+)$/);

    if (req.method === 'GET' && p === '/api/config') {
      return send(res, 200, {
        studyVersion: STUDY_VERSION, consentVersion: CONSENT_VERSION,
        recaptchaSiteKey: cfg.recaptchaSiteKey || null, webrtc: cfg.webrtc,
        researcher: cfg.researcher, institution: cfg.institution, contact: cfg.contact,
        // The consent text describes where data goes, so it must follow the configuration.
        storage: sink ? 'github' : 'local',
      });
    }

    if (req.method === 'POST' && p === '/api/session') {
      const body = await readBody(req, 64 * 1024);
      if (body.consent !== true || body.adult !== true || body.consentVersion !== CONSENT_VERSION) {
        return send(res, 400, { error: 'consent required' });
      }
      const ip = clientIp(req, cfg.trustProxy);
      const ipDay = dailyIpHash(ip);
      const n = (sessionsPerIpDay.get(ipDay) || 0) + 1;
      if (n > cfg.maxSessionsPerIpDay && !cfg.dev) return send(res, 429, { error: 'too many sessions from this network today' });
      sessionsPerIpDay.set(ipDay, n);

      // Cohort labels the session as ground truth. Anything other than a
      // human participant must present the cohort key, so a visitor cannot
      // label themselves a bot (or the reverse) by editing a URL.
      let cohort = 'human';
      if (body.cohort && body.cohort !== 'human') {
        if (cfg.cohortKey && body.cohortKey === cfg.cohortKey && /^[a-z0-9_-]{1,40}$/.test(body.cohort)) cohort = body.cohort;
        else return send(res, 403, { error: 'invalid cohort key' });
      }
      const cookie = (req.headers.cookie || '').match(/(?:^|;\s*)sl_nav=([\w-]+)/)?.[1];
      const nav = cookie ? navByCookie.get(cookie) : null;
      if (cookie) navByCookie.delete(cookie);
      const salt = randomBytes(16).toString('hex');
      const { id, deletionCode, writeToken } = await store.create({
        study_version: STUDY_VERSION, consent_version: CONSENT_VERSION, consented_at: new Date().toISOString(),
        cohort, run_label: typeof body.runLabel === 'string' ? body.runLabel.slice(0, 80) : null,
        server_started: Date.now(),
        network: {
          tls: req.socket.sl?.tls || (cfg.tlsCert ? { status: 'not-captured' } : { status: 'no-tls (behind proxy or http)' }),
          navigation_headers: nav ? nav.headers : null,
          api_headers: headerSignals(req),
          ip_network: cfg.ipLookup ? await lookupNetwork(ip) : { status: 'disabled' },
          ip_sessions_today: n,
          ip_day_hash: ipDay,
          // Behind a proxy the header order is the proxy's, not the browser's,
          // and there is no TLS fingerprint (docs/DATA_DICTIONARY.md, Network).
          behind_proxy: cfg.trustProxy,
        },
        webrtc_salt: salt,
      });
      return send(res, 201, { sessionId: id, writeToken, deletionCode, serverTime: Date.now(), webrtcSalt: cfg.webrtc ? salt : null });
    }

    if (req.method === 'POST' && p === '/api/delete') {
      const body = await readBody(req, 4096);
      const code = String(body.code || '').trim().toUpperCase();
      let deleted = !!(await store.deleteByCode(code));
      if (!deleted && sink && code) {
        try { deleted = await sink.remove(hashCode(code)); }
        catch (e) { console.error('[social-lab] remote delete failed:', e.message); return send(res, 503, { error: 'storage unavailable, try again later' }); }
      }
      return send(res, deleted ? 200 : 404, { deleted });
    }

    if (m && req.method === 'POST') {
      const [, id, action] = m;
      if (!(await authed(req, id))) return send(res, 403, { error: 'bad session token' });

      if (action === 'withdraw') { await store.remove(id); return send(res, 200, { deleted: true }); }

      const meta = await store.meta(id);
      if (meta.ended_at && action !== 'end') return send(res, 409, { error: 'session ended' });
      if ((meta.bytes || 0) > cfg.maxSessionBytes) return send(res, 413, { error: 'session size limit reached' });

      if (action === 'batch') {
        const body = await readBody(req, 4 * 1024 * 1024);
        if (!Array.isArray(body.events)) return send(res, 400, { error: 'events must be an array' });
        await store.append(id, 'events.ndjson', { seq: body.seq | 0, sent: Number(body.sent) || null, recv: Date.now(), events: body.events });
        return send(res, 200, { ok: true, serverTime: Date.now() });
      }
      if (action === 'device') {
        const body = await readBody(req, 512 * 1024);
        await store.writeJSON(id, 'device.json', { recv: Date.now(), ...body });
        return send(res, 200, { ok: true });
      }
      if (action === 'recaptcha') {
        const body = await readBody(req, 16 * 1024);
        if (!cfg.recaptchaSecret) return send(res, 501, { error: 'recaptcha not configured' });
        let result;
        try {
          const r = await fetch('https://www.google.com/recaptcha/api/siteverify', {
            method: 'POST', signal: AbortSignal.timeout(8000),
            body: new URLSearchParams({ secret: cfg.recaptchaSecret, response: String(body.token || ''), remoteip: clientIp(req, cfg.trustProxy) }),
          });
          result = await r.json();
        } catch (e) { result = { success: false, 'error-codes': [String(e.message || e)] }; }
        await store.append(id, 'recaptcha.ndjson', {
          recv: Date.now(), client_t: Number(body.t) || null, requested_action: String(body.action || '').slice(0, 40),
          success: !!result.success, score: result.score ?? null, action: result.action ?? null,
          hostname: result.hostname ?? null, challenge_ts: result.challenge_ts ?? null, errors: result['error-codes'] || [],
        });
        // The score is never sent back: a participant who saw it could change
        // how they behave, and the score is what is being measured.
        return send(res, 200, { ok: true });
      }
      if (action === 'webrtc') {
        const body = await readBody(req, 16 * 1024);
        const hashes = Array.isArray(body.hashes) ? body.hashes.filter(h => /^[a-f0-9]{64}$/.test(h)).slice(0, 10) : [];
        const result = webrtcMatches(meta.webrtc_salt, clientIp(req, cfg.trustProxy), hashes);
        await store.writeJSON(id, 'meta.json', { ...meta, webrtc: { ...result, status: body.status || 'ok' } });
        return send(res, 200, { ok: true });
      }
      if (action === 'end') {
        const body = await readBody(req, 64 * 1024);
        await store.writeJSON(id, 'end.json', { recv: Date.now(), ...body });
        await store.writeJSON(id, 'meta.json', { ...meta, ended_at: new Date().toISOString(), ended_reason: 'finished', bytes: await store.size(id) });
        send(res, 200, { ok: true });
        upload(id, 'ended');
        return;
      }
      return send(res, 404, { error: 'unknown action' });
    }

    if (p.startsWith('/admin/')) {
      const token = req.headers.authorization?.replace(/^Bearer /, '') || '';
      // Compared as hashes in constant time, so response timing does not leak the token.
      const h = x => createHash('sha256').update(String(x)).digest();
      if (!cfg.adminToken || !timingSafeEqual(h(token), h(cfg.adminToken))) return send(res, 403, { error: 'admin token required' });
      if (p === '/admin/sessions') {
        const out = [];
        for (const id of await store.list()) {
          try {
            const meta = await store.meta(id);
            out.push({ id, cohort: meta.cohort, consented_at: meta.consented_at, ended_at: meta.ended_at || null, bytes: await store.size(id) });
          } catch { /* half-written session */ }
        }
        return send(res, 200, out);
      }
      const am = p.match(/^\/admin\/session\/([a-f0-9]{32})$/);
      if (am && (await store.exists(am[1]))) {
        const files = {};
        for (const f of ['meta.json', 'device.json', 'end.json', 'events.ndjson', 'recaptcha.ndjson']) files[f] = await store.readFile(am[1], f);
        return send(res, 200, files);
      }
      return send(res, 404, { error: 'not found' });
    }

    if (req.method === 'GET') return serveStatic(req, res, url);
    return send(res, 404, 'Not found');
  }

  const handler = (req, res) => handle(req, res).catch(e => {
    if (!res.headersSent) send(res, e.status || 500, { error: e.status ? e.message : 'server error' });
    if (!e.status) console.error('[social-lab]', e);
  });

  return { handler, store, sink, sweep, upload };
}

export async function start(cfg) {
  if (!cfg.dev && !cfg.contact) {
    throw new Error('STUDY_CONTACT is not set. The consent page must name who to contact; set it in .env (or DEV=1 for local testing).');
  }
  const app = createApp(cfg);
  if (app.sink) {
    await app.sink.check();
    // Sessions left on disk by an earlier run (where the disk survives).
    app.sweep(true).catch(() => {});
    setInterval(() => app.sweep().catch(e => console.error('[social-lab] sweep:', e.message)), 60_000).unref();
  }
  let server;
  if (cfg.tlsCert && cfg.tlsKey) {
    // TLS is terminated here rather than by https.createServer, because the
    // ClientHello has to be read before the handshake consumes it. Each raw
    // TCP socket is read until the ClientHello is complete; then a stream that
    // replays those bytes and forwards the rest is wrapped in a TLSSocket and
    // handed to a plain HTTP server. (unshift() would not work: a TLSSocket
    // over a net.Socket reads the native handle and never sees JS-buffered
    // bytes.) The fingerprint and peer address ride on the TLSSocket as .sl,
    // so every request can see the ClientHello of its own connection.
    const secureContext = tls.createSecureContext({ cert: readFileSync(cfg.tlsCert), key: readFileSync(cfg.tlsKey) });
    const httpServer = http.createServer(app.handler);
    server = net.createServer(sock => {
      sock.on('error', () => {});
      sock.setTimeout(30_000, () => sock.destroy());
      let buf = Buffer.alloc(0);
      const onData = chunk => {
        buf = Buffer.concat([buf, chunk]);
        const { done, hello } = extractClientHello(buf);
        if (!done) return;
        sock.removeListener('data', onData);
        sock.pause();
        let fp = { status: 'unparsed' };
        if (hello) { try { fp = { status: 'ok', ...fingerprintHello(hello) }; } catch { /* keep 'unparsed' */ } }
        const replay = new Duplex({
          read() { sock.resume(); },
          write(chunk, _enc, cb) { sock.write(chunk, cb); },
          final(cb) { sock.end(); cb(); },
          destroy(err, cb) { sock.destroy(); cb(err); },
        });
        replay.push(buf);
        sock.on('data', c => { if (!replay.push(c)) sock.pause(); });
        sock.on('end', () => replay.push(null));
        sock.on('close', () => replay.destroy());
        const secure = new tls.TLSSocket(replay, { isServer: true, secureContext, ALPNProtocols: ['http/1.1'] });
        secure.sl = { remoteAddress: sock.remoteAddress, remotePort: sock.remotePort, tls: fp };
        secure.on('error', () => sock.destroy());
        httpServer.emit('connection', secure);
      };
      sock.on('data', onData);
    });
    if (cfg.httpRedirectPort) {
      http.createServer((req, res) => {
        const host = (req.headers.host || '').replace(/:\d+$/, '');
        res.writeHead(301, { location: `https://${host}${cfg.port === 443 ? '' : ':' + cfg.port}${req.url}` }); res.end();
      }).listen(cfg.httpRedirectPort, cfg.host);
    }
  } else {
    server = http.createServer(app.handler);
  }
  await new Promise(r => server.listen(cfg.port, cfg.host, r));
  const scheme = cfg.tlsCert ? 'https' : 'http';
  console.log(`Social Lab ${STUDY_VERSION} on ${scheme}://${cfg.host === '0.0.0.0' ? 'localhost' : cfg.host}:${cfg.port}`);
  console.log(`  data: ${cfg.dataDir}`);
  console.log(`  TLS fingerprints: ${cfg.tlsCert ? 'on' : 'off (no TLS_CERT)'} | reCAPTCHA: ${cfg.recaptchaSecret ? 'on' : 'off'} | WebRTC check: ${cfg.webrtc ? 'on' : 'off'} | IP lookup: ${cfg.ipLookup ? 'on' : 'off'}${cfg.trustProxy ? ' | behind proxy' : ''}${cfg.dev ? ' | DEV' : ''}`);
  console.log(`  storage: ${app.sink ? `sealed sessions -> github.com/${cfg.dataRepo} (local copies removed after upload)` : 'local disk only'}`);

  // On SIGTERM (a redeploy or restart), stop taking requests and move every
  // session still on disk to the repository before the container goes away.
  let stopping = false;
  const shutdown = async signal => {
    if (stopping) return;
    stopping = true;
    console.log(`[social-lab] ${signal}: uploading pending sessions`);
    server.close();
    const n = await app.sweep(true).catch(() => 0);
    console.log(`[social-lab] uploaded ${n} session(s), exiting`);
    process.exit(0);
  };
  process.once('SIGTERM', () => shutdown('SIGTERM'));
  process.once('SIGINT', () => shutdown('SIGINT'));
  return { server, app };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // --dev works the same in every shell (an inline DEV=1 does not in PowerShell).
  if (process.argv.includes('--dev')) process.env.DEV = '1';
  loadEnv(path.join(ROOT, '.env'));
  // exitCode rather than exit(): exiting while a fetch is still closing can
  // abort Node on Windows. Nothing else keeps the process alive at this point.
  start(config()).catch(e => { console.error('[social-lab] cannot start: ' + e.message); process.exitCode = 1; });
}
