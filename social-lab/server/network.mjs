// Network signals about a request, collected server-side.
//
// Nothing here stores an IP address. The address is used, while the request
// is being handled, for three things and then dropped:
//   1. a lookup of what kind of network it belongs to (country, time zone,
//      autonomous system, hosting / proxy / mobile flags),
//   2. a keyed hash that only lets us count repeat sessions from the same
//      address on the same day (the key changes daily and is never written),
//   3. the WebRTC comparison (see webrtcMatches).
// See docs/DATA_DICTIONARY.md, section "Network", for what each one tells.

import { createHmac, randomBytes } from 'node:crypto';
import net from 'node:net';

// Request headers whose values are recorded. Everything else is recorded by
// name and position only. These are the ones that differ systematically
// between real browsers and HTTP libraries, and carry no personal content.
const VALUE_HEADERS = new Set([
  'user-agent', 'accept', 'accept-language', 'accept-encoding', 'connection', 'upgrade-insecure-requests',
  'sec-ch-ua', 'sec-ch-ua-mobile', 'sec-ch-ua-platform', 'sec-fetch-site', 'sec-fetch-mode', 'sec-fetch-dest',
  'sec-fetch-user', 'sec-gpc', 'dnt', 'priority', 'cache-control', 'pragma', 'te', 'content-type', 'origin',
]);

/** Header names in the order the client sent them, plus whitelisted values.
 *  Order and capitalisation are a property of the HTTP stack, not the user. */
export function headerSignals(req) {
  const order = [], values = {};
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i], lower = name.toLowerCase();
    order.push(name);
    if (VALUE_HEADERS.has(lower)) values[lower] = req.rawHeaders[i + 1].slice(0, 400);
  }
  return { http_version: req.httpVersion, order, values };
}

export function clientIp(req, trustProxy) {
  let ip = req.socket.sl?.remoteAddress || req.socket.remoteAddress || '';
  // Railway reports the client in X-Real-IP; most other proxies in X-Forwarded-For.
  if (trustProxy) ip = String(req.headers['x-real-ip'] || req.headers['x-forwarded-for'] || ip).split(',')[0].trim();
  return ip.replace(/^::ffff:/, '');
}

const isPrivate = ip => {
  if (!net.isIP(ip)) return true;
  return /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|::1$|fc|fd|fe80)/i.test(ip);
};

// One key per UTC day, held in memory only. Restarting the server mid-day
// starts a new key, which can only under-count repeats - never link days.
let dayKey = { day: '', key: null };
export function dailyIpHash(ip) {
  const day = new Date().toISOString().slice(0, 10);
  if (dayKey.day !== day) dayKey = { day, key: randomBytes(32) };
  return createHmac('sha256', dayKey.key).update(ip).digest('hex').slice(0, 16);
}

const lookupCache = new Map();
/** Network type of an address via ip-api.com (free tier: non-commercial use,
 *  45 requests/minute, HTTP only). Returns null on failure; the session goes
 *  ahead without it. */
export async function lookupNetwork(ip) {
  if (isPrivate(ip)) return { status: 'private-address' };
  const hit = lookupCache.get(ip);
  if (hit && hit.at > Date.now() - 3600_000) return hit.value;
  try {
    const r = await fetch(`http://ip-api.com/json/${encodeURIComponent(ip)}?fields=status,message,countryCode,timezone,as,isp,proxy,hosting,mobile`,
      { signal: AbortSignal.timeout(4000) });
    const j = await r.json();
    const value = j.status === 'success'
      ? { status: 'ok', country: j.countryCode, timezone: j.timezone, asn: (j.as || '').split(' ')[0], isp: j.isp,
          proxy: j.proxy, hosting: j.hosting, mobile: j.mobile }
      : { status: 'failed', message: j.message };
    lookupCache.set(ip, { at: Date.now(), value });
    if (lookupCache.size > 5000) lookupCache.delete(lookupCache.keys().next().value);
    return value;
  } catch (e) {
    return { status: 'error', message: String(e.message || e).slice(0, 100) };
  }
}

/** WebRTC check: the browser hashes the public addresses its STUN request
 *  discovered, salted with the session's salt; we hash the address the
 *  request came from the same way. A mismatch means traffic goes out one way
 *  (e.g. through a proxy) while WebRTC exposes another - the classic proxy
 *  leak. Only the boolean outcome is stored. */
export function webrtcMatches(salt, requestIp, candidateHashes) {
  const mine = createHmac('sha256', salt).update(requestIp).digest('hex');
  return { candidates: candidateHashes.length, matches_request_ip: candidateHashes.includes(mine) };
}
