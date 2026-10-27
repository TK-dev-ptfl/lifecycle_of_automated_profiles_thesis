// Encrypting a session for storage elsewhere (the GitHub data repository).
//
// Hybrid encryption with Node's built-in crypto: each session gets a fresh
// random AES-256-GCM key; that key is encrypted with the researcher's RSA
// public key (RSA-OAEP, SHA-256). The server holds only the public key, so it
// can seal sessions but cannot open them - nor can anyone who reads the
// repository, GitHub included. Only the private key, kept by the researcher
// off the server, opens them (analysis/decrypt.mjs).
//
// Format: "SLE1" | u16 wrapped-key length | wrapped key | 12-byte IV |
//         16-byte GCM tag | ciphertext.  GCM authenticates the ciphertext, so
//         a tampered or truncated file fails to open rather than decrypting
//         to garbage.

import { publicEncrypt, privateDecrypt, randomBytes, createCipheriv, createDecipheriv, constants, generateKeyPairSync, createPublicKey } from 'node:crypto';

const MAGIC = Buffer.from('SLE1');
const OAEP = { padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: 'sha256' };

/** Accepts a PEM, or a PEM encoded as base64 on one line (environment
 *  variables do not hold newlines well). */
export function readKey(text) {
  // Forgiving about how the value was pasted into a hosting dashboard:
  // surrounding quotes, a trailing "# comment", and line breaks or spaces
  // inside the base64 are all dropped.
  let t = String(text || '').trim().replace(/^(['"])([\s\S]*)\1$/, '$2').trim();
  if (!t) return null;
  if (t.includes('-----BEGIN')) return t.replace(/\\n/g, '\n');
  t = t.replace(/\s#.*$/s, '').replace(/\s+/g, '');
  return Buffer.from(t, 'base64').toString('utf8');
}

export function seal(plain, publicKeyPem) {
  const key = randomBytes(32), iv = randomBytes(12);
  const wrapped = publicEncrypt({ key: publicKeyPem, ...OAEP }, key);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  const body = Buffer.concat([cipher.update(plain), cipher.final()]);
  const len = Buffer.alloc(2); len.writeUInt16BE(wrapped.length);
  return Buffer.concat([MAGIC, len, wrapped, iv, cipher.getAuthTag(), body]);
}

export function open(sealed, privateKeyPem) {
  if (!sealed.subarray(0, 4).equals(MAGIC)) throw new Error('not a sealed session file');
  const n = sealed.readUInt16BE(4);
  let p = 6;
  const wrapped = sealed.subarray(p, p += n), iv = sealed.subarray(p, p += 12), tag = sealed.subarray(p, p += 16);
  const key = privateDecrypt({ key: privateKeyPem, ...OAEP }, wrapped);
  const d = createDecipheriv('aes-256-gcm', key, iv);
  d.setAuthTag(tag);
  return Buffer.concat([d.update(sealed.subarray(p)), d.final()]);
}

export function generateKeys() {
  return generateKeyPairSync('rsa', {
    modulusLength: 4096,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  });
}

/** Throws unless `pem` is a usable RSA public key, so a bad configuration
 *  stops the server at start instead of failing on the first upload. */
export function checkPublicKey(pem) {
  const k = createPublicKey(pem);
  if (k.asymmetricKeyType !== 'rsa') throw new Error('DATA_PUBLIC_KEY must be an RSA public key');
  return k;
}
