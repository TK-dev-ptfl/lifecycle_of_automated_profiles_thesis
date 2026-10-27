// Command-line options as { name: value }: "--data DIR" -> { data: 'DIR' },
// a bare "--flag" -> { flag: true }. Values are taken whole, so paths with
// spaces or double dashes inside them survive.
export function parseArgs(argv = process.argv.slice(2)) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const m = argv[i].match(/^--([\w-]+)(?:=(.*))?$/);
    if (!m) continue;
    if (m[2] !== undefined) out[m[1]] = m[2];
    else if (i + 1 < argv.length && !argv[i + 1].startsWith('--')) out[m[1]] = argv[++i];
    else out[m[1]] = true;
  }
  return out;
}
