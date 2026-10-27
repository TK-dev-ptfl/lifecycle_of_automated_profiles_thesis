# Data dictionary

Everything Social Lab records, field by field. Each item has:
- **Tells**: what the value measures;
- **RQ**: which research question in [STUDY.md](STUDY.md) needs it;
- the code that produces it.

An item that served no question would not be here; see the last section for what was
left out on purpose. Reference keys are in [REFERENCES.md](REFERENCES.md).

Storage: `data/sessions/<session id>/`, one folder per session, while the session is
being recorded.

With `DATA_REPO` set (the Railway setup), each session is sealed when it ends:
- **when:** at the end, after 30 min without activity, or on server shutdown;
- **how:** gzip, then AES-256-GCM with a fresh key wrapped by the researcher's RSA
  public key (`server/seal.mjs`);
- **where:** uploaded to the private data repository as
  `sessions/<2 hex>/<sha256(deletion code)>.sle`;
- the local folder is then deleted.

The server cannot decrypt what it uploaded. `analysis/decrypt.mjs` restores the folders
below on the researcher's machine.

| File | Written | Content |
|---|---|---|
| `meta.json` | at consent; updated at the end | consent, cohort, network signals |
| `events.ndjson` | every 3 s | input and page events, in batches |
| `device.json` | once, seconds after consent | browser, machine and consistency snapshot |
| `recaptcha.ndjson` | per verified token | reCAPTCHA v3 results |
| `end.json` | at the end | questionnaire and task timings |

## Conventions

- **t**: milliseconds since page load (`performance.now()`), 0.1 ms resolution as
  recorded. Browsers coarsen it further (STUDY.md, limitations).
- **Positions**: CSS pixels in the viewport (`clientX/Y`). Page coordinates are
  position + scroll (`sc`).
- **trusted**: `Event.isTrusted`, 1 when the browser's own input pipeline produced the
  event, 0 when a script dispatched it [whatwg_dom]. This is a fact about the event,
  not a statistic. Untrusted input in a "human" session means a script ran.
- **Target kind** (`data-t` on the element): `like`, `repost`, `save`, `share`, `cmt`
  (open comments), `reply` (comment field), `send`, `composer`, `post-btn`, `follow`,
  `author`, `profile-close`, `more`, `media`, `nav`, `trend`, `search`.
  **Target id** (`data-p`) is the post or user it belongs to.

## Events (`events.ndjson`)

Each line is `{seq, sent, recv, events}`:
- `seq`: batch number. Gaps mean a lost batch.
- `sent`: the client's wall clock.
- `recv`: the server's wall clock.
- `events`: an array of tuples. The first element is the code below.

Source: `public/js/recorder.js` unless stated.

### Pointer

| Code | Fields | Tells | RQ |
|---|---|---|---|
| `pm` | t, x, y, buttons, movementX, movementY, pointerType (`m` mouse, `t` touch, `p` pen), trusted, coalesced[] | The pointer trajectory. `coalesced` holds the samples the device reported between two dispatched events, flattened as (Δt, x, y); it is empty when there was only one. With them the trajectory is at the device's own rate (125–1000 Hz for mice), not the frame rate. Kinematics come from this [morasso1981spatial; flash1985coordination; meyer1988optimality]. `movementX/Y` are the device's relative deltas; position changes without them indicate synthetic input. | M1, M4, M5 |
| `pd` | t, x, y, button, pointerType, pressure, width, height, trusted, target kind, target id, target rect [x, y, w, h], screenX−clientX, screenY−clientY | The start of a press, *on what*, and *how big that target was*. Target size and position make each click a Fitts' law trial [fitts1954information; mackenzie1992fitts]. Pressure is 0.5 for a pressed mouse button by specification [w3c_pointerevents3]; touch reports contact size. The screen−client offset is the window position plus browser chrome; input injected through DevTools has been reported to leave it at 0. | M2, M3, M5, H3 |
| `pu` | t, x, y, button, pointerType, trusted | The end of a press. pu − pd is the press duration. | M3 |
| `pc` | t, pointerType | The browser took over the pointer (e.g. a touch scroll). Needed so cancelled touches are not read as long presses. | M5 |
| `ck` | t, x, y, detail, trusted, target kind, target id | The click itself. `detail` is the click count: 1 for a single click, 2 for a double click, **0 for a click with no pointer behind it** (keyboard activation, or `element.click()` from a script). | M3, H3 |
| `ho` | t, target kind, target id | The pointer entered a different target (or left all of them, empty kind). Tells whether a target was hovered before it was clicked. Real pointing passes over a target before pressing it; a teleported click does not. | M3 |

### Keyboard and text

| Code | Fields | Tells | RQ |
|---|---|---|---|
| `kd` | t, category, hand, key slot, modifiers, repeat, trusted, field | A key went down. **The key itself is not recorded.** Fields: **category** (`l` letter, `d` digit, `s` space, `p` punctuation, `b` backspace, `x` delete, `e` enter, `t` tab, `a` arrow, `m` modifier, `u` IME/dead key, `o` other); **hand** (`L`/`R` by the key's physical position in touch-typing, `S` space); **key slot** (a per-session number for each physical key, so each press can be paired with its release); **modifiers** (bit mask: 1 shift, 2 ctrl, 4 alt, 8 meta); **field** (`reply`, `composer`, `search` or empty). Category gives word boundaries and corrections. Hand gives same-hand vs. alternating pairs [dhakal2018typing]. The slot gives hold times and rollover [killourhy2009keystroke; dhakal2018typing]. | K1–K4 |
| `ku` | t, category, hand, key slot, trusted | A key came up. | K1, K2 |
| `in` | t, inputType, field, inserted characters, field length, trusted | The field changed and how: typing, deleting, pasting, autocorrect or IME composition (`inputType`). **Only lengths**, never the text. Comparing inserted characters with key presses shows text that arrived without keys: paste, autofill, or a script setting the value. | K2, K3, H3 |
| `cp` | t, copy/cut/paste, field | Clipboard use. Paste explains text without keys. | K3 |

### Scrolling, attention, page

| Code | Fields | Tells | RQ |
|---|---|---|---|
| `wh` | t, deltaX, deltaY, deltaMode, trusted | One wheel or trackpad event. Mice send discrete notches of a fixed size (deltaMode 0 in Chrome, often ±100 px); trackpads send many small fractional deltas with inertia. Notch intervals and burst length are the wheel rhythm. | S1, M5 |
| `sc` | t, scrollX, scrollY | The page scroll position. Gives scroll speed and reading pauses, and is needed to convert any viewport position to a page position. | S2, R1, M4 |
| `se` | t, selected characters | Text selection outside input fields: some readers mark text as they read [rodden2008eyemouse]. Length only. | M4 |
| `vs` | t, 1 visible / 0 hidden | Tab switches. Hidden time is subtracted from viewport time and excluded from idle-hand measurements. | R1, M4 |
| `fo` | t, 1 / 0 | Window focus. Another window can hold focus while this page stays visible. | R1 |
| `rs` | t, innerWidth, innerHeight, devicePixelRatio, outerWidth, outerHeight | Viewport and window size at start and on every resize. Outer − inner is the browser chrome; zoom changes the DPR. | H1, M2 |
| `fr` | t, median frame interval, 95th percentile, frames, longest | Display refresh rate (16.7 ms = 60 Hz, 8.3 = 120, 6.9 = 144) and how steady it is, from `requestAnimationFrame`, every 300 frames. | H2 |
| `net` | t, round-trip ms, server clock − client clock ms | Round-trip time of each upload, and the clock offset (midpoint estimate). | N4 |
| `cnt` | t, mousemove total, pointermove total, untrusted total | Running totals. Browsers fire a pointer event for every mouse event; mouse events alone mean they were synthesised directly. | H3 |
| `clk` | t, Date.now(), performance.timeOrigin | Ties page time to wall-clock time. | (alignment) |
| `end` | t | Recording stopped. | (alignment) |

### What was shown and what was done (`public/js/feed.js`, `main.js`)

| Code | Fields | Tells | RQ |
|---|---|---|---|
| `seed` | t, seed | The content seed. `makeContent(seed)` regenerates the exact feed. | (reproducibility) |
| `it` | t, post id, words, characters, has image, comment count, feed position, author id | A post was rendered. Its length is what reading time is regressed on [brysbaert2019reading; grusky2017viewport]; position and author are what engagement choices are related to. | R1, R2, E2 |
| `ly` | t, post id, page top, height | Where the post sits on the page; re-emitted when its size changes (comments opened). With `sc` this gives each post's position in the viewport at any moment: the input of the Gaussian viewport attention model [grusky2017viewport], and of "is the cursor on the post being read". | R1, M4 |
| `iv` | t, post id, visible share (0, .25, .5, .75, 1) | Viewport exposure, recorded whenever the visible share crosses a quarter step. Viewport time is computed from this [lagun2016attention; grusky2017viewport]. | R1, R2, E1 |
| `act` | t, action, post id, extra | A social action: `like`/`unlike`, `repost`/`unrepost`, `save`/`unsave`, `share`, `comments_open`/`close`, `comment_submit` (extra: characters, words), `post_submit` (same), `follow`/`unfollow`, `profile_open` (extra: user), `profile_close`, `media_click`, `nav_click`, `trend_click`, `search_submit`, `more`. Gives the action sequence, inter-action intervals and burstiness [barabasi2005bursts; goh2008burstiness; nwala2023bloc]. | E1–E4 |
| `ph` | t, `free` / `tasks` | Phase boundaries. Phase 1 behaviour was not asked for; phase 2 was. | E4, design |
| `tk` | t, task id | A task was completed. | design |

## Device snapshot (`device.json`, `public/js/device.js`)

Taken once, right after consent. RQ-H1 uses the values themselves: their *joint*
distribution [laperdrix2016beauty; gomezboix2018hiding]. RQ-H3 uses the
`consistency` and `automation` groups: how often real people trip each check
[venugopalan2024fpinconsistent].

| Field | Tells |
|---|---|
| `browser.user_agent`, `ua_brands`, `ua_mobile`, `ua_platform`, `ua_high_entropy` (platform version, architecture, bitness, model, full version list) | What the browser claims to be, in both the classic string and User-Agent Client Hints. Real Chromium browsers keep them consistent; spoofed ones often update only one. |
| `browser.platform`, `vendor`, `languages`, `language` | Classic navigator values the UA must agree with. Languages also tie to the IP country (N3). |
| `browser.plugins`, `pdf_viewer`, `cookies`, `do_not_track`, `gpc` | Values that headless or stripped browsers report differently (e.g. 0 plugins on desktop), and privacy settings that explain other failures. |
| `machine.cores`, `memory_gb`, `touch_points` | Hardware the page can see. Must agree with workers and with the OS. |
| `machine.screen`, `dpr`, `inner`, `outer` | Display geometry; `800x600` and outer = inner are headless defaults. |
| `machine.webgl` (vendor, renderer, max texture, WebGL2) | The GPU, the attribute with the most identity-specific variety, and the one our own fingerprint layer was caught misreporting in workers. |
| `machine.media_devices` | *How many* microphones, speakers and cameras, without labels (no permission is requested). Zero of everything is a headless trait. |
| `input_capabilities` | `pointer: fine` / `coarse` and `hover` media queries: the device class the operating system reports. Cross-checks the questionnaire's device answer. |
| `preferences` | Dark mode, reduced motion, contrast, forced colours. Part of the joint distribution; reduced motion also changes scroll behaviour. |
| `locale` | Time zone and UTC offset: compared with the IP's time zone (N3). |
| `connection` | Network Information API (Chromium only): effective type, RTT estimate, downlink. Compared with measured RTT. |
| `consistency.worker_dedicated`, `worker_shared` | What a background thread reports: UA, cores, memory, languages, platform, GPU, time zone. |
| `consistency.worker_matches`, `shared_worker_matches`, `iframe` | Whether each of those agrees with the page. Disagreement is the signal of FP-Inconsistent [venugopalan2024fpinconsistent]. |
| `consistency.canvas_stable` | The same drawing rendered twice gives the same pixels. Canvas-randomising extensions make it differ. |
| `consistency.permission` | Notification permission vs. its query state; "denied" vs. "prompt" is a classic headless tell. |
| `automation.webdriver`, `leftovers`, `tampered`, `headless_ua`, `chrome_object` | Direct automation evidence: the WebDriver flag, globals left by Selenium/Puppeteer/Playwright/PhantomJS, built-ins whose source is no longer native, "Headless" in the UA, Chrome without `window.chrome`. |
| `automation.botd` | FingerprintJS BotD's verdict and which of its detectors fired [fingerprintjs_botd]. |

## Network (`meta.json` → `network`, `server/network.mjs`, `server/tls-fingerprint.mjs`)

| Field | Tells | RQ |
|---|---|---|
| `tls.ja4`, `tls.ja4_r` | JA4 fingerprint of the TLS ClientHello and its raw pre-hash form, per the FoxIO specification [foxio_ja4]. Identifies the TLS library: browsers vs. Python, Go, curl, Node. Recorded only when this server terminates TLS. | N1 |
| `tls.ja3`, `ja3_r` | JA3, for comparison with older data. Changes per connection for current Chrome, which randomises extension order; that itself identifies it. | N1 |
| `tls.alpn`, `tls_versions`, `grease`, `sni_present` | ALPN offers (h2 / http/1.1), TLS versions, GREASE use (browsers send GREASE; most libraries do not), whether a server name was sent. | N1 |
| `navigation_headers` | The headers of the page load itself: names **in order**, plus values for a whitelist (`user-agent`, `accept*`, `sec-ch-ua*`, `sec-fetch-*`, `upgrade-insecure-requests`, `priority`, …). Header order and casing are a property of the HTTP stack. | N2 |
| `api_headers` | The same for the consent request (a `fetch`, so different `sec-fetch-*` values). | N2 |
| `ip_network` | Country, time zone, autonomous system, ISP, and the hosting / proxy / mobile flags of the address, from ip-api.com [ip_api]. **The address itself is discarded.** | N3 |
| `behind_proxy` | The request came through a proxy that terminates TLS (e.g. Railway's edge). Then `tls` is empty and the header order is the proxy's, not the browser's: exclude those sessions from RQ-N1 and N2. | N1, N2 |
| `ip_sessions_today`, `ip_day_hash` | How many sessions came from the same address today, via a keyed hash whose key changes daily and is never written down. Catches repeat participation without being able to link days. | design |
| `webrtc` (optional) | Whether the public address WebRTC discovers matches the request's address. Only the yes/no outcome is stored. | N3 |

## reCAPTCHA (`recaptcha.ndjson`)

One line per token, requested on page load and on likes, comments, posts, follows,
every 2,500 px of scrolling, every 45 s while visible, and at finish (at most one per
8 s). Fields:
- `requested_action` vs. `action` (Google's echo);
- `score` (0.0 bot … 1.0 human);
- `success`, `hostname`, `challenge_ts`, `errors`;
- `client_t`: page time of the request.

RQ-X1. The score is never sent to the page.

## End (`end.json`)

- `survey`: the seven questionnaire answers (STUDY.md, design, step 4).
- `tasks`: milliseconds from the start of phase 2 to each task's completion, or
  `null` if not done.
- `phase_started`: wall-clock start of each phase.

## Deliberately not collected

| Not collected | Why not |
|---|---|
| Which keys were pressed | It would reconstruct what people typed. Category, hand and timing answer every keyboard question. |
| Text of comments and posts | Content is not what the study measures; lengths suffice. |
| IP address | Network type and a daily keyed hash answer N3 and repeat detection. |
| Canvas, WebGL or audio fingerprint hashes, font lists | They identify a device across sites and answer no question here. Canvas *stability within the session* (a boolean) is enough for H3. |
| Geolocation, battery, Bluetooth, USB, device labels | Need permissions or identify the person; no question needs them. |
| Cookies or storage from other sites | Not accessible, and not wanted. |
| Free-text questionnaire answers | Every question is multiple choice, so nothing identifying can be typed in. |
| Name, email, account | No question needs to know who someone is. |
| HTTP/2 fingerprint (SETTINGS and frame order) | Would need an HTTP/2 server; the lab serves HTTP/1.1. A known gap for RQ-N1. |
| CreepJS | Its full run takes several seconds of heavy computation in the participant's browser, enough to disturb the session being measured. It is run against bots in the backend's feed lab; for humans BotD plus the consistency checks cover H3. |
