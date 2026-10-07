# Hearth feed lab

A dummy social feed with a floating "Session check" panel. The panel scores:

- **Behaviour**: cursor paths, clicks, scrolling and typing, analysed in the page.
- **Fingerprint consistency**: automation leftovers, headless tells and spoofing mismatches, analysed in the page.
- **reCAPTCHA v3**: Google's 0.0–1.0 score. This needs your keys and the included server.

The first two run entirely in the page, so the lab is useful with no keys at all —
which is the usual way to exercise `app.behaviour` against something that pushes
back.

## 1. Configure (optional)

```bash
cp .env.example .env
```

Then fill in `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET`. Get them from
https://www.google.com/recaptcha/admin/create — choose "Score based (v3)" and add
`localhost` plus any domain you will use.

`.env` is gitignored. Real environment variables take precedence over it, so a
one-off override still works: `PORT=9000 node server.mjs`.

Leave the keys blank and reCAPTCHA shows as "Not configured"; everything else
still runs.

## 2. Run (Node 18 or newer, no install step)

```bash
node server.mjs
```

Open http://localhost:8080.

## How reCAPTCHA runs

It runs at page load, then again on likes, reposts, comments, posts and follows,
every 2,500 px of scrolling, and every 45 seconds — at most once per 8 seconds.
Each token is verified by the server, and the panel shows the latest score. The
server console logs every score.

The reCAPTCHA badge is hidden so it doesn't overlap the panel; the required
attribution text appears in the panel instead.

## Limits

No client-side tester is bulletproof. A real browser driven with replayed human
input can pass the in-page checks. reCAPTCHA scores also depend heavily on your
Google cookies and IP reputation, not only on behaviour on this page — a fresh
profile or VPN can score low even for a human.
