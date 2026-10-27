# Deploying Social Lab for free

Target: an **Oracle Cloud "Always Free"** virtual machine with a free **DuckDNS**
domain and a free **Let's Encrypt** certificate. Total cost €0. The server terminates
TLS itself, so every signal works, including TLS fingerprints.

About 1–2 hours the first time. Commands marked **PC** run in PowerShell on your
Windows machine; commands marked **VM** run on the server over SSH.

> **Don't share the link** until the ethics question in
> [../docs/STUDY.md](../docs/STUDY.md) (Ethics and data protection) is answered.
> Deploying and piloting with people you know is fine.

## Why this setup

| Option | Cost | TLS fingerprints | Data survives | Verdict |
|---|---|---|---|---|
| **Oracle Cloud Always Free VM** | €0, card needed for verification | ✅ | ✅ (block volume) | **use this** |
| Google Cloud free e2-micro | €0, card needed; US regions only | ✅ | ✅ | fallback |
| Render / Railway / Koyeb free tiers | €0 | ❌ their proxy terminates TLS | ❌ disk wiped on restart, apps sleep | unsuitable |
| Your PC + Cloudflare Tunnel | €0 | ❌ Cloudflare terminates TLS | ✅ | only if the PC never sleeps |

Also free:
- **DuckDNS** gives a name like `hearth-study.duckdns.org`.
- **reCAPTCHA v3** is free up to 10,000 checks a month. A session uses about 15, so
  that covers roughly 600 sessions.
- **ip-api.com** is free for non-commercial use.

Optional: a real domain (`.sk` or `.eu` for about €10 a year) looks more trustworthy to
participants than a DuckDNS name.

---

## 1. Create an SSH key (PC)

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\sociallab
# Press Enter twice for no passphrase, or set one.
Get-Content $HOME\.ssh\sociallab.pub   # copy this line; you need it in step 2
```

## 2. Create the VM (Oracle Cloud console)

1. Sign up at **cloud.oracle.com/free**. Choose a home region close to your
   participants, e.g. *Germany Central (Frankfurt)*. **The home region cannot be
   changed later.** The card is only for verification; Always Free resources are
   never charged.
2. **Menu → Compute → Instances → Create instance:**
   - **Image:** Canonical Ubuntu 24.04.
   - **Shape:** *VM.Standard.E2.1.Micro* (AMD, "Always Free-eligible"). The ARM
     *A1.Flex* is also free and much faster, but often shows "out of capacity"; the
     micro is enough for this server.
   - **Networking:** keep the defaults (new VCN, public subnet, **assign a public
     IPv4 address**).
   - **Add SSH keys:** *Paste public key*, the line from step 1.
3. **Create**, wait for *Running*, and write down the **Public IP address**.
4. **Open ports 80 and 443 in Oracle's firewall:**
   - instance page → the subnet link → *Security Lists* → *Default Security List* →
     **Add Ingress Rules**;
   - add two rules: source CIDR `0.0.0.0/0`, IP protocol TCP, destination port `80`;
     then the same with `443`.

## 3. Get a free domain (DuckDNS)

1. Sign in at **duckdns.org** (with GitHub or Google).
2. Add a subdomain, e.g. `hearth-study`, set its **current ip** to the VM's public IP
   and click *update ip*.
3. Check on the PC: `nslookup hearth-study.duckdns.org` should return that IP.

Below, replace `hearth-study.duckdns.org` with your name.

## 4. Prepare the server (VM)

```powershell
# PC: connect
ssh -i $HOME\.ssh\sociallab ubuntu@<PUBLIC_IP>
```

```bash
# VM: updates, Node 24, certbot
sudo apt update && sudo apt -y upgrade
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt -y install nodejs certbot
node --version                      # v24.x

# Oracle's Ubuntu images also block ports in the OS firewall. Open 80 and 443 there too:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# A user that only runs the service
sudo useradd --system --home /opt/social-lab --shell /usr/sbin/nologin sociallab
sudo mkdir -p /opt/social-lab
```

## 5. Upload the code (PC → VM)

Only `social-lab/` is needed. Pack it without data, secrets or local output:

```powershell
# PC, in the repository root
tar -czf social-lab.tgz --exclude=social-lab/data --exclude=social-lab/.env --exclude=social-lab/analysis/out social-lab
scp -i $HOME\.ssh\sociallab social-lab.tgz ubuntu@<PUBLIC_IP>:/tmp/
```

```bash
# VM
sudo tar -xzf /tmp/social-lab.tgz -C /opt --no-same-owner
sudo mkdir -p /opt/social-lab/data
sudo chown -R root:root /opt/social-lab
sudo chown sociallab:sociallab /opt/social-lab/data
sudo chmod 700 /opt/social-lab/data
cd /opt/social-lab && node --test        # should print: pass 34, fail 0
```

The code is owned by root and read-only to the service. Only `data/` is writable, and
only by the service.

## 6. Get the certificate (VM)

Nothing listens on port 80 yet, so certbot can use it once:

```bash
sudo certbot certonly --standalone -d hearth-study.duckdns.org -m you@example.org --agree-tos -n
sudo install -m 755 /opt/social-lab/deploy/install-cert.sh /usr/local/bin/social-lab-install-cert
sudo /usr/local/bin/social-lab-install-cert     # copies it to /opt/social-lab/certs
```

## 7. Configure and start (VM)

```bash
cd /opt/social-lab
sudo cp .env.example .env
echo "ADMIN_TOKEN: $(openssl rand -hex 32)"     # copy both values into .env,
echo "COHORT_KEY:  $(openssl rand -hex 32)"     # and save them in your password manager
sudo nano .env
```

Set these in `.env`:

```
STUDY_RESEARCHER=Tomas Knepp
STUDY_INSTITUTION=Comenius University Bratislava, Faculty of Mathematics, Physics and Informatics
STUDY_CONTACT=your.address@uniba.sk
HOST=0.0.0.0
PORT=443
HTTP_REDIRECT_PORT=80
TLS_CERT=/opt/social-lab/certs/fullchain.pem
TLS_KEY=/opt/social-lab/certs/privkey.pem
RECAPTCHA_SITE_KEY=          # step 9; empty is fine for now
RECAPTCHA_SECRET=
ADMIN_TOKEN=<from above>
COHORT_KEY=<from above>
# Raise this if you recruit on a campus or company network (one shared address):
MAX_SESSIONS_PER_IP_DAY=10
```

```bash
sudo chown root:sociallab .env && sudo chmod 640 .env     # the service can read it, nobody else
sudo cp deploy/social-lab.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now social-lab
sudo systemctl status social-lab          # "active (running)"
journalctl -u social-lab -n 20            # "Social Lab 1.0.0 on https://localhost:443 ... TLS fingerprints: on"
```

Open **https://hearth-study.duckdns.org** in your browser.

## 8. Switch renewals to the running server (VM)

The certificate lasts 90 days and certbot renews it automatically. The site now holds
port 80, so renewal must go through the files the site serves (`public/`):

```bash
sudo certbot certonly --webroot -w /opt/social-lab/public -d hearth-study.duckdns.org \
  --deploy-hook /usr/local/bin/social-lab-install-cert --force-renewal -n
sudo certbot renew --dry-run               # must say "Congratulations, all simulated renewals succeeded"
```

## 9. reCAPTCHA keys

1. Go to **google.com/recaptcha/admin/create**.
2. Choose **Score based (v3)**, domain `hearth-study.duckdns.org`.
3. Put the site key and secret key into `.env`.
4. Run `sudo systemctl restart social-lab`.

The log line should now say `reCAPTCHA: on`.

## 10. Check it end to end

1. Do one full session yourself in a normal browser.
2. On the VM, run `sudo ls /opt/social-lab/data/sessions/`. There should be one
   folder, containing `meta.json`, `device.json`, `events.ndjson`, `end.json` and
   `recaptcha.ndjson`.
3. Check the TLS fingerprint was captured:
   `sudo grep -o '"ja4":"[^"]*"' /opt/social-lab/data/sessions/*/meta.json`.
4. Check the admin list from the PC:
   ```powershell
   curl.exe -H "Authorization: Bearer <ADMIN_TOKEN>" https://hearth-study.duckdns.org/admin/sessions
   ```
5. Delete your test session with its deletion code, at the bottom of the start page.

Then run the **pilot** with 3–5 people (on a mouse, a trackpad and a phone) and look
at their data with `npm run analyze` (step 11).

## 11. Day-to-day

**Download the data to your PC** for analysis and backup:
```powershell
# Pack on the server, then copy. (Not "ssh ... > file": Windows PowerShell 5.1
# re-encodes redirected output as text and corrupts the archive.)
$d = Get-Date -Format yyyy-MM-dd
ssh -i $HOME\.ssh\sociallab ubuntu@<PUBLIC_IP> "sudo tar -czf /tmp/data.tgz -C /opt/social-lab data && sudo chown ubuntu /tmp/data.tgz"
scp -i $HOME\.ssh\sociallab ubuntu@<PUBLIC_IP>:/tmp/data.tgz "backup-$d.tgz"
ssh -i $HOME\.ssh\sociallab ubuntu@<PUBLIC_IP> "rm /tmp/data.tgz"
# Extract into the local social-lab folder, then analyse:
tar -xzf "backup-$d.tgz" -C social-lab
cd social-lab; npm run analyze
```

It is personal data:
- keep backups on encrypted storage (e.g. BitLocker);
- never put them in git or a shared drive;
- delete everything at the end of the retention period stated in the consent text.

| Task | Command (VM) |
|---|---|
| Live log | `journalctl -u social-lab -f` |
| Restart | `sudo systemctl restart social-lab` |
| Update the code | repeat step 5, keeping `data/` and `.env` (`--exclude` does that), then restart |
| Run a bot cohort | open `https://hearth-study.duckdns.org/?cohort=<label>&key=<COHORT_KEY>&run=<id>` |

## Things that can go wrong

| Symptom | Cause and fix |
|---|---|
| The browser can't connect at all | Port closed. Check **both** firewalls: the Oracle security list (step 2.4) and iptables (step 4). |
| certbot: "Timeout during connect" | The same two firewalls, or DuckDNS still points at an old IP. |
| The service won't start: "STUDY_CONTACT is not set" | Fill it in `.env`. This is deliberate: the consent page must name a contact. |
| `EACCES` on port 443 | The unit file lacks `AmbientCapabilities`, or it was not reloaded (`daemon-reload`). |
| Participants get "too many sessions from this network today" | They share one address. Raise `MAX_SESSIONS_PER_IP_DAY` and restart. |
| JA4 missing in `meta.json` | Something in front is terminating TLS (a proxy or CDN). Connect directly to the VM. |
| Oracle stopped or deleted the VM | Oracle may reclaim Always Free VMs that stay idle (very low CPU) for a week. Back up weekly. To avoid it, upgrade the account to *Pay As You Go*: Always Free resources stay free, and idle reclamation does not apply. |
