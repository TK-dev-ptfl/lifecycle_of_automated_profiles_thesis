# Deploying on Railway, with data saved to GitHub

Railway builds and runs `social-lab/` straight from your GitHub repository and
redeploys when you push changes to it. Railway's disk is wiped on every restart, so
finished sessions are **encrypted on the server and moved to a separate private
GitHub repository**.

About 30–45 minutes the first time. No server administration.

## How it fits together

```
participant ──https──▶ Railway edge ──▶ social-lab container (Node)
                                           │  while recording: local files
                                           │  on end / 30 min idle / shutdown:
                                           │    gzip → encrypt (your PUBLIC key) → upload
                                           ▼
                           github.com/<you>/social-lab-data   (PRIVATE, ciphertext only)
                                           │
               your PC: git pull → npm run decrypt (your PRIVATE key) → npm run analyze
```

- **Two repositories.** Your thesis repo is **public**: it holds the code, and Railway
  deploys from it. The data goes to a **separate private** repo. If data were
  committed to the code repo, every session would trigger a redeploy, and it would be
  public. The server refuses to start if the data repo is public.
- **The server can encrypt but never decrypt.** It holds only the public key. The
  private key stays on your PC. Anyone who gets into the data repo (GitHub included)
  sees only ciphertext.
- **Deletion codes keep working.** Each file is named by the hash of its deletion
  code, so the server can find and delete it without reading it.

## What you give up compared with your own server

- **No TLS fingerprints** (RQ-N1). Railway's edge handles TLS, so the browser's TLS
  handshake never reaches the app. Sessions record `behind_proxy: true`.
- **Header order** (RQ-N2) is Railway's, not the browser's. Treat it as unavailable.
- **Everything else is unaffected:** behaviour, device snapshot, reCAPTCHA, and the
  network type of the address (Railway passes the client address in `X-Real-IP`).

## Cost

- **Trial:** new accounts get a one-time $5 credit.
- **After the trial:** the **Free plan** gives $1 of usage a month, with up to 0.5 GB
  RAM and no persistent volumes; it does not need them.
- **Expected cost:** Railway bills RAM at $10 per GB per month and CPU at $20 per vCPU
  per month. This server idles at about 40 MB, roughly $0.40 a month of RAM plus a
  little CPU, so it should fit within $1. That is an estimate: check
  **Usage** in the Railway dashboard after a week.
- **If it doesn't fit,** Hobby costs $5 a month including $5 of usage.

Prices are from Railway's pricing page, October 2026.

---

## 1. Commit and push the code (PC)

`social-lab/` must be in your GitHub repo for Railway to deploy it. It contains no
secrets: those go into Railway's variables in step 5, and `.env`, `data/`,
`data-remote/` and keys are gitignored.

```powershell
cd C:\Users\<you>\Documents\lifecycle_of_automated_profiles_thesis
git status                              # check: no data/, .env or *.pem listed
git add social-lab
git commit -m "Social Lab: study site with encrypted GitHub storage"
git push
```

## 2. Create the private data repository (GitHub)

1. Go to **github.com/new**.
2. Name it, for example, `social-lab-data`.
3. Set it to **Private**.
4. Tick **Add a README file**. The repo needs at least one commit before the server
   can write to it.
5. Click **Create repository**.

Don't add collaborators. Anyone with read access can download the ciphertext,
although they cannot decrypt it.

## 3. Create a token that can write only to that repository (GitHub)

1. Go to **github.com/settings/personal-access-tokens/new** (a *fine-grained* token).
2. Fill it in:

   | Field | Value |
   |---|---|
   | Name | `social-lab-railway` |
   | Expiration | until the end of data collection; write the date down, since uploads stop when it expires |
   | Repository access | **Only select repositories** → `social-lab-data` |
   | Permissions | **Contents: Read and write**. Metadata becomes Read-only automatically. Nothing else. |

3. Click **Generate token** and copy it (`github_pat_…`). It is shown only once.

## 4. Create the encryption keys (PC)

```powershell
cd social-lab
npm run keygen
```

This writes your **private key** to `C:\Users\<you>\.social-lab\private-key.pem` and
prints a long one-line **public key**. Copy that line for step 5.

> **Back up the private key now**, e.g. as a secure note in a password manager.
> Without it, every collected session is unreadable for good. Never commit it, and
> never put it on Railway.

## 5. Create the Railway service (railway.com)

1. Sign in at **railway.com** with GitHub.
2. Choose **New Project → Deploy from GitHub repo**, and allow the Railway GitHub app
   access to the thesis repository.
3. Pick the **thesis** repository (`lifecycle_of_automated_profiles_thesis`), not
   the data repository: Railway never needs access to the data repository, the
   server writes there only with the token. Railway creates a service and starts a
   first build. It may fail until the settings below are in place; that's expected.
4. Open the service. Under **Settings**:
   - **Root Directory:** `/social-lab`
   - **Config file path** (Config-as-code): `/social-lab/railway.json`. This must be
     the path from the repo root. The file sets the Dockerfile build, the health
     check, a 30 s shutdown window, and **watch paths `/social-lab/**`**, so pushes
     that change only your thesis text or backend do not redeploy, and therefore do
     not interrupt, the study.
5. Under **Variables**, add these. Use the *Raw Editor* to paste them all at once.

   ```
   STUDY_RESEARCHER=Tomas Knepp
   STUDY_INSTITUTION=Comenius University Bratislava, Faculty of Mathematics, Physics and Informatics
   STUDY_CONTACT=your.address@uniba.sk
   DATA_REPO=TK-dev-ptfl/social-lab-data
   DATA_REPO_TOKEN=github_pat_...                 # step 3
   DATA_PUBLIC_KEY=LS0tLS1CRUdJTi...              # step 4, the whole line
   ADMIN_TOKEN=<random>                            # see below
   COHORT_KEY=<random>
   MAX_SESSIONS_PER_IP_DAY=10                      # raise for campus/company networks
   RECAPTCHA_SITE_KEY=                             # step 7
   RECAPTCHA_SECRET=
   ```

   Make the two random values on the PC with:

   ```powershell
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   ```

   Run it twice and save both values in your password manager.

   Not needed: `HOST` and `TRUST_PROXY`, which the server sets itself on Railway, and
   `PORT`, which Railway provides.
6. Under **Settings → Networking**, click **Generate Domain**. You get
   `https://<something>.up.railway.app`.
7. Click **Deploy** (or push any change under `social-lab/`). In **Deploy Logs**
   you should see:

   ```
   Social Lab 1.1.0 on http://localhost:8080
     ... | behind proxy
     storage: sealed sessions -> github.com/TK-dev-ptfl/social-lab-data (local copies removed after upload)
   ```

   If it says `cannot start: …`, the message names the variable to fix: a missing
   key, a bad token, or a public repo.

## 6. Check the whole path

1. Open the Railway URL and do a complete session.
2. In `social-lab-data` on GitHub, a file `sessions/xx/<64 hex>.sle` should appear,
   with commit message "session". Opening it shows binary noise; that is correct.
3. On the PC:

   ```powershell
   cd ..                                            # the folder containing your thesis repo
   git clone https://github.com/TK-dev-ptfl/social-lab-data.git
   cd lifecycle_of_automated_profiles_thesis\social-lab
   npm run decrypt -- --in ..\..\social-lab-data
   npm run analyze -- --data data-remote --device any
   ```

   `analysis/out/summary.md` should list your one session.
4. Delete it with its deletion code (bottom of the start page). The file disappears
   from the data repo.

## 7. reCAPTCHA

1. Go to **google.com/recaptcha/admin/create**, choose **Score based (v3)**, and set
   the domain to `<something>.up.railway.app`.
2. Put both keys into Railway's variables. Railway redeploys automatically.

## 8. Day-to-day

| Task | How |
|---|---|
| Get new data | `git -C ..\..\social-lab-data pull`, then `npm run decrypt -- --in ..\..\social-lab-data` and `npm run analyze -- --data data-remote` |
| Sessions currently being recorded | `curl.exe -H "Authorization: Bearer <ADMIN_TOKEN>" https://<domain>/admin/sessions` |
| Logs | Railway → service → **Deploy Logs**: one line per uploaded session (`session uploaded (ended)`) |
| Cost | Railway → **Usage** |
| Run a bot cohort | `https://<domain>/?cohort=<label>&key=<COHORT_KEY>&run=<id>` |

**Redeploys interrupt sessions in progress.** On shutdown the server uploads
everything pending; sessions record `ended_reason: shutdown`. But a participant who
is mid-session loses the rest of their recording. Before pushing a change under
`social-lab/`, check that `/admin/sessions` is empty.

`ended_reason` in `meta.json` tells you how each session reached the repo:

| Value | Meaning |
|---|---|
| `finished` | completed normally |
| `abandoned` | no activity for 30 min (`IDLE_MINUTES`) |
| `shutdown` | uploaded during a redeploy |

### Purging deleted sessions from history (monthly, and after any deletion request)

Deleting a file removes it from the repo, but git history keeps old versions. They
are only ciphertext, but the consent text promises they are purged within 30 days.
With no sessions in progress:

```powershell
cd ..\..\social-lab-data
git pull
git checkout --orphan fresh
git add -A
git commit -m "snapshot"
git branch -D main
git branch -m main
git push --force origin main
```

This replaces the history with a single commit holding only the current files.
GitHub may keep unreachable objects in its caches for a while; they too are only
ciphertext.

## If something goes wrong

| Symptom | Cause and fix |
|---|---|
| Build log says *Railpack could not determine how to build the app* and lists only `README.md` | The service is connected to the data repository. Settings → Source → Disconnect, then connect the thesis repository and check Root Directory and Config file path again. |
| Build fails: "Dockerfile not found" | Root Directory is not `/social-lab`. |
| Every push redeploys the study | Config file path is not `/social-lab/railway.json`, so the watch paths aren't loaded. |
| `cannot start: DATA_REPO ... not reachable with this token (HTTP 401)` | Token wrong or expired. Make a new one (step 3) and update the variable. |
| `... is public` | The data repo must be private: Settings → General → Danger Zone → Change visibility. |
| `upload failed, kept locally` in the logs | GitHub unreachable, or the token expired mid-study. The server retries every minute; fix the token. A redeploy while uploads are failing would lose those sessions. |
| Health check fails | The app didn't start; read the first lines of Deploy Logs. |
| Participants get "too many sessions from this network today" | They share one address. Raise `MAX_SESSIONS_PER_IP_DAY`. |
