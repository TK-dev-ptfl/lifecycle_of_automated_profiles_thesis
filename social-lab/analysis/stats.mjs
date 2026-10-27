// Small statistics toolkit, no dependencies. Every function returns null
// rather than NaN when there is not enough data, so a missing measurement is
// an empty CSV cell, not a number that looks real.

export const finite = a => a.filter(v => typeof v === 'number' && Number.isFinite(v));
export const mean = a => { a = finite(a); return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null; };
export const sd = a => {
  a = finite(a); if (a.length < 2) return null;
  const m = mean(a); return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1));
};
export const cv = a => { const m = mean(a), s = sd(a); return m && s !== null ? s / m : null; };

/** Quantile with linear interpolation (type 7, the R / numpy default). */
export function quantile(a, q) {
  a = finite(a).sort((x, y) => x - y);
  if (!a.length) return null;
  const h = (a.length - 1) * q, lo = Math.floor(h);
  return a[lo] + (h - lo) * ((a[Math.min(lo + 1, a.length - 1)]) - a[lo]);
}
export const median = a => quantile(a, 0.5);

/** Burstiness B = (sigma - m) / (sigma + m) of inter-event times
 *  (Goh & Barabasi 2008, eq. 1): -1 periodic, 0 Poisson, -> 1 bursty. */
export function burstiness(intervals) {
  const m = mean(intervals), s = sd(intervals);
  return m !== null && s !== null && s + m > 0 ? (s - m) / (s + m) : null;
}

/** Memory coefficient M (Goh & Barabasi 2008, eq. 4): correlation between
 *  consecutive inter-event times. */
export function memory(intervals) {
  const a = finite(intervals); if (a.length < 4) return null;
  const x = a.slice(0, -1), y = a.slice(1);
  const mx = mean(x), my = mean(y), sx = sd(x), sy = sd(y);
  if (!sx || !sy) return null;
  let s = 0; for (let i = 0; i < x.length; i++) s += (x[i] - mx) * (y[i] - my);
  return s / ((x.length - 1) * sx * sy);
}

/** Ordinary least squares y = a + b x, with R^2. */
export function ols(xs, ys) {
  const pts = xs.map((x, i) => [x, ys[i]]).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  if (pts.length < 3) return null;
  const mx = mean(pts.map(p => p[0])), my = mean(pts.map(p => p[1]));
  let sxy = 0, sxx = 0, syy = 0;
  for (const [x, y] of pts) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2; }
  if (!sxx) return null;
  const b = sxy / sxx, a = my - b * mx;
  return { a, b, r2: syy ? (sxy * sxy) / (sxx * syy) : null, n: pts.length };
}

/** Mann-Whitney AUC: probability that a random value from `pos` exceeds one
 *  from `neg` (ties count half). 0.5 = the two groups are indistinguishable. */
export function auc(pos, neg) {
  pos = finite(pos); neg = finite(neg);
  if (!pos.length || !neg.length) return null;
  const all = [...pos.map(v => [v, 1]), ...neg.map(v => [v, 0])].sort((a, b) => a[0] - b[0]);
  let rankSum = 0;
  for (let i = 0; i < all.length;) {
    let j = i; while (j < all.length && all[j][0] === all[i][0]) j++;
    const avg = (i + j + 1) / 2;
    for (let k = i; k < j; k++) if (all[k][1]) rankSum += avg;
    i = j;
  }
  return (rankSum - pos.length * (pos.length + 1) / 2) / (pos.length * neg.length);
}

export const round = (v, d = 3) => (typeof v === 'number' && Number.isFinite(v) ? Math.round(v * 10 ** d) / 10 ** d : null);
