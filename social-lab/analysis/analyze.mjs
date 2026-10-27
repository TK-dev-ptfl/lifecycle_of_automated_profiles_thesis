// Turns collected sessions into tables and a summary.
//
//   node analysis/analyze.mjs [--data data] [--out analysis/out] [--device mouse]
//
// Writes:
//   out/sessions.csv  one row per session, every metric (docs/ANALYSIS.md)
//   out/strokes.csv   every aimed mouse movement           (RQ-M1)
//   out/clicks.csv    every mouse click as a Fitts trial   (RQ-M2, M3)
//   out/posts.csv     every post shown: exposure, actions  (RQ-R1, R2, E1, E2)
//   out/summary.md    the human reference ranges, pooled fits, and - when bot
//                     cohorts exist - how well each metric separates them
//
// "Human" means cohort=human AND the session finished. --device restricts the
// human reference to one reported input device (default: mouse), because a
// trackpad or touch screen moves differently and would widen every range.

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from './args.mjs';
import { fileURLToPath } from 'node:url';
import { analyzeSession } from './metrics.mjs';
import { median, quantile, auc, ols, round } from './stats.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export async function loadSession(dir) {
  const read = async (f, parse = JSON.parse) => { try { return parse(await readFile(path.join(dir, f), 'utf8')); } catch { return null; } };
  const lines = s => s.trim() ? s.trim().split('\n').map(l => JSON.parse(l)) : [];
  return {
    meta: await read('meta.json'), device: await read('device.json'), end: await read('end.json'),
    recaptcha: (await read('recaptcha.ndjson', lines)) || [], batches: (await read('events.ndjson', lines)) || [],
  };
}

const csvCell = v => v === null || v === undefined ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
const toCsv = rows => {
  if (!rows.length) return '';
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))];
  return [cols.join(','), ...rows.map(r => cols.map(c => csvCell(r[c])).join(','))].join('\n') + '\n';
};

// Metrics compared across cohorts in the summary: numeric, behavioural or
// technical, one value per session.
const SKIP = new Set(['session', 'cohort', 'run_label', 'study_version', 'natural_rating', 'tasks_done', 'idle_windows',
  'sessions_from_network_today', 'recaptcha_n', 'clicks', 'keys', 'strokes', 'posts_seen', 'read_fit_n', 'fitts_n', 'episodes',
  'free_phase_s', 'task_phase_s']);

export function summarize(rows, { device = 'mouse' } = {}) {
  const humans = rows.filter(r => r.cohort === 'human' && r.completed && (!device || r.device_reported === device));
  const cohorts = [...new Set(rows.map(r => r.cohort))].filter(c => c !== 'human');
  const numeric = Object.keys(rows[0] || {}).filter(k => !SKIP.has(k) && rows.some(r => typeof r[k] === 'number'));
  const lines = [];
  lines.push(`# Social Lab summary`, '', `Generated ${new Date().toISOString()}.`, '',
    `Sessions: ${rows.length} (${rows.filter(r => r.completed).length} finished). Cohorts: ${[...new Set(rows.map(r => r.cohort))].map(c => `${c} ${rows.filter(r => r.cohort === c).length}`).join(', ')}.`,
    `Human reference: ${humans.length} finished human sessions${device ? ` with reported device "${device}"` : ''}.`, '');
  if (humans.length < 20) lines.push(`> Fewer than 20 human sessions: ranges below are not yet a reference. See docs/STUDY.md, "Sample size".`, '');

  lines.push('## Human reference ranges', '', 'Median, interquartile range and the central 90 % across human sessions. Each row is one metric of docs/ANALYSIS.md.', '',
    '| Metric | n | Median | IQR | 5th-95th |', '|---|---|---|---|---|');
  const ranges = {};
  for (const k of numeric) {
    const v = humans.map(r => r[k]).filter(x => typeof x === 'number');
    if (!v.length) continue;
    ranges[k] = { lo: quantile(v, 0.025), hi: quantile(v, 0.975), n: v.length };
    const f = x => round(x, 3);
    lines.push(`| ${k} | ${v.length} | ${f(median(v))} | ${f(quantile(v, 0.25))} - ${f(quantile(v, 0.75))} | ${f(quantile(v, 0.05))} - ${f(quantile(v, 0.95))} |`);
  }

  for (const kind of ['hard_flags', 'consistency_failures']) {
    const counts = {};
    for (const r of humans) for (const f of String(r[kind] || '').split(' ').filter(Boolean)) counts[f] = (counts[f] || 0) + 1;
    lines.push('', `## ${kind === 'hard_flags' ? 'Automation flags' : 'Fingerprint consistency failures'} among humans`, '',
      kind === 'hard_flags' ? 'Each of these is meant to fire only for automation. The share of humans who trip it is its false-positive rate (RQ-H3).'
        : 'Same, for the individual consistency checks.', '');
    if (!Object.keys(counts).length) lines.push('None fired for any human session.');
    else { lines.push('| Flag | Humans | Share |', '|---|---|---|'); for (const [f, n] of Object.entries(counts).sort((a, b) => b[1] - a[1])) lines.push(`| ${f} | ${n} | ${round(n / humans.length, 3)} |`); }
  }

  return { lines, ranges, humans, cohorts, numeric };
}

/** Per session: how many metrics fall outside the human 2.5-97.5 % range.
 *  For human sessions their own value is left out of the range (leave one
 *  out), so humans are not judged against themselves. */
export function outsideHumanRange(rows, humans, numeric) {
  return rows.map(r => {
    const ref = humans.filter(h => h !== r);
    let checked = 0; const outside = [];
    for (const k of numeric) {
      if (typeof r[k] !== 'number') continue;
      const v = ref.map(h => h[k]).filter(x => typeof x === 'number');
      if (v.length < 10) continue;
      checked++;
      if (r[k] < quantile(v, 0.025) || r[k] > quantile(v, 0.975)) outside.push(k);
    }
    return { session: r.session, cohort: r.cohort, checked, outside: outside.length, outside_share: checked ? outside.length / checked : null, outside_metrics: outside.join(' ') };
  });
}

async function main() {
  const args = parseArgs();
  const data = path.resolve(ROOT, args.data || 'data');
  const out = path.resolve(ROOT, args.out || 'analysis/out');
  const device = args.device === 'any' ? null : (args.device || 'mouse');
  const ids = (await readdir(path.join(data, 'sessions')).catch(() => [])).filter(n => /^[a-f0-9]{32}$/.test(n));
  if (!ids.length) { console.log(`no sessions in ${data}`); return; }

  const rows = [], strokeRows = [], clickRows = [], postRows = [], pooled = { ID: [], MT: [], words: [], vt: [] };
  for (const id of ids) {
    const s = await loadSession(path.join(data, 'sessions', id));
    if (!s.meta || !s.batches.length) continue;
    const a = analyzeSession(s);
    rows.push(a.row);
    const tag = { session: id, cohort: s.meta.cohort };
    for (const st of a.strokes) strokeRows.push({ ...tag, ...Object.fromEntries(Object.entries(st).filter(([k]) => !['start', 'end'].includes(k)).map(([k, v]) => [k, round(v, 4)])) });
    for (const c of a.clicks) {
      clickRows.push({ ...tag, ...Object.fromEntries(Object.entries(c).map(([k, v]) => [k, typeof v === 'number' ? round(v, 4) : v])) });
      if (s.meta.cohort === 'human' && a.row.device_reported === (device || a.row.device_reported) && c.moved && c.D >= 2 * c.W && c.MT > 0) { pooled.ID.push(c.ID); pooled.MT.push(c.MT); }
    }
    for (const p of a.posts) {
      postRows.push({ ...tag, post: p.id, words: p.words, media: p.media, index: p.index, vt_ms: round(p.vt_ms, 0), seen: p.first_visible !== null,
        liked: p.actions.some(x => x[1] === 'like'), commented: p.actions.some(x => x[1] === 'comment_submit'), actions: p.actions.map(x => x[1]).join(' ') });
      if (s.meta.cohort === 'human' && !p.media && p.vt_ms >= 1000 && p.vt_ms <= 120000) { pooled.words.push(p.words); pooled.vt.push(p.vt_ms / 1000); }
    }
  }

  const { lines, humans, cohorts, numeric } = summarize(rows, { device });
  const fitts = ols(pooled.ID, pooled.MT), read = ols(pooled.words, pooled.vt);
  lines.push('', '## Pooled fits (human sessions)', '',
    fitts ? `- **Fitts' law** (RQ-M2), Shannon form MT = a + b·log2(D/W + 1) over ${fitts.n} clicks: a = ${round(fitts.a, 1)} ms, b = ${round(fitts.b, 1)} ms/bit, R² = ${round(fitts.r2, 3)}.` : '- Fitts\' law: not enough clicks yet.',
    read ? `- **Viewport time vs words** (RQ-R1) over ${read.n} text posts: ${round(read.a, 2)} s + ${round(read.b, 3)} s/word, R² = ${round(read.r2, 3)}; the slope implies ${round(60 / read.b, 0)} words/min (Brysbaert 2019: 238 for silent reading of non-fiction).` : '- Reading fit: not enough posts yet.');

  if (cohorts.length && humans.length) {
    lines.push('', '## Separation from humans (RQ-V1)', '',
      'AUC of each metric, human sessions vs each other cohort (Mann-Whitney; 0.5 = indistinguishable, 0 or 1 = perfectly separated, in either direction). Sorted by how far from 0.5.', '');
    for (const c of cohorts) {
      const other = rows.filter(r => r.cohort === c);
      const res = numeric.map(k => ({ k, a: auc(other.map(r => r[k]), humans.map(r => r[k])) })).filter(x => x.a !== null)
        .sort((x, y) => Math.abs(y.a - 0.5) - Math.abs(x.a - 0.5));
      lines.push(`### ${c} (${other.length} sessions)`, '', '| Metric | AUC | Median (cohort) | Median (human) |', '|---|---|---|---|');
      for (const { k, a } of res.slice(0, 25)) lines.push(`| ${k} | ${round(a, 3)} | ${round(median(other.map(r => r[k])), 3)} | ${round(median(humans.map(r => r[k])), 3)} |`);
      lines.push('');
    }
  }
  const outside = outsideHumanRange(rows, humans, numeric);
  if (humans.length >= 10) {
    lines.push('## Sessions outside the human range', '', 'Share of metrics outside the human 2.5-97.5 % range (humans scored leave-one-out). A human sits outside about 5 % of ranges by construction.', '',
      '| Cohort | Sessions | Median share outside |', '|---|---|---|');
    for (const c of ['human', ...cohorts]) { const v = outside.filter(o => o.cohort === c).map(o => o.outside_share); lines.push(`| ${c} | ${v.length} | ${round(median(v), 3)} |`); }
  }

  await mkdir(out, { recursive: true });
  const byId = Object.fromEntries(outside.map(o => [o.session, o]));
  await writeFile(path.join(out, 'sessions.csv'), toCsv(rows.map(r => ({ ...r, outside_human_share: round(byId[r.session]?.outside_share, 3), outside_metrics: byId[r.session]?.outside_metrics }))));
  await writeFile(path.join(out, 'strokes.csv'), toCsv(strokeRows));
  await writeFile(path.join(out, 'clicks.csv'), toCsv(clickRows));
  await writeFile(path.join(out, 'posts.csv'), toCsv(postRows));
  await writeFile(path.join(out, 'summary.md'), lines.join('\n') + '\n');
  console.log(`${rows.length} sessions -> ${out}\n  sessions.csv, strokes.csv (${strokeRows.length}), clicks.csv (${clickRows.length}), posts.csv (${postRows.length}), summary.md`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(e => { console.error(e); process.exit(1); });
