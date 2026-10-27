// Exports sessions in formats other tools already read. Files only, so the
// lab stays independent of whatever consumes them.
//
//   node analysis/export.mjs --format sapimouse [--data data] [--out analysis/out/sapimouse] [--cohort human]
//   node analysis/export.mjs --format trace     ...
//
// sapimouse  One CSV per session in the SapiMouse layout (Antal et al. 2021):
//            "client timestamp,button,state,x,y" with states Move / Pressed /
//            Released / Drag. Any SapiMouse-trained mouse-dynamics model, or
//            code written for that dataset, reads it unchanged.
// trace      One JSON per session in the input-trace layout the thesis's
//            feed lab exports (moves, downs, ups, wheels, keys, scrolls; times
//            in ms since page load), so sessions can be scored by the same
//            judges as the lab's runs.

import { readdir, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from './args.mjs';
import { fileURLToPath } from 'node:url';
import { loadSession } from './analyze.mjs';
import { flatten } from './metrics.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BUTTON = { 0: 'Left', 1: 'Middle', 2: 'Right' };

export function toSapiMouse(ev) {
  const rows = ['client timestamp,button,state,x,y'];
  let down = null;
  for (const e of ev) {
    if (e[0] === 'pm' && e[7] === 'm') {
      const co = e[9] || [];
      const pts = co.length >= 6 ? Array.from({ length: co.length / 3 }, (_, i) => [e[1] + co[3 * i], co[3 * i + 1], co[3 * i + 2]]) : [[e[1], e[2], e[3]]];
      for (const [t, x, y] of pts) rows.push(`${Math.round(t)},${down === null ? 'NoButton' : BUTTON[down] || 'Left'},${down === null ? 'Move' : 'Drag'},${Math.round(x)},${Math.round(y)}`);
    } else if (e[0] === 'pd' && e[5] === 'm') { down = e[4]; rows.push(`${Math.round(e[1])},${BUTTON[e[4]] || 'Left'},Pressed,${Math.round(e[2])},${Math.round(e[3])}`); }
    else if (e[0] === 'pu' && e[5] === 'm') { rows.push(`${Math.round(e[1])},${BUTTON[e[4]] || 'Left'},Released,${Math.round(e[2])},${Math.round(e[3])}`); down = null; }
  }
  return rows.join('\n') + '\n';
}

export function toTrace(ev) {
  const t = { origin: (ev.find(e => e[0] === 'clk') || [])[3] || null, moves: [], downs: [], ups: [], wheels: [], keys: [], scrolls: [] };
  for (const e of ev) {
    if (e[0] === 'pm' && e[7] === 'm') t.moves.push([e[1], e[2], e[3], e[8]]);
    else if (e[0] === 'pd') t.downs.push([e[1], e[2], e[3], e[4], e[9]]);
    else if (e[0] === 'pu') t.ups.push([e[1], e[2], e[3], e[4]]);
    else if (e[0] === 'wh') t.wheels.push([e[1], e[3], e[4]]);
    else if (e[0] === 'kd') t.keys.push([e[1], 'd', e[6]]);
    else if (e[0] === 'ku') t.keys.push([e[1], 'u', 0]);
    else if (e[0] === 'sc') t.scrolls.push([e[1], e[3]]);
  }
  return t;
}

async function main() {
  const args = parseArgs();
  const format = args.format;
  if (!['sapimouse', 'trace'].includes(format)) { console.log('usage: --format sapimouse|trace [--data DIR] [--out DIR] [--cohort NAME]'); process.exit(2); }
  const data = path.resolve(ROOT, args.data || 'data');
  const out = path.resolve(ROOT, args.out || `analysis/out/${format}`);
  await mkdir(out, { recursive: true });
  let n = 0;
  for (const id of (await readdir(path.join(data, 'sessions')).catch(() => [])).filter(x => /^[a-f0-9]{32}$/.test(x))) {
    const s = await loadSession(path.join(data, 'sessions', id));
    if (!s.meta || (args.cohort && s.meta.cohort !== args.cohort)) continue;
    const ev = flatten(s.batches);
    const name = `${s.meta.cohort}_${id}`;
    if (format === 'sapimouse') await writeFile(path.join(out, name + '.csv'), toSapiMouse(ev));
    else await writeFile(path.join(out, name + '.json'), JSON.stringify(toTrace(ev)));
    n++;
  }
  console.log(`${n} session(s) -> ${out}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(e => { console.error(e); process.exit(1); });
