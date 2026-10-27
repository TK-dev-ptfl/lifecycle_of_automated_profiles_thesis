// Session storage: one folder per session, append-only files.
//
// data/sessions/<id>/
//   meta.json        consent, cohort, network signals, timestamps (rewritten on end)
//   events.ndjson    one line per uploaded batch: { seq, recv, sent, events: [...] }
//   device.json      the device snapshot (written once)
//   recaptcha.ndjson one line per verified reCAPTCHA token
//   end.json         post-session questionnaire and task completion
//
// Plain files on purpose: nothing to install, trivially copied off a server
// with scp/rsync, and each session can be deleted by removing one folder,
// which is what a participant's deletion request needs.

import { mkdir, writeFile, appendFile, readFile, rm, readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { createHash, randomBytes } from 'node:crypto';

export const SESSION_ID = /^[a-f0-9]{32}$/;

export class Store {
  constructor(root) {
    this.root = path.resolve(root);
    this.sessions = path.join(this.root, 'sessions');
  }

  async init() { await mkdir(this.sessions, { recursive: true }); }

  dir(id) {
    if (!SESSION_ID.test(id)) throw new Error('bad session id');
    return path.join(this.sessions, id);
  }

  async create(meta) {
    const id = randomBytes(16).toString('hex');
    // Shown to the participant at the end; only its hash is kept, so the
    // data alone cannot be used to find the code.
    const deletionCode = randomBytes(6).toString('base64url').toUpperCase().replace(/[-_]/g, 'X');
    const writeToken = randomBytes(24).toString('base64url');
    await mkdir(this.dir(id), { recursive: true });
    await this.writeJSON(id, 'meta.json', {
      ...meta, id,
      deletion_code_sha256: hashCode(deletionCode),
      write_token_sha256: hashCode(writeToken),
      bytes: 0,
    });
    return { id, deletionCode, writeToken };
  }

  async exists(id) { return SESSION_ID.test(id) && existsSync(this.dir(id)); }
  async meta(id) { return JSON.parse(await readFile(path.join(this.dir(id), 'meta.json'), 'utf8')); }
  async writeJSON(id, name, obj) { await writeFile(path.join(this.dir(id), name), JSON.stringify(obj, null, 1)); }
  async append(id, name, obj) {
    const line = JSON.stringify(obj) + '\n';
    await appendFile(path.join(this.dir(id), name), line);
    return Buffer.byteLength(line);
  }
  async size(id) {
    let total = 0;
    for (const f of await readdir(this.dir(id))) total += (await stat(path.join(this.dir(id), f))).size;
    return total;
  }

  async checkToken(id, token) {
    if (!token || !(await this.exists(id))) return false;
    return (await this.meta(id)).write_token_sha256 === hashCode(token);
  }

  async deleteByCode(code) {
    const h = hashCode(String(code || '').trim().toUpperCase());
    for (const id of await this.list()) {
      try { if ((await this.meta(id)).deletion_code_sha256 === h) { await this.remove(id); return id; } } catch { /* skip */ }
    }
    return null;
  }

  /** Every file of a session as text, for sealing and upload. */
  async bundle(id) {
    const files = {};
    for (const f of await readdir(this.dir(id))) files[f] = await readFile(path.join(this.dir(id), f), 'utf8');
    return { format: 'social-lab-session-1', id, files };
  }

  /** Time of the latest write to any of the session's files. */
  async lastActivity(id) {
    let latest = 0;
    for (const f of await readdir(this.dir(id))) latest = Math.max(latest, (await stat(path.join(this.dir(id), f))).mtimeMs);
    return latest;
  }

  async remove(id) { await rm(this.dir(id), { recursive: true, force: true }); }
  async list() {
    if (!existsSync(this.sessions)) return [];
    return (await readdir(this.sessions)).filter(n => SESSION_ID.test(n));
  }
  async readFile(id, name) { return readFile(path.join(this.dir(id), name), 'utf8').catch(() => null); }
}

export const hashCode = s => createHash('sha256').update(String(s)).digest('hex');
