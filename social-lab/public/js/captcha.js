// reCAPTCHA v3: Google's score (0.0 likely bot ... 1.0 likely human) for each
// action. Tokens are verified server-side and the score is stored there; the
// page never sees it. What it is for: the distribution of a deployed commercial
// detector's scores over real people - its false-positive rate on this site -
// and, against bot cohorts, how well it separates them (docs/STUDY.md, RQ-X1).
// It is not used as ground truth: Google does not say what it measures.

export class Captcha {
  constructor({ siteKey, endpoint, token }) {
    Object.assign(this, { siteKey, endpoint, token });
    this.ready = false; this.last = 0; this.scrolledTo = 0;
  }

  async load() {
    if (!this.siteKey) return false;
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://www.google.com/recaptcha/api.js?render=' + encodeURIComponent(this.siteKey);
      s.async = true; s.onload = resolve; s.onerror = () => reject(new Error('blocked'));
      document.head.appendChild(s);
      setTimeout(() => reject(new Error('timeout')), 10000);
    }).catch(() => null);
    if (!window.grecaptcha) return false;
    await new Promise(r => grecaptcha.ready(r));
    this.ready = true;
    addEventListener('scroll', () => {
      if (scrollY - this.scrolledTo > 2500) { this.scrolledTo = scrollY; this.run('scroll'); }
    }, { passive: true });
    this.heartbeat = setInterval(() => { if (document.visibilityState === 'visible') this.run('heartbeat'); }, 45000);
    return true;
  }

  // At most one token per 8 s unless forced: reCAPTCHA is rate-sensitive, and
  // each request is itself something Google sees.
  async run(action, force = false) {
    if (!this.ready) return;
    const t = performance.now();
    if (!force && Date.now() - this.last < 8000) return;
    this.last = Date.now();
    try {
      const token = await grecaptcha.execute(this.siteKey, { action });
      await fetch(this.endpoint, { method: 'POST', headers: { 'content-type': 'application/json', 'x-session-token': this.token },
        body: JSON.stringify({ token, action, t: Math.round(t) }) });
    } catch { /* a failed token is simply missing from the record */ }
  }

  stop() { clearInterval(this.heartbeat); this.ready = false; }
}
