// Moves finished sessions off the server into a private GitHub repository,
// sealed (seal.mjs) so the repository only ever holds ciphertext.
//
// Why: on a host with no persistent disk (Railway's free plan), the container's
// files disappear on every restart. A session therefore lives on local disk
// only while it is being recorded, and is uploaded - then removed locally -
// when it ends, when it is abandoned (no writes for IDLE_MS), or when the
// server is told to shut down.
//
// One file per session, named by the hash of its deletion code:
//   sessions/<first 2 hex>/<sha256(code)>.sle
// so a deletion request can find and delete the file without anything in the
// repository linking it to a person, and without the server being able to
// read it. Removing a file leaves it in the repository's history (as
// ciphertext); DEPLOY_RAILWAY.md describes purging the history.
//
// Uses the GitHub REST "contents" API with a fine-grained token limited to
// that one repository (Contents: read and write).

import zlib from 'node:zlib';
import { seal } from './seal.mjs';


export class GitHubSink {
  constructor({ repo, token, branch = 'main', publicKey, api = 'https://api.github.com', fetch = globalThis.fetch, log = console.log }) {
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo || '')) throw new Error('DATA_REPO must look like owner/name');
    if (!token) throw new Error('DATA_REPO_TOKEN is required with DATA_REPO');
    if (!publicKey) throw new Error('DATA_PUBLIC_KEY is required with DATA_REPO: sessions are never uploaded unencrypted');
    Object.assign(this, { repo, token, branch, publicKey, api: api.replace(/\/$/, ''), fetch, log });
  }

  static pathFor(deletionCodeHash) {
    if (!/^[a-f0-9]{64}$/.test(deletionCodeHash)) throw new Error('bad hash');
    return `sessions/${deletionCodeHash.slice(0, 2)}/${deletionCodeHash}.sle`;
  }

  async call(method, path, body) {
    const r = await this.fetch(`${this.api}/repos/${this.repo}/contents/${path}${method === 'GET' ? `?ref=${encodeURIComponent(this.branch)}` : ''}`, {
      method,
      headers: { authorization: `Bearer ${this.token}`, accept: 'application/vnd.github+json', 'x-github-api-version': '2022-11-28',
        'user-agent': 'social-lab', ...(body ? { 'content-type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30_000),
    });
    const json = await r.json().catch(() => ({}));
    return { status: r.status, json };
  }

  async sha(path) {
    const { status, json } = await this.call('GET', path);
    if (status === 404) return null;
    if (status !== 200) throw new Error(`GitHub GET ${status}: ${json.message || ''}`);
    return json.sha;
  }

  /** Seals and uploads a session bundle ({ files: { name: text } }). */
  async upload(deletionCodeHash, bundle) {
    const path = GitHubSink.pathFor(deletionCodeHash);
    const sealed = seal(zlib.gzipSync(JSON.stringify(bundle)), this.publicKey);
    const sha = await this.sha(path);
    // The commit message says nothing about the session: commit metadata is
    // not encrypted.
    const { status, json } = await this.call('PUT', path, { message: 'session', content: sealed.toString('base64'), branch: this.branch, ...(sha ? { sha } : {}) });
    if (status !== 200 && status !== 201) throw new Error(`GitHub PUT ${status}: ${json.message || ''}`);
    return path;
  }

  /** Deletes the session stored for this deletion-code hash. False if none. */
  async remove(deletionCodeHash) {
    const path = GitHubSink.pathFor(deletionCodeHash);
    const sha = await this.sha(path);
    if (!sha) return false;
    const { status, json } = await this.call('DELETE', path, { message: 'delete', sha, branch: this.branch });
    if (status !== 200) throw new Error(`GitHub DELETE ${status}: ${json.message || ''}`);
    return true;
  }

  /** Checks the token can see the repository, at start-up. */
  async check() {
    const r = await this.fetch(`${this.api}/repos/${this.repo}`, {
      headers: { authorization: `Bearer ${this.token}`, accept: 'application/vnd.github+json', 'user-agent': 'social-lab' },
      signal: AbortSignal.timeout(15_000),
    });
    const j = await r.json().catch(() => ({}));
    if (r.status !== 200) throw new Error(`DATA_REPO ${this.repo} not reachable with this token (HTTP ${r.status}: ${j.message || ''})`);
    if (!j.private) throw new Error(`DATA_REPO ${this.repo} is public. Collected data must go to a private repository.`);
    if (j.permissions && !j.permissions.push) throw new Error(`the token cannot write to ${this.repo}`);
    return true;
  }
}
