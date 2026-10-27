// The analysis on synthetic sessions whose right answers are known by
// construction. If one of these breaks, a number in the thesis would be wrong.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { strokes, strokeMetrics, clickTrials, typing, exposure, rhythm, mouseSamples, analyzeSession } from '../analysis/metrics.mjs';
import { burstiness, memory, auc, quantile, ols } from '../analysis/stats.mjs';
import { toSapiMouse } from '../analysis/export.mjs';

const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} not within ${tol} of ${b}`);

// Minimum-jerk point-to-point movement (Flash & Hogan 1985): position
// s(tau) = 10 tau^3 - 15 tau^4 + 6 tau^5, a symmetric bell-shaped speed profile.
function minJerk(t0, x0, y0, x1, y1, ms, dt = 8) {
  const out = [];
  for (let t = 0; t <= ms; t += dt) {
    const u = t / ms, s = 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5;
    out.push([t0 + t, x0 + (x1 - x0) * s, y0 + (y1 - y0) * s]);
  }
  return out;
}

test('a straight minimum-jerk movement: straightness 1, peak in the middle, one submovement', () => {
  const m = strokeMetrics(minJerk(0, 100, 100, 600, 100, 600));
  near(m.straightness, 1, 1e-6, 'straightness');
  near(m.peak_position, 0.5, 0.05, 'peak position');
  assert.equal(m.submovements, 1);
  near(m.distance_px, 500, 1e-6, 'distance');
  // Peak speed of minimum jerk is 1.875 x mean speed.
  near(m.peak_speed / m.mean_speed, 1.875, 0.1, 'peak/mean');
  assert.ok(m.end_speed_ratio < 0.1, 'decelerates into the target');
});

test('a primary movement plus a correction counts two submovements (Meyer et al. 1988)', () => {
  const a = minJerk(0, 100, 100, 560, 100, 500);
  const b = minJerk(504, 560, 100, 600, 100, 200).slice(1);
  assert.equal(strokeMetrics([...a, ...b]).submovements, 2);
});

test('constant-speed, script-like movement has no velocity variation', () => {
  const line = Array.from({ length: 40 }, (_, i) => [i * 16, 100 + i * 10, 300]);
  const m = strokeMetrics(line);
  assert.ok(m.speed_cv < 0.05, `speed cv ${m.speed_cv}`);
  assert.ok(m.end_speed_ratio > 0.9);
});

test('strokes are cut at pauses over 300 ms and short twitches are dropped', () => {
  const s = [...minJerk(0, 0, 0, 200, 0, 300), ...minJerk(1000, 200, 0, 205, 0, 100), ...minJerk(2000, 205, 0, 500, 0, 300)];
  assert.equal(strokes(s).length, 2);
});

test('a click is turned into a Fitts trial with the right D, W and ID', () => {
  const move = minJerk(0, 100, 300, 500, 300, 500);
  const samples = move;
  const st = strokes(samples).map(strokeMetrics);
  const ev = [
    ['ho', 480, 'like', 'p1'],
    ['pd', 600, 503, 301, 0, 'm', 0.5, 1, 1, 1, 'like', 'p1', [480, 280, 40, 40], 0, 80],
    ['pu', 690, 503, 301, 0, 'm', 1],
  ];
  const [c] = clickTrials(ev, samples, st);
  near(c.D, 400, 1e-6, 'D');
  near(c.W, 40, 1e-6, 'W (target extent along the approach)');
  near(c.ID, Math.log2(400 / 40 + 1), 1e-9, 'ID');
  near(c.MT, 600, 1e-6, 'MT');
  near(c.press_ms, 90, 1e-9, 'press');
  near(c.along, 3 / 40, 1e-9, 'endpoint along');
  assert.equal(c.hovered_first, true);
  assert.equal(c.overshoot, false);
});

test('typing: holds, inter-key intervals, rollover and backspace rate', () => {
  // "ab c" then a backspace; key b goes down before a is released (rollover).
  const kd = (t, cat, hand, id) => ['kd', t, cat, hand, id, 0, 0, 1, 'reply'];
  const ku = (t, cat, hand, id) => ['ku', t, cat, hand, id, 1];
  const ev = [
    ['pd', 0, 1, 1, 0, 'm', 0.5, 1, 1, 1, 'reply', 'p1', [0, 0, 10, 10], 0, 80],
    kd(400, 'l', 'L', 1), kd(500, 'l', 'L', 2), ku(520, 'l', 'L', 1), ku(580, 'l', 'L', 2),
    kd(700, 's', 'S', 3), ku(780, 's', 'S', 3), kd(900, 'l', 'L', 4), ku(990, 'l', 'L', 4),
    kd(1100, 'b', 'R', 5), ku(1180, 'b', 'R', 5),
  ];
  const t = typing(ev);
  assert.equal(t.keys, 5);
  assert.equal(t.hold_ms, 80);             // holds 120, 80, 80, 90, 80
  assert.deepEqual(t.iki, [100, 200, 200, 200]);
  assert.equal(t.rollover_rate, 0.25);     // 1 of 4 pairs
  assert.equal(t.backspace_rate, 0.2);
  assert.equal(t.pre_typing_ms, 400);
  assert.equal(t.iki_word_start_ms, 200);  // space -> letter
  assert.equal(t.iki_same_hand_ms, 100);   // L -> L
});

test('viewport time counts only inside the window, excluding overlays', () => {
  // Visible 1000-9000; window (phase 1) 0-5000; profile overlay 2000-3000.
  const ev = [['it', 0, 'p1', 40, 200, 0, 0, 0, 'u1'], ['iv', 1000, 'p1', 1], ['iv', 9000, 'p1', 0]];
  const { posts } = exposure(ev, [], 10000, [0, 5000], [[2000, 3000]]);
  assert.equal(posts[0].vt_ms, 3000);
});

test('viewport time counts only >= 50 % visible and excludes hidden-tab time', () => {
  const ev = [['it', 0, 'p1', 40, 200, 0, 0, 0, 'u1'], ['iv', 1000, 'p1', 0.75], ['iv', 6000, 'p1', 0.25], ['iv', 7000, 'p1', 1], ['iv', 9000, 'p1', 0]];
  const { posts } = exposure(ev, [[2000, 3000]], 10000);
  assert.equal(posts[0].vt_ms, 4000 + 2000);
});

test('burstiness: periodic is -1, bursty is positive (Goh & Barabasi 2008)', () => {
  near(burstiness([100, 100, 100, 100, 100]), -1, 1e-9, 'periodic');
  assert.ok(burstiness([10, 10, 10, 5000, 10, 10, 8000, 10]) > 0.3);
  assert.ok(memory([1, 2, 3, 4, 5, 6, 7, 8]) > 0.9);
});

test('AUC: 1 for perfectly separated groups, 0.5 for identical ones', () => {
  assert.equal(auc([5, 6, 7], [1, 2, 3]), 1);
  assert.equal(auc([1, 2, 3], [1, 2, 3]), 0.5);
  assert.equal(quantile([1, 2, 3, 4], 0.5), 2.5);
  const f = ols([1, 2, 3, 4], [3, 5, 7, 9]); near(f.a, 1, 1e-9, 'a'); near(f.b, 2, 1e-9, 'b');
});

test('action rhythm string and spontaneous engagement', () => {
  const ev = [['ph', 0, 'free'], ['act', 1000, 'like', 'p1', null], ['act', 1500, 'like', 'p2', null], ['ph', 5000, 'tasks'],
    ['act', 20000, 'comment_submit', 'p3', null], ['end', 90000]];
  const r = rhythm(ev, { free: [0, 5000], tasks: [5000, 90000], end: 90000 });
  assert.equal(r.action_string, 'LL:C');
  assert.equal(r.spontaneous_engagement, true);
});

test('coalesced samples are used when present, trusted mouse input only', () => {
  const ev = [['pm', 100, 10, 10, 0, 0, 0, 'm', 1, [-6, 4, 4, -3, 7, 7, 0, 10, 10]], ['pm', 116, 20, 20, 0, 0, 0, 'm', 0, []], ['pm', 132, 30, 30, 0, 0, 0, 't', 1, []]];
  assert.deepEqual(mouseSamples(ev).map(s => s[0]), [94, 97, 100]);
});

test('SapiMouse export uses its states and column layout', () => {
  const csv = toSapiMouse([['pm', 10, 1, 2, 0, 0, 0, 'm', 1, []], ['pd', 20, 1, 2, 0, 'm'], ['pm', 25, 3, 4, 1, 0, 0, 'm', 1, []], ['pu', 30, 3, 4, 0, 'm']]);
  assert.equal(csv, 'client timestamp,button,state,x,y\n10,NoButton,Move,1,2\n20,Left,Pressed,1,2\n25,Left,Drag,3,4\n30,Left,Released,3,4\n');
});

test('a session with no input yields empty measurements, not errors', () => {
  const { row } = analyzeSession({ meta: { id: 'x', cohort: 'human', network: {} }, device: null, end: null, recaptcha: [], batches: [{ seq: 0, events: [['ph', 0, 'free'], ['end', 1000]] }] });
  assert.equal(row.strokes, 0);
  assert.equal(row.key_hold_ms, null);
  assert.equal(row.hard_flags, '');
});

test('command-line options keep paths whole, including ones with "--" inside', async () => {
  const { parseArgs } = await import('../analysis/args.mjs');
  assert.deepEqual(parseArgs(['--data', 'C:/a--b/c d', '--device', 'any', '--flag', '--out=x--y']),
    { data: 'C:/a--b/c d', device: 'any', flag: true, out: 'x--y' });
});
