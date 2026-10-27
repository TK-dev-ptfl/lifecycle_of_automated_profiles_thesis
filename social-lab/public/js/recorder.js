// Input recorder. Every event type below is listed, with what it is for and
// the study it rests on, in docs/DATA_DICTIONARY.md - the code names (pm, pd,
// kd, ...) are the same there. Nothing is recorded before consent: this module
// is only imported once the participant has agreed.
//
// Times are performance.now() milliseconds, rounded to 0.1 ms, measured from
// page load. Positions are CSS pixels in the viewport (client coordinates);
// page coordinates follow from the scroll trace (sc).

const r1 = v => Math.round(v * 10) / 10;
const now = () => r1(performance.now());

// Key category. The key itself is never recorded - only what kind of key it
// was, which is enough for typing rhythm, word boundaries and corrections.
function keyCategory(e) {
  const k = e.key || '';
  if (k.length === 1) {
    if (k === ' ') return 's';
    if (/\p{L}/u.test(k)) return 'l';
    if (/\d/.test(k)) return 'd';
    return 'p';
  }
  return ({ Backspace: 'b', Delete: 'x', Enter: 'e', Tab: 't', Shift: 'm', Control: 'm', Alt: 'm', Meta: 'm', AltGraph: 'm',
    CapsLock: 'm', Process: 'u', Unidentified: 'u', Dead: 'u', Escape: 'o' })[k] || (k.startsWith('Arrow') ? 'a' : 'o');
}

// Which hand would press this physical key in standard touch-typing - from
// e.code, which names the key's position, not its letter. Lets the analysis
// separate same-hand from alternating-hand key pairs (Dhakal et al. 2018)
// without knowing what was typed.
const LEFT = /^(Backquote|Digit[1-5]|Key[QWERTASDFGZXCVB]|Tab|CapsLock|ShiftLeft|ControlLeft|AltLeft|MetaLeft)$/;
const RIGHT = /^(Digit[6-90]|Minus|Equal|Key[YUIOPHJKLNM]|Bracket(Left|Right)|Backslash|Semicolon|Quote|Comma|Period|Slash|Enter|Backspace|ShiftRight|ControlRight|AltRight|MetaRight|Arrow\w+|Delete)$/;
const hand = code => code === 'Space' ? 'S' : LEFT.test(code) ? 'L' : RIGHT.test(code) ? 'R' : '';

const ptype = t => (t === 'mouse' ? 'm' : t === 'touch' ? 't' : t === 'pen' ? 'p' : '?');
const targetOf = el => el && el.closest ? el.closest('[data-t]') : null;
const fieldOf = el => (el && el.dataset && el.dataset.field) || (el && el.closest && el.closest('[data-field]')?.dataset.field) || '';

export class Recorder {
  constructor({ endpoint, token, onNet }) {
    this.endpoint = endpoint;
    this.token = token;
    this.buf = [];
    this.seq = 0;
    this.keyIds = new Map();
    this.counts = { mousemove: 0, pointermove: 0, untrusted: 0 };
    this.frames = [];
    this.onNet = onNet;
    this.stopped = false;
    this.lastHover = null;
  }

  emit(...ev) { if (!this.stopped) this.buf.push(ev); }

  start() {
    const o = { capture: true, passive: true };
    const on = (type, fn) => addEventListener(type, fn, o);
    const trust = e => { if (!e.isTrusted) this.counts.untrusted++; return e.isTrusted ? 1 : 0; };

    this.emit('clk', now(), Date.now(), r1(performance.timeOrigin));

    on('mousemove', () => { this.counts.mousemove++; });
    on('pointermove', e => {
      this.counts.pointermove++;
      // Coalesced samples: positions the device reported between two
      // dispatched events. A real mouse at 500-1000 Hz yields several per
      // frame; input injected through DevTools yields one.
      const co = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
      const flat = [];
      if (co.length > 1) for (const c of co) flat.push(r1(c.timeStamp - e.timeStamp), r1(c.clientX), r1(c.clientY));
      this.emit('pm', r1(e.timeStamp), r1(e.clientX), r1(e.clientY), e.buttons, e.movementX, e.movementY,
        ptype(e.pointerType), trust(e), flat);
    }, o);
    on('pointerdown', e => {
      const t = targetOf(e.target);
      const r = t ? t.getBoundingClientRect() : null;
      this.emit('pd', r1(e.timeStamp), r1(e.clientX), r1(e.clientY), e.button, ptype(e.pointerType),
        r1(e.pressure), r1(e.width), r1(e.height), trust(e),
        t ? t.dataset.t : '', t ? (t.dataset.p || '') : '', r ? [r1(r.x), r1(r.y), r1(r.width), r1(r.height)] : null,
        r1(e.screenX - e.clientX), r1(e.screenY - e.clientY));
    });
    on('pointerup', e => this.emit('pu', r1(e.timeStamp), r1(e.clientX), r1(e.clientY), e.button, ptype(e.pointerType), trust(e)));
    on('pointercancel', e => this.emit('pc', r1(e.timeStamp), ptype(e.pointerType)));
    on('click', e => {
      const t = targetOf(e.target);
      this.emit('ck', r1(e.timeStamp), r1(e.clientX), r1(e.clientY), e.detail, trust(e), t ? t.dataset.t : '', t ? (t.dataset.p || '') : '');
    });
    on('pointerover', e => {
      const t = targetOf(e.target);
      const key = t ? t.dataset.t + ':' + (t.dataset.p || '') : null;
      if (key !== this.lastHover) { this.lastHover = key; this.emit('ho', r1(e.timeStamp), t ? t.dataset.t : '', t ? (t.dataset.p || '') : ''); }
    });
    on('wheel', e => this.emit('wh', r1(e.timeStamp), r1(e.deltaX), r1(e.deltaY), e.deltaMode, trust(e)));
    on('scroll', e => { if (e.target === document) this.emit('sc', r1(e.timeStamp), r1(scrollX), r1(scrollY)); });
    on('keydown', e => {
      let id = this.keyIds.get(e.code);
      if (id === undefined) { id = this.keyIds.size + 1; this.keyIds.set(e.code, id); }
      const mods = (e.shiftKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.altKey ? 4 : 0) | (e.metaKey ? 8 : 0);
      this.emit('kd', r1(e.timeStamp), keyCategory(e), hand(e.code), id, mods, e.repeat ? 1 : 0, trust(e), fieldOf(e.target));
    });
    on('keyup', e => {
      const id = this.keyIds.get(e.code) ?? 0;
      this.emit('ku', r1(e.timeStamp), keyCategory(e), hand(e.code), id, trust(e));
    });
    on('input', e => {
      const f = fieldOf(e.target);
      if (!f) return;
      this.emit('in', r1(e.timeStamp), e.inputType || '', f, e.data ? e.data.length : 0, (e.target.value || '').length, trust(e));
    });
    for (const kind of ['copy', 'cut', 'paste']) on(kind, e => this.emit('cp', r1(e.timeStamp), kind, fieldOf(e.target)));
    let selT = 0;
    on('selectionchange', e => {
      if (e.timeStamp - selT < 250) return;
      selT = e.timeStamp;
      const s = getSelection();
      const inField = document.activeElement && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
      if (!inField) this.emit('se', r1(e.timeStamp), s ? String(s).length : 0);
    });
    document.addEventListener('visibilitychange', () => this.emit('vs', now(), document.visibilityState === 'visible' ? 1 : 0));
    addEventListener('focus', () => this.emit('fo', now(), 1));
    addEventListener('blur', () => this.emit('fo', now(), 0));
    const size = () => this.emit('rs', now(), innerWidth, innerHeight, r1(devicePixelRatio), outerWidth, outerHeight);
    addEventListener('resize', size);
    size();

    // Frame timing: the display's refresh interval and how steady it is.
    let last = performance.now();
    const frame = t => {
      if (this.stopped) return;
      this.frames.push(t - last); last = t;
      if (this.frames.length >= 300) this.flushFrames();
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);

    this.timer = setInterval(() => this.flush(), 3000);
    addEventListener('pagehide', () => this.flush(true));
  }

  flushFrames() {
    const f = this.frames.filter(x => x > 0 && x < 1000).sort((a, b) => a - b);
    if (f.length > 10) this.emit('fr', now(), r1(f[f.length >> 1]), r1(f[Math.floor(f.length * 0.95)]), f.length, r1(f[f.length - 1]));
    this.frames = [];
  }

  async flush(final = false) {
    if (!this.buf.length && !final) return;
    this.emit('cnt', now(), this.counts.mousemove, this.counts.pointermove, this.counts.untrusted);
    const events = this.buf; this.buf = [];
    const body = JSON.stringify({ seq: this.seq++, sent: Date.now(), events });
    const sentAt = performance.now();
    try {
      let payload = body, headers = { 'content-type': 'application/json', 'x-session-token': this.token };
      if (!final && typeof CompressionStream === 'function') {
        payload = await new Response(new Blob([body]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
        headers['content-encoding'] = 'gzip';
      }
      const r = await fetch(this.endpoint, { method: 'POST', headers, body: payload, keepalive: final });
      if (!final && r.ok) {
        const j = await r.json();
        const rtt = performance.now() - sentAt;
        // Round trip, and the server clock relative to ours (NTP-style
        // midpoint estimate).
        this.emit('net', now(), r1(rtt), Math.round(j.serverTime - (Date.now() - rtt / 2)));
        this.onNet && this.onNet(rtt);
      }
    } catch {
      // Network hiccup: put the events back and try again next tick.
      if (!final) this.buf = events.concat(this.buf);
    }
  }

  async stop() {
    this.flushFrames();
    this.emit('end', now());
    clearInterval(this.timer);
    await this.flush();
    this.stopped = true;
  }
}

export const _internal = { keyCategory, hand };
