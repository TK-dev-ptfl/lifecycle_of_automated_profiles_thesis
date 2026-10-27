// TLS ClientHello parsing and the JA4 / JA3 fingerprints computed from it.
//
// What it tells: which TLS library opened the connection. Real Chrome, real
// Firefox and real Safari each send a characteristic set of cipher suites,
// extensions and signature algorithms; Python requests, curl, Go's net/http
// and Node send different ones. A client that claims "Chrome" in its User-Agent
// but negotiates TLS like Python is lying about what it is (thesis 2.4.2;
// docs/DATA_DICTIONARY.md, section "Network").
//
// JA4 follows the FoxIO specification exactly
// (https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md, BSD-3):
// GREASE removed everywhere, ciphers and extensions sorted before hashing, so
// Chrome's per-connection extension shuffling does not change the result.
// JA3 (Salesforce, 2017) is computed as well because much existing data uses
// it; unlike JA4 it changes per connection for Chrome >= 110, which is itself
// a property worth recording.

import { createHash } from 'node:crypto';

const isGrease = v => (v & 0x0f0f) === 0x0a0a && (v >> 8) === (v & 0xff);
const hex4 = v => v.toString(16).padStart(4, '0');
const sha12 = s => createHash('sha256').update(s).digest('hex').slice(0, 12);

const VERSION_CODE = {
  0x0304: '13', 0x0303: '12', 0x0302: '11', 0x0301: '10', 0x0300: 's3', 0x0002: 's2',
  0xfeff: 'd1', 0xfefd: 'd2', 0xfefc: 'd3',
};

/**
 * Collects a complete ClientHello handshake message from the first bytes of a
 * connection. Returns { done: false } until enough bytes arrived, then
 * { done: true, hello: Buffer|null } - null when the connection is not TLS
 * (e.g. plain HTTP sent to the TLS port) or is malformed.
 */
export function extractClientHello(buf) {
  if (buf.length < 1) return { done: false };
  if (buf[0] !== 0x16) return { done: true, hello: null };
  const parts = [];
  let off = 0, need = null, have = 0;
  while (off + 5 <= buf.length) {
    if (buf[off] !== 0x16) return { done: true, hello: null };
    const len = buf.readUInt16BE(off + 3);
    if (off + 5 + len > buf.length) return { done: false };
    parts.push(buf.subarray(off + 5, off + 5 + len));
    have += len;
    off += 5 + len;
    if (need === null && have >= 4) {
      const hs = Buffer.concat(parts);
      if (hs[0] !== 0x01) return { done: true, hello: null };
      need = 4 + hs.readUIntBE(1, 3);
    }
    if (need !== null && have >= need) return { done: true, hello: Buffer.concat(parts).subarray(0, need) };
  }
  if (buf.length > 64 * 1024) return { done: true, hello: null };
  return { done: false };
}

/** Parses a ClientHello handshake message (type 0x01 header included). */
export function parseClientHello(hs) {
  let p = 4;
  const u8 = () => hs[p++];
  const u16 = () => { const v = hs.readUInt16BE(p); p += 2; return v; };
  const legacyVersion = u16();
  p += 32;                       // random
  const sessionIdLen = u8();     // (not 'p += u8()': p would be read before u8 advances it)
  p += sessionIdLen;
  const cipherLen = u16();
  const ciphers = [];
  for (const end = p + cipherLen; p < end;) ciphers.push(u16());
  const compressionLen = u8();
  p += compressionLen;
  const extensions = [];
  const out = { legacyVersion, ciphers, extensions, sni: null, alpn: [], supportedVersions: [], sigAlgs: [], groups: [], pointFormats: [] };
  if (p + 2 > hs.length) return out;
  const extEnd = p + 2 + u16();
  while (p + 4 <= extEnd) {
    const type = u16(), len = u16(), body = hs.subarray(p, p + len);
    p += len;
    extensions.push(type);
    try {
      if (type === 0x0000 && len >= 5) out.sni = body.subarray(5, 5 + body.readUInt16BE(3)).toString('latin1');
      else if (type === 0x0010 && len >= 2) {
        for (let q = 2; q < 2 + body.readUInt16BE(0);) { const l = body[q]; out.alpn.push(body.subarray(q + 1, q + 1 + l)); q += 1 + l; }
      } else if (type === 0x002b && len >= 1) {
        for (let q = 1; q < 1 + body[0]; q += 2) out.supportedVersions.push(body.readUInt16BE(q));
      } else if (type === 0x000d && len >= 2) {
        for (let q = 2; q < 2 + body.readUInt16BE(0); q += 2) out.sigAlgs.push(body.readUInt16BE(q));
      } else if (type === 0x000a && len >= 2) {
        for (let q = 2; q < 2 + body.readUInt16BE(0); q += 2) out.groups.push(body.readUInt16BE(q));
      } else if (type === 0x000b && len >= 1) {
        for (let q = 1; q < 1 + body[0]; q++) out.pointFormats.push(body[q]);
      }
    } catch { /* a malformed extension body leaves that field empty */ }
  }
  return out;
}

function alpnCode(alpn) {
  const first = alpn[0];
  if (!first || first.length === 0) return '00';
  const alnum = b => (b >= 0x30 && b <= 0x39) || (b >= 0x41 && b <= 0x5a) || (b >= 0x61 && b <= 0x7a);
  const a = first[0], z = first[first.length - 1];
  if (alnum(a) && alnum(z)) return String.fromCharCode(a) + String.fromCharCode(z);
  const h = first.toString('hex');
  return h[0] + h[h.length - 1];
}

/** JA4 for a parsed ClientHello over TCP. Returns the fingerprint and the raw
 *  (pre-hash) strings, which are what an analysis can compare field by field. */
export function ja4(ch) {
  const versions = ch.supportedVersions.filter(v => !isGrease(v));
  const version = VERSION_CODE[versions.length ? Math.max(...versions) : ch.legacyVersion] || '00';
  const ciphers = ch.ciphers.filter(v => !isGrease(v));
  const exts = ch.extensions.filter(v => !isGrease(v));
  const count = n => String(Math.min(n, 99)).padStart(2, '0');
  const a = `t${version}${ch.sni !== null || exts.includes(0) ? 'd' : 'i'}${count(ciphers.length)}${count(exts.length)}${alpnCode(ch.alpn)}`;

  const cipherStr = ciphers.map(hex4).sort().join(',');
  const extStr = exts.filter(v => v !== 0x0000 && v !== 0x0010).map(hex4).sort().join(',');
  const sigStr = ch.sigAlgs.filter(v => !isGrease(v)).map(hex4).join(',');
  const cRaw = sigStr ? `${extStr}_${sigStr}` : extStr;
  const b = ciphers.length ? sha12(cipherStr) : '000000000000';
  const c = extStr ? sha12(cRaw) : '000000000000';
  return { ja4: `${a}_${b}_${c}`, ja4_r: `${a}_${cipherStr}_${cRaw}` };
}

/** JA3: version,ciphers,extensions,groups,point formats in the order sent,
 *  GREASE removed, MD5. */
export function ja3(ch) {
  const ng = a => a.filter(v => !isGrease(v));
  const raw = [ch.legacyVersion, ng(ch.ciphers).join('-'), ng(ch.extensions).join('-'),
    ng(ch.groups).join('-'), ch.pointFormats.join('-')].join(',');
  return { ja3: createHash('md5').update(raw).digest('hex'), ja3_r: raw };
}

/** Everything recorded about one TLS connection. */
export function fingerprintHello(hello) {
  const ch = parseClientHello(hello);
  return {
    ...ja4(ch),
    ...ja3(ch),
    alpn: ch.alpn.map(b => b.toString('latin1')),
    tls_versions: ch.supportedVersions.filter(v => !isGrease(v)).map(hex4),
    grease: ch.ciphers.some(isGrease) || ch.extensions.some(isGrease),
    sni_present: ch.sni !== null,
  };
}

export const _internal = { isGrease, sha12, alpnCode };
