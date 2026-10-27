// Creates the key pair that protects collected sessions.
//
//   node analysis/keygen.mjs [--out <path to private key>]
//
// The private key is written to your home folder by default, outside the
// repository, readable only by you. Keep a backup of it (e.g. in a password
// manager): without it no collected session can ever be read again.
// The public key is printed as one base64 line: paste it into Railway as
// DATA_PUBLIC_KEY. The server can then encrypt sessions but never decrypt them.

import { writeFileSync, existsSync, mkdirSync, chmodSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { generateKeys } from '../server/seal.mjs';

const i = process.argv.indexOf('--out');
const out = path.resolve(i > 0 ? process.argv[i + 1] : path.join(homedir(), '.social-lab', 'private-key.pem'));
if (existsSync(out)) {
  console.error(`${out} already exists. Refusing to overwrite: sessions encrypted for it would become unreadable.`);
  process.exit(1);
}
const { publicKey, privateKey } = generateKeys();
mkdirSync(path.dirname(out), { recursive: true });
writeFileSync(out, privateKey, { mode: 0o600 });
try { chmodSync(out, 0o600); } catch { /* Windows: rely on the user folder's permissions */ }
writeFileSync(out.replace(/\.pem$/, '') + '.pub.pem', publicKey);

console.log(`Private key: ${out}`);
console.log('  Keep it secret, never commit it, and back it up. Without it the data cannot be read.\n');
console.log('DATA_PUBLIC_KEY (paste into Railway as one line):\n');
console.log(Buffer.from(publicKey).toString('base64'));
