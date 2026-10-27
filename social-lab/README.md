# Social Lab

A dummy social network, **Hearth**, for collecting data on how real people use a
social feed. It records how they move the pointer, type, scroll, read and engage, and
what their browser, machine and connection reveal. Everything is on a documented
scientific basis and gathered only with consent. The data calibrates the thesis's
behaviour algorithm and measures how well bot-detection signals separate people from
bots.

It is **separate from the rest of the repository**: nothing here imports from
`backend/` or `frontend/`, and they do not import from here. Exchange happens through
files (`analysis/export.mjs`).

| Document | Content |
|---|---|
| [docs/STUDY.md](docs/STUDY.md) | Why: research questions, what each one calibrates, study design, sample size, ethics. **Read first.** |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | What: every recorded field, what it tells, which question it serves, and what is deliberately not collected |
| [docs/ANALYSIS.md](docs/ANALYSIS.md) | How: the exact definition of every derived measurement |
| [docs/REFERENCES.md](docs/REFERENCES.md) | The studies and specifications behind each measurement ([references.bib](docs/references.bib)) |

## Requirements

Node.js 22 or newer. No `npm install`: there are no dependencies.

## Run locally

```bash
cd social-lab
cp .env.example .env          # optional for local runs
npm run dev                   # DEV=1: no contact required, no per-network limit
# open http://127.0.0.1:8090
```

Without reCAPTCHA keys the site works and that signal is simply absent. Without TLS
there are no TLS fingerprints.

## Test

```bash
npm test
```

The tests cover:
- JA4 against the FoxIO specification's test vectors and a real ClientHello;
- every analysis definition on synthetic sessions with known answers (e.g. a
  minimum-jerk movement must peak at its midpoint);
- the server's guarantees: no session without consent, no write without the session
  token, deletion and withdrawal really delete, cohorts cannot be self-assigned, no
  IP stored, nothing outside `public/` served.

## Deploy for data collection

Two step-by-step guides:

| Guide | Hosting | Data storage | TLS fingerprints | Effort |
|---|---|---|---|---|
| **[deploy/DEPLOY_RAILWAY.md](deploy/DEPLOY_RAILWAY.md)** | Railway, deployed from GitHub; free plan ($1/month credit) | encrypted, in a private GitHub repo | no (Railway's edge terminates TLS) | ~45 min, no server admin |
| [deploy/DEPLOY.md](deploy/DEPLOY.md) | Oracle Cloud Always Free VM + DuckDNS + Let's Encrypt | on the VM | yes | 1–2 h, a Linux server to run |

The summary below is the general shape of the VM setup.

1. **A VPS with a domain** pointing to it. The server should terminate TLS itself, so
   it sees the TLS ClientHello (RQ-N1):
   ```bash
   sudo certbot certonly --standalone -d study.example.org
   ```
2. **`.env`**:
   ```
   STUDY_RESEARCHER=...
   STUDY_INSTITUTION=...
   STUDY_CONTACT=you@example.org          # required; the server refuses to start without it
   HOST=0.0.0.0
   PORT=443
   HTTP_REDIRECT_PORT=80
   TLS_CERT=/etc/letsencrypt/live/study.example.org/fullchain.pem
   TLS_KEY=/etc/letsencrypt/live/study.example.org/privkey.pem
   RECAPTCHA_SITE_KEY=...                 # score-based v3, domain registered
   RECAPTCHA_SECRET=...
   ADMIN_TOKEN=<long random string>
   COHORT_KEY=<another long random string>
   ```
   Binding to 443 needs privileges: run as a service with
   `AmbientCapabilities=CAP_NET_BIND_SERVICE`, or use port 8443 and a firewall
   redirect.
3. **Behind a CDN or reverse proxy instead?** Leave `TLS_*` empty and set
   `TRUST_PROXY=1`. Everything works except TLS fingerprints, which the proxy
   consumes.
4. **Before sharing the link,** go through the ethics checklist in
   [docs/STUDY.md](docs/STUDY.md).

## Run bots against it

A bot session is labelled as its own cohort by opening the site with the cohort key:

```
https://study.example.org/?cohort=behaviour-v3&key=<COHORT_KEY>&run=identity-7
```

It then goes through the same consent, phases and tasks as a person. Without a valid
key the label is refused (403), so participants cannot mislabel themselves.

## Get the data and analyse it

With the Railway setup, sessions arrive encrypted in the private data repo instead:

```bash
npm run keygen                                         # once: key pair; private key stays on your PC
git clone https://github.com/<you>/<data repo> ../../social-lab-data   # then: git -C ../../social-lab-data pull
npm run decrypt -- --in ../../social-lab-data          # -> data-remote/ (rebuilt each time; deletions propagate)
npm run analyze -- --data data-remote
```

On your own server:

```bash
# list or download from the server
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://study.example.org/admin/sessions
rsync -a server:/path/to/social-lab/data/ ./data/      # or copy the folder

npm run analyze                            # -> analysis/out/{sessions,strokes,clicks,posts}.csv, summary.md
node analysis/analyze.mjs --device any     # human reference over all input devices
node analysis/export.mjs --format sapimouse --cohort human   # SapiMouse-format CSVs
node analysis/export.mjs --format trace                       # input traces in the feed-lab layout
```

`data/`, `data-remote/` and `analysis/out/` are gitignored. They contain personal data; never commit
them.

## Layout

```
server/
  server.mjs            HTTP(S) server, API, consent gate, TLS termination
  tls-fingerprint.mjs   ClientHello parser, JA4, JA3
  network.mjs           header order, network type, daily IP hash, WebRTC check
  store.mjs             one folder per session, deletion by code
  seal.mjs              hybrid encryption (RSA-OAEP + AES-256-GCM) of sessions before they leave the server
  github-sink.mjs       uploads sealed sessions to the private data repo; deletes by code
public/
  index.html            consent, feed, questionnaire, debrief
  css/app.css
  js/main.js            study flow and tasks
  js/content.js         seeded synthetic feed
  js/feed.js            the network: rendering, interactions, exposure (it, ly, iv, act)
  js/recorder.js        input recording and upload
  js/device.js          device snapshot and consistency checks
  js/probe-worker.js    worker-side snapshot
  js/captcha.js         reCAPTCHA v3
  js/webrtc.js          optional WebRTC address check
  vendor/botd/          FingerprintJS BotD 2.0.0 (MIT)
analysis/
  stats.mjs             quantiles, OLS, AUC, burstiness
  metrics.mjs           every per-session measurement
  analyze.mjs           tables and summary
  export.mjs            SapiMouse and trace exports
  keygen.mjs            creates the key pair (npm run keygen)
  decrypt.mjs           data repo clone -> data-remote/ (npm run decrypt)
deploy/                 DEPLOY_RAILWAY.md, DEPLOY.md (VM), systemd unit, certificate hook
Dockerfile, railway.json  container and Railway configuration
test/                   node --test suites
```
