# Vendored detectors

Third-party bot and fingerprint detectors, served by `server.mjs` under
`/vendor/` so the lab can be judged by tools other than its own panel. Copied
unmodified; each keeps its own licence.

| Folder | Project | Version | Licence |
|---|---|---|---|
| `botd/` | [FingerprintJS BotD](https://github.com/fingerprintjs/BotD) | npm `@fingerprintjs/botd@2.0.0` (`dist/botd.esm.js`) | MIT (`botd/LICENSE`) |
| `creepjs/` | [CreepJS](https://github.com/abrahamjuliot/creepjs) | `docs/` build at commit `10aa6724cd33a1015db1574211890518cd04f0cc` | MIT (`creepjs/LICENSE`) |
| `rebrowser/` | [rebrowser-bot-detector](https://github.com/rebrowser/rebrowser-bot-detector) | `main` as of 2026-10-11 | MIT (declared in its `package.json`; the repo has no LICENSE file) |

To update one, replace its folder with the new release and change the row above.
