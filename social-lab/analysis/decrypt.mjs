// Turns a clone of the private data repository back into session folders.
//
//   git clone https://github.com/<you>/<data repo>.git ../social-lab-data   (once; later: git -C ../social-lab-data pull)
//   node analysis/decrypt.mjs --in ../social-lab-data [--key <private key>] [--out data-remote]
//   node analysis/analyze.mjs --data data-remote
//
// The output folder is rebuilt from scratch on every run, so a session deleted
// from the repository (a participant's deletion request) disappears locally
// too. It is gitignored; it is personal data in plain text, so keep it on an
// encrypted disk.

import { readdir, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { open } from '../server/seal.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function sealedFiles(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    if (e.name === '.git') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...(await sealedFiles(p)));
    else if (e.name.endsWith('.sle')) out.push(p);
  }
  return out;
}

/** Decrypts every *.sle under inDir into outDir/sessions/<id>/. Returns counts. */
export async function decryptAll(inDir, outDir, privateKeyPem) {
  const sessions = path.join(outDir, 'sessions');
  await rm(sessions, { recursive: true, force: true });
  await mkdir(sessions, { recursive: true });
  let ok = 0; const failed = [];
  for (const file of await sealedFiles(inDir)) {
    try {
      const bundle = JSON.parse(zlib.gunzipSync(open(await readFile(file), privateKeyPem)).toString('utf8'));
      if (bundle.format !== 'social-lab-session-1' || !/^[a-f0-9]{32}$/.test(bundle.id)) throw new Error('unknown format');
      const dir = path.join(sessions, bundle.id);
      await mkdir(dir, { recursive: true });
      for (const [name, text] of Object.entries(bundle.files)) {
        if (!/^[\w.-]+$/.test(name)) continue;          // file names only, no paths
        await writeFile(path.join(dir, name), text);
      }
      ok++;
    } catch (e) { failed.push(`${path.relative(inDir, file)}: ${e.message}`); }
  }
  return { ok, failed };
}

async function main() {
  const arg = k => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
  const inDir = arg('--in');
  if (!inDir || !existsSync(inDir)) { console.log('usage: node analysis/decrypt.mjs --in <clone of the data repo> [--key <private key>] [--out data-remote]'); process.exit(2); }
  const keyPath = arg('--key') || path.join(homedir(), '.social-lab', 'private-key.pem');
  const outDir = path.resolve(ROOT, arg('--out') || 'data-remote');
  const { ok, failed } = await decryptAll(path.resolve(inDir), outDir, await readFile(keyPath, 'utf8'));
  console.log(`${ok} session(s) -> ${path.join(outDir, 'sessions')}`);
  for (const f of failed) console.log(`  could not open ${f}`);
  console.log(`next: node analysis/analyze.mjs --data ${path.relative(ROOT, outDir) || outDir}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(e => { console.error(e.message); process.exit(1); });
