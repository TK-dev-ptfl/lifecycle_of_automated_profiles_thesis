// Hearth feed lab server. Node 18+, no dependencies.
// Serves index.html with your site key filled in, and verifies tokens server-side.
// Reads keys from .env next to this file (see .env.example).
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const dir = path.dirname(fileURLToPath(import.meta.url));

// Load .env next to this file, if there is one. Done here rather than relying on
// `node --env-file` so plain `node server.mjs` works on any Node 18+, and so the
// keys live in a gitignored file instead of your shell history. Real environment
// variables still win, which is what makes a one-off override possible.
function loadEnvFile(file) {
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    // Strip one layer of matching quotes, so a value with spaces can be quoted.
    if (value.length > 1 && value[0] === value.at(-1) && (value[0] === '"' || value[0] === "'")) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = value;
  }
}
loadEnvFile(path.join(dir, '.env'));

const {
  // Loopback by default: this is a local lab, and binding every interface would
  // put it on the network for anyone on the same Wi-Fi. Set HOST=0.0.0.0 if you
  // deliberately want to reach it from another device.
  HOST = '127.0.0.1',
  PORT = 8080,
  RECAPTCHA_SITE_KEY = '', RECAPTCHA_SECRET = ''
} = process.env;

const json = (res, code, obj) => {
  res.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  res.end(JSON.stringify(obj));
};
const clientIp = req =>
  (req.headers['cf-connecting-ip'] || (req.headers['x-forwarded-for'] || '').split(',')[0] || req.socket.remoteAddress || '').trim();

async function readBody(req) {
  let data = '';
  for await (const chunk of req) {
    data += chunk;
    if (data.length > 100_000) throw new Error('body-too-large');
  }
  return JSON.parse(data || '{}');
}

async function siteverify(url, secret, token, ip) {
  const r = await fetch(url, {
    method: 'POST',
    body: new URLSearchParams({ secret, response: String(token || ''), remoteip: ip })
  });
  return r.json();
}

http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');

    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      let html = await readFile(path.join(dir, 'index.html'), 'utf8');
      if (RECAPTCHA_SITE_KEY) html = html.replace('__RECAPTCHA_SITE_KEY__', () => RECAPTCHA_SITE_KEY);
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
      return res.end(html);
    }

    if (req.method === 'POST' && url.pathname === '/verify/recaptcha') {
      if (!RECAPTCHA_SECRET) return json(res, 501, { success: false, 'error-codes': ['server-missing-RECAPTCHA_SECRET'] });
      const { token, action } = await readBody(req);
      const result = await siteverify('https://www.google.com/recaptcha/api/siteverify', RECAPTCHA_SECRET, token, clientIp(req));
      // result: { success, score (0.0 bot … 1.0 human), action, challenge_ts, hostname, error-codes }
      if (result.success && action && result.action !== action) result['error-codes'] = ['action-mismatch'];
      console.log(`[recaptcha] action=${result.action} score=${result.score} success=${result.success}`);
      return json(res, 200, result);
    }

    res.writeHead(404, { 'content-type': 'text/plain' });
    res.end('Not found');
  } catch (e) {
    json(res, 500, { success: false, 'error-codes': [String(e.message || e)] });
  }
}).listen(PORT, HOST, () => {
  console.log(`Hearth feed lab on http://${HOST === '0.0.0.0' ? 'localhost' : HOST}:${PORT}`);
  console.log(`reCAPTCHA v3: ${RECAPTCHA_SITE_KEY && RECAPTCHA_SECRET ? 'on' : 'off'}`);
});
