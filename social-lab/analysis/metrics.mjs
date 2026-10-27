// Per-session measurements. Each block is tagged with the research question it
// answers (docs/STUDY.md) and every definition is written out in
// docs/ANALYSIS.md; keep the two in step. Pure functions of one session's
// data, so they can be tested on synthetic sessions (test/metrics.test.mjs).

import { mean, median, quantile, cv, sd, burstiness, memory, ols, round } from './stats.mjs';

const STROKE_GAP_MS = 300;      // a pause longer than this ends a movement
const MIN_STROKE_PX = 40;       // shorter movements are adjustments, not aimed moves
const RESAMPLE_MS = 16;         // kinematics on a fixed grid (sampling-rate independent)
const VISIBLE_RATIO = 0.5;      // a post counts as "on screen" at >= 50 % visible
const TYPING_GAP_MS = 5000;     // a longer gap between keys starts a new typing episode
const IKI_MAX_MS = 3000;        // longer gaps are pauses, not inter-key intervals

const FIELD_KINDS = new Set(['reply', 'composer', 'search']);
const ACTIONS = { like: 'L', repost: 'R', save: 'S', share: 'H', comment_submit: 'C', post_submit: 'P',
  follow: 'F', profile_open: 'V', comments_open: 'O', media_click: 'M' };

// ---------------------------------------------------------------- loading

/** Flattens a session's batches into one time-ordered event list. */
export function flatten(batches) {
  const ev = [];
  for (const b of batches.sort((a, b) => a.seq - b.seq)) for (const e of b.events) ev.push(e);
  return ev.sort((a, b) => a[1] - b[1]);
}

const of = (ev, type) => ev.filter(e => e[0] === type);

function phases(ev) {
  const ph = of(ev, 'ph');
  const end = (of(ev, 'end')[0] || ev[ev.length - 1] || [0, 0])[1];
  const out = {};
  ph.forEach((p, i) => { out[p[2]] = [p[1], i + 1 < ph.length ? ph[i + 1][1] : end]; });
  return { ...out, end };
}

/** Hidden-tab intervals, from visibilitychange events. */
function hiddenIntervals(ev, end) {
  const out = []; let since = null;
  for (const e of of(ev, 'vs')) {
    if (e[2] === 0 && since === null) since = e[1];
    if (e[2] === 1 && since !== null) { out.push([since, e[1]]); since = null; }
  }
  if (since !== null) out.push([since, end]);
  return out;
}
const overlap = (a, b, ints) => ints.reduce((s, [x, y]) => s + Math.max(0, Math.min(b, y) - Math.max(a, x)), 0);
/** Union of intervals, so overlapping exclusions are not subtracted twice. */
function mergeIntervals(ints) {
  const s = ints.filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]), out = [];
  for (const [a, b] of s) { if (out.length && a <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b); else out.push([a, b]); }
  return out;
}

// ------------------------------------------------------- pointer: samples

/** Mouse positions over time. Uses the coalesced samples when the device
 *  reported them (the device's own rate), else the dispatched events. */
export function mouseSamples(ev) {
  const s = [];
  for (const e of of(ev, 'pm')) {
    if (e[7] !== 'm' || !e[8]) continue;   // mouse only, trusted only
    const co = e[9] || [];
    if (co.length >= 6) for (let i = 0; i < co.length; i += 3) s.push([e[1] + co[i], co[i + 1], co[i + 2]]);
    else s.push([e[1], e[2], e[3]]);
  }
  s.sort((a, b) => a[0] - b[0]);
  return s.filter((p, i) => i === 0 || p[0] > s[i - 1][0] || p[1] !== s[i - 1][1] || p[2] !== s[i - 1][2]);
}

/** Cuts samples into strokes at pauses longer than STROKE_GAP_MS. */
export function strokes(samples) {
  const out = []; let cur = [];
  for (const p of samples) {
    if (cur.length && p[0] - cur[cur.length - 1][0] > STROKE_GAP_MS) { out.push(cur); cur = []; }
    cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out.filter(s => s.length >= 6 && Math.hypot(s[s.length - 1][1] - s[0][1], s[s.length - 1][2] - s[0][2]) >= MIN_STROKE_PX);
}

function resample(stroke) {
  const out = [], t0 = stroke[0][0], t1 = stroke[stroke.length - 1][0];
  let j = 0;
  for (let t = t0; t <= t1; t += RESAMPLE_MS) {
    while (j < stroke.length - 2 && stroke[j + 1][0] < t) j++;
    const a = stroke[j], b = stroke[j + 1] || a, f = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0;
    out.push([t, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
  }
  return out;
}

/** RQ-M1: kinematics of one aimed movement. */
export function strokeMetrics(stroke) {
  const r = resample(stroke);
  const v = [];
  for (let i = 1; i < r.length; i++) v.push(Math.hypot(r[i][1] - r[i - 1][1], r[i][2] - r[i - 1][2]) / RESAMPLE_MS);
  let path = 0, turns = [];
  let prevAngle = null;
  for (let i = 1; i < stroke.length; i++) {
    const dx = stroke[i][1] - stroke[i - 1][1], dy = stroke[i][2] - stroke[i - 1][2];
    const d = Math.hypot(dx, dy); path += d;
    if (d >= 1) {
      const a = Math.atan2(dy, dx);
      if (prevAngle !== null) { let t = a - prevAngle; while (t > Math.PI) t -= 2 * Math.PI; while (t < -Math.PI) t += 2 * Math.PI; turns.push(Math.abs(t)); }
      prevAngle = a;
    }
  }
  const s0 = stroke[0], s1 = stroke[stroke.length - 1];
  const dist = Math.hypot(s1[1] - s0[1], s1[2] - s0[2]);
  if (!v.length) return null;
  const peak = Math.max(...v), peakIdx = v.indexOf(peak);
  const tail = v.slice(Math.floor(v.length * 0.9));
  // Submovements: speed maxima above 20 % of the peak, separated by a dip
  // below 70 % of the smaller neighbouring maximum (Meyer et al. 1988: a
  // primary movement plus corrective ones).
  const sm = v.map((x, i) => (v[i - 1] ?? x) / 4 + x / 2 + (v[i + 1] ?? x) / 4);
  let subs = 0, lastPeak = null, minSince = Infinity;
  for (let i = 1; i < sm.length - 1; i++) {
    minSince = Math.min(minSince, sm[i]);
    if (sm[i] >= sm[i - 1] && sm[i] > sm[i + 1] && sm[i] >= 0.2 * peak) {
      if (lastPeak === null || minSince < 0.7 * Math.min(lastPeak, sm[i])) { subs++; lastPeak = sm[i]; minSince = Infinity; }
      else lastPeak = Math.max(lastPeak, sm[i]);
    }
  }
  return {
    t0: s0[0], t1: s1[0], duration_ms: s1[0] - s0[0], distance_px: dist, path_px: path,
    straightness: path ? dist / path : null, peak_speed: peak, mean_speed: mean(v), speed_cv: cv(v),
    peak_position: v.length > 1 ? peakIdx / (v.length - 1) : null, end_speed_ratio: peak ? mean(tail) / peak : null,
    submovements: Math.max(1, subs), turn_mean: mean(turns),
    start: [s0[1], s0[2]], end: [s1[1], s1[2]], samples: stroke.length,
  };
}

// ------------------------------------------------------- pointer: clicks

/** RQ-M2/M3: each mouse click on a known target as a Fitts' law trial. */
export function clickTrials(ev, samples, strokeList) {
  const downs = of(ev, 'pd'), ups = of(ev, 'pu'), hovers = of(ev, 'ho');
  const trials = [];
  let prevDown = -Infinity;
  for (const d of downs) {
    const [, t, x, y, button, pt, , , , trusted, kind, , rect] = d;
    const prev = prevDown; prevDown = t;
    if (pt !== 'm' || button !== 0 || !trusted) continue;
    const up = ups.find(u => u[1] >= t && u[4] === button);
    const trial = { t, kind, press_ms: up ? up[1] - t : null, hovered_first: null, D: null, W: null, ID: null, MT: null,
      along: null, across: null, overshoot: null, settle_ms: null, moved: false };
    if (kind) trial.hovered_first = hovers.some(h => h[1] > prev && h[1] <= t && h[2] === kind);
    // The movement that brought the cursor here: the last stroke that ended
    // no more than 1.5 s before the press.
    const st = [...strokeList].reverse().find(s => s.t1 <= t + 20 && t - s.t1 <= 1500);
    if (rect && st) {
      const cx = rect[0] + rect[2] / 2, cy = rect[1] + rect[3] / 2;
      const D = Math.hypot(cx - st.start[0], cy - st.start[1]);
      if (D > 1) {
        const ux = (cx - st.start[0]) / D, uy = (cy - st.start[1]) / D;
        const W = Math.abs(ux) * rect[2] + Math.abs(uy) * rect[3];     // target extent along the approach
        const Wp = Math.abs(uy) * rect[2] + Math.abs(ux) * rect[3];    // ... and across it
        const ex = x - cx, ey = y - cy;
        const seg = samples.filter(p => p[0] >= st.t0 && p[0] <= t);
        const reach = Math.max(...seg.map(p => (p[1] - st.start[0]) * ux + (p[2] - st.start[1]) * uy));
        let arrival = null;
        for (let i = seg.length - 1; i >= 0; i--) {
          const p = seg[i];
          if (p[1] >= rect[0] && p[1] <= rect[0] + rect[2] && p[2] >= rect[1] && p[2] <= rect[1] + rect[3]) arrival = p[0]; else break;
        }
        Object.assign(trial, {
          moved: true, D, W, ID: Math.log2(D / W + 1), MT: t - st.t0,
          along: (ex * ux + ey * uy) / W, across: (-ex * uy + ey * ux) / Wp,
          overshoot: reach > D + W / 2 + 2, settle_ms: arrival !== null ? t - arrival : null,
        });
      }
    }
    trials.push(trial);
  }
  return trials;
}

// ------------------------------------------------------------- keyboard

/** RQ-K1..K5: typing in the site's text fields. */
export function typing(ev) {
  const downs = of(ev, 'kd').filter(e => FIELD_KINDS.has(e[8]) && !e[6] && e[7]);
  const ups = of(ev, 'ku');
  const holds = [];
  for (const d of downs) {
    const u = ups.find(x => x[1] >= d[1] && x[4] === d[4]);
    if (u) holds.push(u[1] - d[1]);
  }
  const iki = [], ikiWordStart = [], ikiInWord = [], sameHand = [], otherHand = [];
  let rollovers = 0, pairs = 0;
  const episodes = [];
  let ep = null;
  for (let i = 0; i < downs.length; i++) {
    const d = downs[i], p = downs[i - 1];
    if (!p || d[8] !== p[8] || d[1] - p[1] > TYPING_GAP_MS) { ep = { field: d[8], t0: d[1], t1: d[1], keys: 0 }; episodes.push(ep); }
    ep.keys++; ep.t1 = d[1];
    if (!p || d[8] !== p[8]) continue;
    const gap = d[1] - p[1];
    if (gap > IKI_MAX_MS) continue;
    iki.push(gap); pairs++;
    const pu = ups.find(x => x[1] >= p[1] && x[4] === p[4]);
    if (pu && pu[1] > d[1]) rollovers++;
    if (d[2] === 'l' && p[2] === 's') ikiWordStart.push(gap);
    if (d[2] === 'l' && p[2] === 'l') {
      ikiInWord.push(gap);
      if (d[3] && p[3] && d[3] !== 'S' && p[3] !== 'S') (d[3] === p[3] ? sameHand : otherHand).push(gap);
    }
  }
  const inserted = of(ev, 'in').filter(e => FIELD_KINDS.has(e[3]) && e[2].startsWith('insert')).reduce((s, e) => s + e[4], 0);
  const pasted = of(ev, 'in').some(e => e[2] === 'insertFromPaste') || of(ev, 'cp').some(e => e[2] === 'paste');
  const typedKeys = downs.filter(d => 'ldsp'.includes(d[2])).length;
  const minutes = episodes.reduce((s, e) => s + (e.t1 - e.t0), 0) / 60000;
  // Time from clicking into a field to the first key press.
  const presses = of(ev, 'pd').filter(e => FIELD_KINDS.has(e[10]));
  const preType = episodes.map(e => {
    const p = [...presses].reverse().find(x => x[1] <= e.t0 && x[10] === e.field && e.t0 - x[1] < 30000);
    return p ? e.t0 - p[1] : null;
  });
  return {
    keys: downs.length, hold_ms: median(holds), hold_p10: quantile(holds, 0.1), hold_p90: quantile(holds, 0.9), hold_cv: cv(holds),
    iki_ms: median(iki), iki_cv: cv(iki), iki_word_start_ms: median(ikiWordStart), iki_in_word_ms: median(ikiInWord),
    iki_same_hand_ms: median(sameHand), iki_other_hand_ms: median(otherHand),
    rollover_rate: pairs ? rollovers / pairs : null,
    backspace_rate: downs.length ? downs.filter(d => d[2] === 'b').length / downs.length : null,
    wpm: minutes > 0 && typedKeys > 5 ? (typedKeys / 5) / minutes : null,
    pre_typing_ms: median(preType), episodes: episodes.length,
    insert_vs_keys: typedKeys ? inserted / typedKeys : null, pasted,
    holds, iki,
  };
}

// ---------------------------------------------------- wheel and scrolling

/** RQ-S1/S2 */
export function scrolling(ev, hidden) {
  const wh = of(ev, 'wh').filter(e => e[5]);
  const dy = wh.map(e => Math.abs(e[3])).filter(v => v > 0);
  const counts = new Map(); for (const v of dy) counts.set(v, (counts.get(v) || 0) + 1);
  const mode = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  const bursts = []; let cur = [];
  for (const e of wh) { if (cur.length && e[1] - cur[cur.length - 1][1] > 300) { bursts.push(cur); cur = []; } cur.push(e); }
  if (cur.length) bursts.push(cur);
  const intra = bursts.flatMap(b => b.slice(1).map((e, i) => e[1] - b[i][1]));
  const sc = of(ev, 'sc');
  let dist = 0; const pauses = [], speeds = [];
  for (let i = 1; i < sc.length; i++) {
    const dt = sc[i][1] - sc[i - 1][1], d = Math.abs(sc[i][3] - sc[i - 1][3]);
    dist += d;
    if (dt > 1000 && !overlap(sc[i - 1][1], sc[i][1], hidden)) pauses.push(dt);
    else if (dt > 0 && dt <= 200) speeds.push(d / dt * 1000);
  }
  // Scrolling with no wheel event just before it: scrollbar drag, keyboard,
  // touch or a script.
  const nonWheel = sc.filter(s => !wh.some(w => w[1] <= s[1] && s[1] - w[1] < 250)).length;
  return {
    wheel_events: wh.length, wheel_delta_mode: wh.length ? median(wh.map(e => e[4])) : null,
    wheel_dy_mode: mode ? mode[0] : null, wheel_dy_mode_share: mode ? mode[1] / dy.length : null,
    wheel_small_share: dy.length ? dy.filter(v => v < 20).length / dy.length : null,
    wheel_burst_notches: median(bursts.map(b => b.length)), wheel_intra_ms: median(intra), wheel_intra_cv: cv(intra),
    scroll_px: dist, reading_pauses: pauses.length, reading_pause_ms: median(pauses),
    scroll_speed_px_s: median(speeds), scroll_non_wheel_share: sc.length ? nonWheel / sc.length : null,
  };
}

// --------------------------------------------- exposure, reading, engagement

/** Intervals while the profile overlay covered the feed. */
function overlayIntervals(ev, end) {
  const out = []; let since = null;
  for (const a of of(ev, 'act')) {
    if (a[2] === 'profile_open' && since === null) since = a[1];
    if (a[2] === 'profile_close' && since !== null) { out.push([since, a[1]]); since = null; }
  }
  if (since !== null) out.push([since, end]);
  return out;
}

/** RQ-R1/R2/E1/E2: what was on screen, for how long, and what was acted on.
 *
 *  Viewport time counts only inside `window` (phase 1, free browsing, by
 *  default) and outside `excluded` intervals (hidden tab, profile overlay).
 *  In phase 2 people work at the top of the feed on tasks, so the first posts
 *  stay on screen for minutes without being read; counting that time would
 *  turn task time into "reading". First-visible times and actions are taken
 *  from the whole session. */
export function exposure(ev, hidden, end, window = [0, end], excluded = []) {
  const cut = [...hidden, ...excluded, [-Infinity, window[0]], [window[1], Infinity]];
  const counted = (a, b) => Math.max(0, (b - a) - overlap(a, b, mergeIntervals(cut)));
  const posts = new Map();
  for (const e of of(ev, 'it')) posts.set(e[2], { id: e[2], words: e[3], chars: e[4], media: !!e[5], index: e[7], vt_ms: 0, first_visible: null, actions: [] });
  const state = new Map();
  for (const e of of(ev, 'iv')) {
    const p = posts.get(e[2]); if (!p) continue;
    const s = state.get(e[2]);
    if (s && s.ratio >= VISIBLE_RATIO) p.vt_ms += counted(s.since, e[1]);
    if (e[3] >= VISIBLE_RATIO && p.first_visible === null) p.first_visible = e[1];
    state.set(e[2], { ratio: e[3], since: e[1] });
  }
  for (const [id, s] of state) {
    const p = posts.get(id);
    if (s.ratio >= VISIBLE_RATIO) p.vt_ms += counted(s.since, end);
  }
  for (const a of of(ev, 'act')) { const p = posts.get(a[3]); if (p) p.actions.push([a[1], a[2]]); }
  // Own posts and the posts inside a profile are not part of the feed.
  const list = [...posts.values()].filter(p => !p.id.startsWith('own') && !p.id.includes('-p'));
  const seen = list.filter(p => p.first_visible !== null);
  const textOnly = seen.filter(p => !p.media && p.vt_ms >= 1000 && p.vt_ms <= 120000);
  const fit = ols(textOnly.map(p => p.words), textOnly.map(p => p.vt_ms / 1000));
  const rates = textOnly.filter(p => p.words >= 15).map(p => p.words / (p.vt_ms / 60000));
  const liked = seen.filter(p => p.actions.some(a => a[1] === 'like'));
  const likeLatency = liked.map(p => p.actions.find(a => a[1] === 'like')[0] - p.first_visible).filter(v => v >= 0);
  const media = seen.filter(p => p.media && p.vt_ms > 0).map(p => p.vt_ms), text = seen.filter(p => !p.media && p.vt_ms > 0).map(p => p.vt_ms);
  return {
    summary: {
      posts_seen: seen.length, vt_median_ms: median(seen.map(p => p.vt_ms)),
      skim_share: seen.length ? seen.filter(p => p.vt_ms < 1000).length / seen.length : null,
      implied_wpm: median(rates), read_fit_s_per_word: fit ? fit.b : null, read_fit_intercept_s: fit ? fit.a : null,
      read_fit_r2: fit ? fit.r2 : null, read_fit_n: fit ? fit.n : 0,
      media_vt_ratio: median(media) && median(text) ? median(media) / median(text) : null,
      like_latency_ms: median(likeLatency), liked_words_median: median(liked.map(p => p.words)),
      seen_words_median: median(seen.map(p => p.words)), liked_index_median: median(liked.map(p => p.index)),
    },
    posts: list,
  };
}

/** RQ-E3/E4: the session as a sequence of social actions. */
export function rhythm(ev, ph) {
  const acts = of(ev, 'act').filter(a => ACTIONS[a[2]]);
  const times = acts.map(a => a[1]);
  const gaps = times.slice(1).map((t, i) => t - times[i]);
  const inFree = ph.free ? acts.filter(a => a[1] >= ph.free[0] && a[1] < ph.free[1]) : [];
  const freeMin = ph.free ? (ph.free[1] - ph.free[0]) / 60000 : null;
  // Action string: one letter per action, with the pause before it as a
  // separator class: '' < 2 s, '.' < 10 s, ':' < 60 s, '|' longer.
  let str = '';
  acts.forEach((a, i) => {
    if (i) { const g = a[1] - acts[i - 1][1]; str += g < 2000 ? '' : g < 10000 ? '.' : g < 60000 ? ':' : '|'; }
    str += ACTIONS[a[2]];
  });
  return {
    actions: acts.length, free_actions: inFree.length, free_actions_per_min: freeMin ? inFree.length / freeMin : null,
    spontaneous_engagement: inFree.some(a => ['like', 'comment_submit', 'repost', 'follow', 'post_submit'].includes(a[2])),
    action_gap_ms: median(gaps), burstiness: burstiness(gaps), memory: memory(gaps), action_string: str,
  };
}

/** RQ-M4: what the hand does while nothing is being clicked. */
export function idleCursor(ev, samples, hidden, ph) {
  const start = ph.free ? ph.free[0] : (samples[0] || [0])[0], end = ph.end;
  const busy = of(ev, 'pd').map(d => [d[1] - 1000, d[1] + 1000]);
  let windows = 0, active = 0, j = 0;
  for (let t = start; t + 1000 <= end; t += 1000) {
    if (overlap(t, t + 1000, hidden) > 0 || overlap(t, t + 1000, busy) > 0) continue;
    windows++;
    while (j < samples.length && samples[j][0] < t) j++;
    if (j < samples.length && samples[j][0] < t + 1000) active++;
  }
  return { restlessness: windows ? active / windows : null, idle_windows: windows };
}

// --------------------------------------------- hardware, network, detectors

const browserFamily = ua => /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox'
  : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'other';
const osFamily = ua => /Windows/.test(ua) ? 'Windows' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
  : /Mac OS X/.test(ua) ? 'macOS' : /CrOS/.test(ua) ? 'ChromeOS' : /Linux/.test(ua) ? 'Linux' : 'other';

/** RQ-H1..H3 */
export function hardware(device, ev) {
  if (!device) return {};
  const ua = device.browser?.user_agent || '';
  const fr = of(ev, 'fr').map(e => e[2]);
  const pm = of(ev, 'pm').filter(e => e[7] === 'm');
  const multi = pm.filter(e => (e[9] || []).length >= 6);
  const rates = multi.map(e => { const c = e[9]; const span = c[c.length - 3] - c[0]; return span > 0 ? (c.length / 3 - 1) / span * 1000 : null; });
  const c = device.consistency || {}, a = device.automation || {};
  const failed = [];
  for (const [k, v] of Object.entries(c.worker_matches || {})) if (v === false) failed.push('worker_' + k);
  for (const [k, v] of Object.entries(c.shared_worker_matches || {})) if (v === false) failed.push('shared_worker_' + k);
  for (const [k, v] of Object.entries(c.iframe || {})) if (v === false) failed.push('iframe_' + k);
  if (c.canvas_stable === false) failed.push('canvas_unstable');
  if (c.permission && c.permission.notification === 'denied' && c.permission.query === 'prompt') failed.push('permission_mismatch');
  return {
    os: osFamily(ua), browser: browserFamily(ua), browser_major: (ua.match(/(?:Chrome|Firefox|Version)\/(\d+)/) || [])[1] || null,
    screen: device.machine ? `${device.machine.screen.w}x${device.machine.screen.h}` : null, dpr: device.machine?.dpr ?? null,
    cores: device.machine?.cores ?? null, memory_gb: device.machine?.memory_gb ?? null,
    gpu_vendor: (device.machine?.webgl?.renderer || '').match(/NVIDIA|AMD|Radeon|Intel|Apple|Adreno|Mali|SwiftShader|llvmpipe/i)?.[0] || null,
    languages: (device.browser?.languages || []).join(' '), timezone: device.locale?.timezone || null,
    pointer_fine: device.input_capabilities?.pointer_fine ?? null, touch_points: device.machine?.touch_points ?? null,
    refresh_hz: median(fr) ? round(1000 / median(fr), 0) : null,
    coalesced_share: pm.length ? multi.length / pm.length : null, report_rate_hz: median(rates),
    consistency_failures: failed.join(' '),
    webdriver: !!a.webdriver, headless_ua: !!a.headless_ua, automation_leftovers: (a.leftovers || []).length,
    tampered_builtins: (a.tampered || []).length, botd_bot: a.botd ? a.botd.bot ?? null : null,
  };
}

/** RQ-N1..N4 */
export function network(meta, device, ev) {
  const n = meta.network || {};
  const ip = n.ip_network || {};
  const tz = device?.locale?.timezone;
  const order = n.navigation_headers?.order || [];
  return {
    ja4: n.tls?.ja4 || null, ja3: n.tls?.ja3 || null,
    header_order: order.map(h => h.toLowerCase()).join(','),
    accept_language: n.navigation_headers?.values?.['accept-language'] || null,
    ip_country: ip.country || null, ip_asn: ip.asn || null, ip_hosting: ip.hosting ?? null, ip_proxy: ip.proxy ?? null, ip_mobile: ip.mobile ?? null,
    tz_matches_ip: tz && ip.timezone ? tz === ip.timezone : null,
    webrtc_matches: meta.webrtc ? meta.webrtc.matches_request_ip : null,
    rtt_ms: median(of(ev, 'net').map(e => e[2])),
    clock_offset_ms: median(of(ev, 'net').map(e => e[3])),
    sessions_from_network_today: n.ip_sessions_today ?? null,
  };
}

/** Signals that are evidence of automation by themselves, regardless of how
 *  human the behaviour looks. Listed, not scored (docs/ANALYSIS.md). */
export function hardFlags(ev, hw, device) {
  const flags = [];
  const untrusted = of(ev, 'cnt').reduce((m, e) => Math.max(m, e[4]), 0);
  if (untrusted) flags.push('untrusted_events');
  if (hw.webdriver) flags.push('webdriver');
  if (hw.headless_ua) flags.push('headless_ua');
  if (hw.automation_leftovers) flags.push('automation_globals');
  if (hw.tampered_builtins) flags.push('tampered_builtins');
  if (hw.botd_bot) flags.push('botd');
  if (hw.consistency_failures) flags.push('fingerprint_inconsistent');
  const pm = of(ev, 'pm').filter(e => e[7] === 'm');
  if (pm.length >= 200 && hw.pointer_fine && !pm.some(e => (e[9] || []).length >= 6)) flags.push('no_coalesced_samples');
  const pd = of(ev, 'pd').filter(e => e[5] === 'm');
  const outer = device?.machine?.outer, inner = device?.machine?.inner;
  if (pd.length >= 3 && outer && inner && outer[1] - inner[1] > 30 && pd.every(e => e[13] === 0 && e[14] === 0)) flags.push('screen_equals_client');
  const last = of(ev, 'cnt').at(-1);
  if (last && last[2] > 50 && last[3] === 0) flags.push('mouse_without_pointer_events');
  return flags;
}

// ------------------------------------------------------------- the session

export function analyzeSession({ meta, device, end, recaptcha, batches }) {
  const ev = flatten(batches);
  const ph = phases(ev);
  const hidden = hiddenIntervals(ev, ph.end);
  const samples = mouseSamples(ev);
  const strokeList = strokes(samples).map(strokeMetrics).filter(Boolean);
  const clicks = clickTrials(ev, samples, strokeList);
  const typed = typing(ev);
  const exp = exposure(ev, hidden, ph.end, ph.free || [0, ph.end], overlayIntervals(ev, ph.end));
  const hw = hardware(device, ev);
  const moved = clicks.filter(c => c.moved && c.D >= 2 * c.W && c.MT > 0);
  const fitts = ols(moved.map(c => c.ID), moved.map(c => c.MT));
  const scores = (recaptcha || []).filter(r => r.success && typeof r.score === 'number').map(r => r.score);
  const vis = of(ev, 'vs');

  const row = {
    session: meta.id, cohort: meta.cohort, run_label: meta.run_label || '', study_version: meta.study_version,
    device_reported: end?.survey?.device || '', hand: end?.survey?.hand || '', typing_style: end?.survey?.typing || '',
    english_l1: end?.survey?.english || '', age: end?.survey?.age || '', social_use: end?.survey?.social || '',
    natural_rating: end?.survey?.natural ? Number(end.survey.natural) : null,
    completed: !!meta.ended_at, tasks_done: end?.tasks ? Object.values(end.tasks).filter(v => v !== null).length : 0,
    free_phase_s: ph.free ? (ph.free[1] - ph.free[0]) / 1000 : null, task_phase_s: ph.tasks ? (ph.tasks[1] - ph.tasks[0]) / 1000 : null,
    hidden_share: ph.end ? hidden.reduce((s, [a, b]) => s + b - a, 0) / ph.end : null,
    tab_switches: vis.filter(e => e[2] === 0).length, text_selections: of(ev, 'se').filter(e => e[2] > 0).length,
    // RQ-M1
    strokes: strokeList.length,
    stroke_straightness: median(strokeList.map(s => s.straightness)), stroke_peak_speed: median(strokeList.map(s => s.peak_speed)),
    stroke_speed_cv: median(strokeList.map(s => s.speed_cv)), stroke_peak_position: median(strokeList.map(s => s.peak_position)),
    stroke_end_speed_ratio: median(strokeList.map(s => s.end_speed_ratio)), stroke_submovements: median(strokeList.map(s => s.submovements)),
    stroke_turn_mean: median(strokeList.map(s => s.turn_mean)), stroke_duration_ms: median(strokeList.map(s => s.duration_ms)),
    // RQ-M2/M3
    clicks: clicks.length, click_press_ms: median(clicks.map(c => c.press_ms)), click_press_cv: cv(clicks.map(c => c.press_ms)),
    click_settle_ms: median(clicks.map(c => c.settle_ms)), click_hovered_share: share(clicks.filter(c => c.kind), c => c.hovered_first),
    click_overshoot_share: share(moved, c => c.overshoot), click_without_movement_share: share(clicks.filter(c => c.kind), c => !c.moved),
    endpoint_along_sd: sd(moved.map(c => c.along)), endpoint_across_sd: sd(moved.map(c => c.across)),
    fitts_a_ms: fitts ? fitts.a : null, fitts_b_ms_per_bit: fitts ? fitts.b : null, fitts_r2: fitts ? fitts.r2 : null, fitts_n: fitts ? fitts.n : 0,
    throughput_bits_s: mean(moved.map(c => c.ID / (c.MT / 1000))),
    // RQ-M4
    ...idleCursor(ev, samples, hidden, ph),
    // RQ-K
    keys: typed.keys, key_hold_ms: typed.hold_ms, key_hold_p10: typed.hold_p10, key_hold_p90: typed.hold_p90, key_hold_cv: typed.hold_cv,
    iki_ms: typed.iki_ms, iki_cv: typed.iki_cv, iki_word_start_ms: typed.iki_word_start_ms, iki_in_word_ms: typed.iki_in_word_ms,
    iki_same_hand_ms: typed.iki_same_hand_ms, iki_other_hand_ms: typed.iki_other_hand_ms,
    rollover_rate: typed.rollover_rate, backspace_rate: typed.backspace_rate, wpm: typed.wpm, pre_typing_ms: typed.pre_typing_ms,
    insert_vs_keys: typed.insert_vs_keys, pasted: typed.pasted,
    // RQ-S
    ...scrolling(ev, hidden),
    // RQ-R/E
    ...exp.summary,
    ...rhythm(ev, ph),
    // RQ-H
    ...hw,
    // RQ-N
    ...network(meta, device, ev),
    // RQ-X
    recaptcha_n: scores.length, recaptcha_mean: mean(scores), recaptcha_min: scores.length ? Math.min(...scores) : null,
    hard_flags: hardFlags(ev, hw, device).join(' '),
  };
  for (const k of Object.keys(row)) if (typeof row[k] === 'number') row[k] = round(row[k], 4);
  return { row, strokes: strokeList, clicks, posts: exp.posts, holds: typed.holds, iki: typed.iki };
}

function share(list, pred) { const l = list.filter(x => pred(x) !== null && pred(x) !== undefined); return l.length ? l.filter(pred).length / l.length : null; }
