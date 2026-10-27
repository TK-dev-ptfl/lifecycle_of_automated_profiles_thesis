# Measuring how human the behaviour algorithms are

This is the test environment for the question "does `app.behaviour` drive a browser the
way a person does?". It covers what each part measures, why that measurement is valid
(literature, specifications and our own validation against recorded data), what it
cannot tell you, and how to run an experiment whose numbers can go into the thesis.

Supports thesis sections 3.6–3.7 (environment, algorithms) and chapter 4 (methodology).
BibTeX keys in brackets refer to `literatura.bib`.

Code: `backend/tests/behaviour/test_env/` (lab, classifier training, validation, CLI),
`backend/app/behaviour/evaluation/` (judges used at run time),
`backend/app/services/behaviour_run_service.py` (scenarios, the run itself, comparison).

---

## 1. What "human-like" means here

Operationally: **a session driven by the algorithm is human-like if independent
judges cannot tell it apart from sessions driven by people, when both perform the same
task in the same browser.**

Four things follow from that definition, and each is built into the environment:

1. **A human reference.** Without sessions by real people there is nothing to be "like".
   The *manual* scenario records them, in the same lab and the same browser.
2. **A negative control.** A judge that passes the algorithm is only evidence if it
   fails something that is plainly a bot. The *robotic* scenario is that bot.
3. **Independent judges.** Judges the algorithm was not tuned against. Otherwise
   the result only says the algorithm learned the test.
4. **Only one variable changes.** Identity, fingerprint, proxy and task are identical
   across the three styles, so a difference in score can only come from how the page
   was driven.

This is the standard positive/negative control design of an experiment. In
bot-detection research it is how detectors themselves are evaluated: human traffic
vs. bot traffic of known provenance [iliou2021webbots; acien2022becaptcha; chu2013blog].

## 2. The three drivers

| Style | Scenario key | Who drives | Role |
|---|---|---|---|
| manual | `feed-lab-manual` | a person, with a real mouse and keyboard | human reference (positive control) |
| human | `feed-lab` | `app.behaviour` Actor with the identity's profile | the thing being measured |
| robotic | `feed-lab-bot` | `app.behaviour.robotic.RoboticActor` | negative control |

All three perform **the same task** (`FeedTask` in `behaviour_run_service.py`):
read 8 posts, like 3 of them, write one comment and publish one post. These cover
the thesis's three bot types (2.1.3): reading = scraping, liking = engagement,
commenting/posting = messaging.

The task matters. Until 2026-10-16 the human-like scenario only read and scrolled,
so 6 of the lab's 19 behaviour checks never ran for it, while the robotic control was
graded on all of them. That comparison favoured the algorithm for free. A test now pins
this (`test_scenarios.py`), and runs carry `protocol: 2` so results from the old
protocol are never pooled with new ones.

The robotic control does what a naive automation script does. Each habit targets a
specific check (see `robotic.py`'s docstring):
- it acts the instant the page loads;
- it moves in straight lines in one burst (Playwright `mouse.move(steps=8)`);
- it clicks dead centre with no hold;
- it scrolls by script on a fixed beat;
- it fires one JavaScript `click()`;
- it types at a fixed 40 ms rhythm with no key hold;
- it fills one field without typing.

## 3. The lab: Hearth feed

`test_env/feed-lab/` is a dummy social feed served by `server.mjs` (Node 18+, no
dependencies) on `http://localhost:8080`. It has posts, likes, reposts, comments, a
composer, follows and infinite scroll. It is local, so no real platform or person is
touched (thesis 2.5.3).

The page carries its own judge (a "Session check" panel) and records a full input trace.
It is designed to judge **the session it is in**, the way a production anti-bot script
does, rather than a replay afterwards.

### 3.1 Input trace

Every `mousemove`, `mousedown`/`mouseup`, `wheel`, `keydown`/`keyup` and `scroll` is
recorded with its timestamp, position, and `isTrusted` flag. Key identities are not
recorded, only timing. The runner reads the trace with `window.__hearthTrace()` *before*
anything else touches the page, so the measurement does not add input to the session
it measures. `window.__hearthReport()` returns every check without the runner having
to click the detail tabs, which matters most in manual sessions.

### 3.2 Behaviour checks (in-page)

Each check reads one signal. The table gives the basis for the signal and what our
validation against recorded humans and bots showed (§6.1).

| Check | Signal | Basis | Validation |
|---|---|---|---|
| Events come from real input | any event with `isTrusted = false` | DOM Standard: only user-agent-generated events are trusted [whatwg_dom] | spec fact |
| Pointer events present | mouse events without matching pointer events | Pointer Events spec: input devices fire both [w3c_pointerevents3] | spec fact |
| Time before first action | first input < 300 ms after load | heuristic: perception and decision take time | not validated |
| Clicks land where the cursor was | mousedown > 6 px from the last mousemove | a real button press happens where the pointer is; synthetic clicks often skip the travel | input-pipeline fact |
| Hover before click | button clicked without `mouseover` first | as above | input-pipeline fact |
| Curved, imperfect paths | share of strokes with straightness > 0.995 | human aimed movements are near-straight but not ruler-straight [morasso1981spatial; flash1985coordination] | humans fail 0 %; synthetic bots 25 % |
| Speed rises and falls | median within-stroke speed CV | bell-shaped velocity profile of aimed movement [morasso1981spatial; flash1985coordination] | humans fail 0 %; weak against real bots |
| Small direction jitter | median heading change per step | motor noise | fails no recorded human or bot; catches only perfectly straight script moves |
| Plausible top speed | fastest single step > 40 px/ms | physical limit | SapiMouse humans fail 0.8 %; Iliou humans 35 % (dataset artifact, §6.1) |
| Imprecise aim | median distance from button centre | endpoint scatter around a target grows with movement speed [fitts1954information; wobbrock2008error] | not validated (no dataset) |
| Natural press length | median mousedown→mouseup | a physical button press takes tens of milliseconds; our SapiMouse measurement: median 80 ms, 5th–95th percentile 47–136 ms | humans fail 1.6 % |
| Keystroke rhythm | median key hold; CV of keydown→keydown gaps | keystroke dynamics [killourhy2009keystroke] | CMU humans fail 0 %; Playwright `type(delay=40)` fails 100 % |
| Text arrives through keys | characters inserted vs keys pressed | `fill()` and script assignment insert text with no key events | spec fact |
| Scrolling follows input | scroll events with no wheel/key/touch/drag within 1.5 s | `window.scrollBy` scrolls with no input | spec fact |
| Pauses to read | reading pauses per 1000 px scrolled | heuristic | not validated |
| Uneven wheel timing | CV of wheel-notch intervals | heuristic | not validated |
| Screen and page coordinates differ | `screenX == clientX` with browser chrome present | reported behaviour of CDP-injected mouse events | not verified here; cannot fire headless (no window chrome) |
| Movement deltas reported | `movementX/Y` zero while moving | reported behaviour of CDP-injected mouse events | passes for Playwright 1.62 in our runs |
| Hardware sampling | `getCoalescedEvents()` never has more than 1 sample | real mice report faster than the frame rate and the browser coalesces [w3c_pointerevents3] | warns on every Playwright run in our tests; weak (trackpads too) |

The score is 100 minus a penalty per failed check, and one third of that penalty per
warning. It only appears once 4 or more checks are active.

**Reading the score.** Use the **behaviour** score for human-likeness. The *overall*
number is a weighted mean of behaviour, fingerprint and reCAPTCHA, capped at 10 above
the lowest of them when one is under 35. A fingerprint problem therefore drags it down
whatever the behaviour.

### 3.3 Fingerprint checks (in-page)

These are not about behaviour. They check that the browser is presented consistently
(automation globals, webdriver flag, headless markers, plugins, OS/engine agreement,
time zone, frames vs. page, workers vs. page, untouched built-ins), plus a verdict from
FingerprintJS BotD [fingerprintjs_botd].

Inconsistency is the main signal commercial detectors use [venugopalan2024fpinconsistent;
vastel2020fpcrawlers; jonker2019fpbot]. These checks are there to show the fingerprint is
**held constant** across the three styles. They are not part of the behaviour measurement.

On 2026-10-16 the worker comparison was extended. It now runs in a **shared** worker as
well as a dedicated one, and compares the WebGL renderer too. Before that, CreepJS caught
an inconsistency the lab missed (§7).

### 3.4 reCAPTCHA v3

With keys in `feed-lab/.env`, Google's score-based reCAPTCHA (0.0 bot – 1.0 human)
[google_recaptcha_v3] is requested on load, on likes, reposts, comments, posts and follows,
and on every 2,500 px of scrolling. Tokens are verified server-side.

This is a **realistic commercial judge, not a measure of behaviour.** Its score depends
heavily on cookies, Google account history and IP reputation. It has been beaten by a
cursor-moving RL agent [akrout2019recaptcha], and CAPTCHA effectiveness in practice is
contested [searles2023captcha]. In our runs it gave 0.9 to the human-like run and to the
robotic control alike. Report it, but draw no behavioural conclusion from it.

## 4. Independent judges after the session

These run in fresh tabs of the same browser context after the session, so they see
the same fingerprint and proxy. None of them can fail the run; a broken judge is recorded
as broken.

### 4.1 Mouse-movement classifier

`app/behaviour/evaluation/mouse_model.py`, trained by `test_env/bot_model/train.py`.
This is the strongest behavioural judge in the environment and the one to report as the
main result.

- **Lineage.** Mouse dynamics as a behavioural biometric [ahmed2007mouse], used for bot
  detection by passive monitoring of mouse and keystroke input [chu2013blog]. Web bots
  are detected by their mouse movement even when they imitate humans [iliou2021webbots].
  Function-based synthetic trajectories serve as bot data [acien2022becaptcha].
- **Data.** Humans: SapiMouse (120 people) [antal2021sapimouse] and the human sessions
  of the Iliou et al. dataset. Bots: Iliou *moderate* and *advanced* bots (real
  automation tools), and synthetic trajectories re-implemented from BeCAPTCHA-Mouse
  Method 1 on SapiMouse's own strokes.
- **Unit.** One stroke, i.e. a continuous movement cut at pauses over 300 ms. Kinematics
  are computed on a path resampled to 16 ms, so differences in recording rate between
  datasets and Playwright do not become a feature. The 23 features
  (`mouse_features.py`) describe path geometry (straightness, maximum deviation),
  the velocity profile (mean, CV, peak position, start/end speed ratios, number of
  speed peaks), and higher derivatives (acceleration and jerk spread) and heading
  changes. These are the quantities in which human aimed movement is characteristic
  [morasso1981spatial; flash1985coordination].
- **Model.** A random forest [breiman2001rf; pedregosa2011sklearn]: 120 trees, depth
  ≤ 14, class-balanced. A session's score is the mean bot probability of its strokes,
  and the verdict is given at 0.5 with at least 5 strokes.
- **Independence.** It is never trained on anything `app.behaviour` or the robotic
  control produced. That rule is written in train.py and the README.

Held-out results (`bot_model/REPORT.md`, 2026-10-16):

| Test | Session AUC | Session accuracy |
|---|---|---|
| Iliou published test split, humans vs moderate bots | 1.0 | 1.0 |
| Iliou published test split, humans vs advanced bots | 1.0 | 1.0 |
| SapiMouse unseen users vs synthetic | 1.0 | 1.0 |
| **Cross-dataset**: trained without Iliou, tested on all Iliou (advanced bots) | 0.997 | 0.993 |
| **Ablation**: without the 4 raw-timing features (advanced bots) | 1.0 | – |

The cross-dataset row is the important one. A model that never saw that recorder,
site, people or bots still separates them, so it has learned movement rather than the
recording setup. The ablation shows the same thing from the other side: dropping every
feature computed on raw event timing leaves the results intact.

**Export parity.** The backend walks the exported trees in plain Python, so scoring
needs no scikit-learn. Training checks that this reproduces scikit-learn on 2,000
held-out strokes. On 2026-10-16 it did not: thresholds were exported rounded to 6
digits, and features were compared in float64 while scikit-learn uses float32. Values
next to a threshold went down the wrong branch, up to 0.006 off. Both are fixed;
the maximum difference is now 7×10⁻⁶.

### 4.2 rebrowser-bot-detector
Tests for leaks specific to Puppeteer and Playwright [rebrowser_botdetector]:
- `Runtime.enable`;
- source URLs in stack traces;
- main-world execution;
- `__pwInitScripts`;
- `exposeFunction`;
- viewport and user agent.

The runner makes the calls the detector asks for, in the same way it reads the lab's
score, so the result describes this runner. Expected result for every style:
`sourceUrlLeak` and `mainWorldExecution`. That comes from plain Playwright's
`page.evaluate`, which is identical across styles, so it does not affect the
comparison. Identities that present **Edge** also fail its `useragent` test: it expects
"Google Chrome" among the client-hint brands. That is a fingerprint property, the same
for every style.

### 4.3 CreepJS
Headless, like-headless and stealth ratings, plus "lies": APIs whose behaviour shows they
were tampered with, including in worker scope [creepjs]. This is a fingerprint judge,
like 3.3.

### 4.4 Public detector pages (opt-in, proxy only)
bot.sannysoft.com (parsed), BrowserScan, Pixelscan and BrowserLeaks (screenshot plus
keyword lines). Off by default because they log visitors.

### 4.5 Raw input statistics
`trace_stats.py` reports the underlying numbers (stroke straightness, speed CV, end-speed
ratio, click and key hold, key-gap CV, wheel-gap CV, reading pauses), computed the same
way for every style. Where judges disagree, these show why.

## 5. Libraries and tools

| Component | Version | Used for |
|---|---|---|
| Playwright for Python [playwright] | 1.62.0 | driving the browser; CDP input |
| installed Chrome / Edge | per identity | the real browser the fingerprint claims (`fingerprint.py`) |
| scikit-learn [pedregosa2011sklearn] | 1.9.1 | training only (`requirements-eval.txt`) |
| numpy | 2.5.4 | training only |
| FingerprintJS BotD | 2.0.0 | in-page second opinion (vendored, MIT) |
| CreepJS | commit `10aa6724` | post-session judge (vendored, MIT) |
| rebrowser-bot-detector | `main`, 2026-10-11 | post-session judge (vendored, MIT) |
| Node.js | ≥ 18 | lab server |

| Dataset | Licence | Used for |
|---|---|---|
| SapiMouse [antal2021sapimouse] | none stated; cite | classifier humans; validation (paths, clicks) |
| Iliou et al. Web Bot Detection [iliou2021webbots] | CC BY-NC-SA 2.0 | classifier humans and bots; validation |
| CMU keystroke benchmark [killourhy2009keystroke] | free for research; cite | validation of keystroke check; calibration of key hold |

Download locations: `test_env/bot_model/README.md`. CMU:
`https://www.cs.cmu.edu/~keystroke/DSL-StrongPasswordData.csv` → `bot_model/data/cmu_keystroke/`.

## 6. Does the environment measure the right thing?

### 6.1 The lab's checks on recorded humans and bots
`test_env/validate_lab_checks.py` runs the lab's own rules, ported line for line from
`index.html`, over the public recordings. Full tables are in `test_env/VALIDATION.md`.

| | Humans failing | Bots failing |
|---|---|---|
| Any of the 4 path checks | SapiMouse 0.8 %, Iliou 34.9 % | Iliou moderate 4.4 %, advanced 2.4 %, synthetic 25.8 % |
| Natural press length | SapiMouse 1.6 % | (no recorded bot clicks) |
| Keystroke rhythm | CMU 0.0 % | Playwright `type(delay=40)` 100 % |

What this means:

- **The click and keystroke checks are well calibrated.** Real people pass them and
  naive automation fails them.
- **The path checks are a floor, not a discriminator.** They catch straight-line,
  constant-speed script movement. They do not catch real bot tools that already curve
  their paths: Iliou's advanced bots pass them 97.6 % of the time. A human-like result
  on the lab panel therefore shows only that the algorithm is not naive. The classifier
  (§4.1) is the judge that separates humans from *good* bots.
- **"Plausible top speed" is fragile.** It takes the single fastest step. On Iliou humans
  that step is a 300–1000 px jump within 2–15 ms, which is almost certainly the dataset
  logging page coordinates through scrolls, not motion. The lab uses viewport coordinates,
  and SapiMouse humans fail it only 0.8 % of the time, so the threshold was left as is.
  Treat a failure of this check alone with caution.

### 6.2 End-to-end: the controls separate
Same identity, same fingerprint, same task, headless, no proxy, 2026-10-16:

| | human-like (`feed-lab`) | robotic (`feed-lab-bot`) |
|---|---|---|
| lab behaviour score | 98 (19 signals, 0 bot signals) | 0 (17 signals, 7 bot signals) |
| mouse classifier | human, bot probability 0.318 (28 strokes) | bot, bot probability 0.681 (5 strokes) |
| stroke straightness (median) | 0.944 | 1.000 |
| stroke speed CV (median) | 0.824 | 0.254 |
| end-speed ratio (median) | 0.083 (decelerates into the target) | 0.570 |
| click hold (median) | 92.6 ms | 2.7 ms |
| key hold (median) / key-gap CV | 66 ms / 0.50 | 45 ms / 0.03 |
| reCAPTCHA v3 | 0.9 | 0.9 |

Run ids `21d9a496` and `5b3ebaa0` in `test_env/runs/`, identity `verify-1`.

Across the protocol-2 verification runs (identities `verify-2` and `verify-3`, one run
per style each), `compare_runs.py --aggregate` gives:
- classifier bot probability: median 0.39 for the algorithm vs 0.74 for the robotic control;
- lab behaviour score: 98 vs 0;
- click hold: 136 ms vs 2.8 ms.

That is 2 runs per group, enough to show the pipeline works end to end, but not a
result. §8 describes the run you can report.

### 6.3 It catches regressions
The first like-for-like run exposed a real bug in the algorithm. `keyboard.press(char)`
releases every key in the same instant it goes down, so the lab measured a **2 ms**
median key hold and failed *Keystroke rhythm*, dropping behaviour from 98 to 68.

The fix is in `primitives/keyboard.py`. Hold times are now drawn log-normally around a
per-identity median (`BehaviourProfile.key_hold_ms`, spread 45–142 ms), calibrated on
the CMU benchmark: median 86 ms, 5th–95th percentile 49–145 ms, σ ≈ 0.34. After the fix
the check passes. A unit test pins it.

A second run, with an identity whose viewport is only 752 px tall, exposed another bug.
Opening a post's comments pushed the comment field below the fold. `ClickOn` aimed
there, the cursor travel is clamped to the viewport, and the click landed on something
else. `TypeInto`'s verification then caught that the field was still empty, and the run
failed rather than reporting a comment that was never written.

The simulator had not caught this because the two adapters disagree. The simulator
counts an off-screen element as not visible; Playwright counts it as visible, because
`is_visible` only checks CSS. Fixed in two places:
- the task scrolls to every target before acting on it (pinned by a test);
- `ClickOn` now refuses a target off screen instead of misclicking.

## 7. Known limitations

- **The human baseline still has to be recorded.** [social-lab/](../social-lab/README.md) is built to collect it at scale, from consenting participants, on a public site. No manual sessions exist yet. The
  algorithm's classifier probability of 0.32 means "below the threshold", not "like
  people in this lab", until there are manual runs to compare against (§8).
- **Only mouse movement has a trained judge.** Keystrokes, clicks and scrolling are judged
  by the lab's rules, which are validated (keys, clicks) or heuristic (scroll, reading).
- **CDP input is one sample per frame.** Real mice report faster, and the browser
  coalesces their samples. Every Playwright-driven session gets *Hardware sampling: warn*,
  and no algorithm can change that: it is a property of the input channel, not of the
  behaviour.
- **Dataset domain shift.** SapiMouse is a drag-and-drop desktop task and Iliou are web
  pages; the lab is a feed. Path statistics transfer approximately.
- **Headless artifacts.** Headless runs show `HeadlessChrome` in shared workers. Run
  experiments **headful**.
- **reCAPTCHA on localhost** says little; see 3.4.
- **Small n.** One run per condition is an anecdote. See §8.
- **Simulator vs. browser.** `SimulatedEnvironment` treats off-screen elements as
  invisible and Playwright does not (§6.3). An algorithm that passes in the simulator
  can still misbehave on a short viewport, so test on several viewport sizes. The
  identities already give you several.

### Issues found in the fingerprint layer (the thing being measured, not the lab)
Found by CreepJS, and since 2026-10-16 by the lab too. Not fixed here:

1. The page reports the identity's GPU, but workers report the host's real GPU
   (`hasBadWebGL`). The WebGL patch exists only in the page. `fingerprint.py`'s own
   rule 2 ("only claim what the engine can back up everywhere") suggests using the
   host's GPU, or patching workers too.
2. Headless shared workers report `HeadlessChrome` (`hasHeadlessWorkerUA`). Playwright's
   user agent override does not reach them. Headful avoids it; so would a launch-level
   `--user-agent`.
3. Canvas and WebGL patches are detected as lies ("failed at too much recursion",
   "failed object toString"), and so is `Screen.colorDepth/pixelDepth` (descriptor
   check).

None of these affect the **behaviour** comparison, because all three styles share the
same fingerprint. They do matter for platform experiments (thesis ch. 4–5).

## 8. Protocol for thesis numbers

1. Start the lab: `cd backend/tests/behaviour/test_env/feed-lab && node server.mjs`.
   Use reCAPTCHA keys in `.env` if you want that row.
2. For each of at least **5 identities**, run all three styles **headful**, through a
   proxy (the default):
   ```bash
   cd backend
   export PYTHONPATH=.
   .venv/Scripts/python.exe tests/behaviour/test_env/run_feed_reader.py --scenario feed-lab-manual --identity id-1
   .venv/Scripts/python.exe tests/behaviour/test_env/run_feed_reader.py --scenario feed-lab        --identity id-1
   .venv/Scripts/python.exe tests/behaviour/test_env/run_feed_reader.py --scenario feed-lab-bot    --identity id-1
   ```
   In manual runs, do the task shown in the log (read about 8 posts, like 3, comment once,
   post once), then click **Finish session**. Several different people make a better
   baseline than one.
3. Aggregate and export:
   ```bash
   .venv/Scripts/python.exe tests/behaviour/test_env/compare_runs.py --aggregate --csv results.csv
   # after changing the algorithm, only count runs since the change:
   .venv/Scripts/python.exe tests/behaviour/test_env/compare_runs.py --aggregate --since 2026-10-20T00:00
   ```
   This prints the median and interquartile range per scenario, and a Mann-Whitney U test
   of each style against the manual baseline on classifier bot probability
   [mann1947test]. The AUC is the effect size [hanley1982auc]: **0.5 means
   indistinguishable from the human sessions**, 1.0 means always more bot-like. Below
   5 runs per group the p-value is not meaningful; the tool says so.
4. Report:
   - the aggregate table;
   - the classifier AUC against the human baseline, for the algorithm and for the
     robotic control;
   - the lab checks that did not pass;
   - the limitations in §7.

## 9. Re-validating after changes

| Changed | Re-run |
|---|---|
| a threshold in `feed-lab/index.html` | port it in `validate_lab_checks.py`, run it, commit `VALIDATION.md` |
| `mouse_features.py` | `bot_model/train.py` (the backend refuses a model with a different feature list) |
| the task, or what a style does | bump `PROTOCOL` in `behaviour_run_service.py` |
| `app.behaviour` | new runs; aggregate with `--since` |

```bash
cd backend
.venv/Scripts/python.exe -m pip install -r requirements-eval.txt     # once
PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/bot_model/train.py
.venv/Scripts/python.exe -I tests/behaviour/test_env/validate_lab_checks.py
.venv/Scripts/python.exe -m pytest tests/behaviour -q
```
