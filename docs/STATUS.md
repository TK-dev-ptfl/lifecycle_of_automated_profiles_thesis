# Implementation status vs. thesis

Snapshot: **2026-10-16**, against `Diplomovka.pdf` (chapters 1–7) and `Presentation.pdf`.
Update this file whenever a row changes state.

Legend: ✅ done · 🟡 partial · ❌ not started · ⚠️ code and thesis text disagree

## Summary

The **test environment's infrastructure** (chapter 3) is largely built: identities,
fingerprints, proxies, email-account creation, a background scheduler and a
dashboard. The **behaviour layer** (human-like input) and an **independent
evaluation harness** for it (feed lab, CreepJS/rebrowser, own mouse classifier)
are the most mature parts of the code.

What the thesis's central question needs is still missing: there is no path from
"identity exists" to "Reddit account exists, warms up, performs tasks, and we
record whether it survives". Concretely, nothing runs a task, there is no warm-up
pipeline, no monitoring of account health, and four of the five communication
methods are stubs. Chapters 4–7 have no text and no data to fill them yet.

The original plan (README) aimed to finish on 2026-09-12. The infrastructure
phase ran long; the experiment phase has not started.

## Chapter 3 — Test environment

### 3.1 Technologies

| Item (thesis table) | State | Notes |
|---|---|---|
| praw | ✅ | Used by `official_api` methods only. |
| playwright | ✅ | Pipelines, behaviour runs. |
| playwright-stealth | 🟡 | Used only in the Tuta email pipeline. Behaviour runs use `app/behaviour/fingerprint.py` instead. |
| curl_cffi | ❌ | Not in `requirements.txt`. Needed for `http_requests` / `unofficial_api`. |
| fake-useragent | ⚠️ | Not used. UAs come from coherent pools in `fingerprint.py`. Update thesis table. |
| Faker | ⚠️ | Not used. Identity generation uses its own generator in `identity_service.py`. Update thesis table. |
| BLOC | ❌ | Named in 2.4.1 and 3.1.2 as an evaluation tool; not integrated. |
| Pixelscan / BrowserLeaks | 🟡 | Opt-in "public" detectors in `behaviour/evaluation/detectors.py` (screenshot + keyword lines, not parsed). |
| CreepJS | ✅ | Vendored into the feed lab, run after each behaviour run. |
| *Not in thesis:* rebrowser-bot-detector, reCAPTCHA v3, own mouse classifier | ✅ | Add these to table 3.2 and describe them (see "thesis gaps" below). |

### 3.3 Control hierarchy

| Layer | State | Where | Gap |
|---|---|---|---|
| 3.3.1 Communication methods | 🟡 | `app/algorithm/methods/` + `MethodWrapper` | Only `official_api` is real (get_data, get_post, get_comments, reply_comment, upvote_post). `unofficial_api`, `http_requests`, `headless_browser`, `classical_browser` return hard-coded dicts. No `submit_post`, `follow`, `subscribe`. |
| 3.3.2 Algorithmic layer | 🟡 | `app/behaviour/` | Strong: profiles per identity, goals, executor, mouse/keyboard/scroll/timing primitives, simulator + Playwright adapters, `ReadFeed`. Missing: upvote / comment / post / follow goals for Reddit; the "probabilistic post selector by interest profile" from 3.3.2. |
| ↳ link between 3.3.1 and 3.3.2 | ❌ | — | `app/algorithm` (methods) and `app/behaviour` (human input) are separate and do not call each other. The browser methods should be built on `app/behaviour`. `app/algorithm/skeletons/` holds a single example. |
| 3.3.3 Task layer | 🟡 | `models/task.py`, `routers/tasks.py`, Tasks page | CRUD, types and `sync_mode` exist. **Nothing executes a task**; `app/tasks/types/` is empty. |
| 3.3.4 Pipeline layer | 🟡 | `app/pipelines/` | See 3.5. `app/lifecycle/modes/` is empty. |

### 3.4 Support services

| Service | State | Where | Gap vs. thesis |
|---|---|---|---|
| 3.4.1 Email | 🟡 ⚠️ | `pipelines/email_pool/providers/tuta.py`, `services/email_service.py`, `workers/pipeline_scheduler.py` | Automated Tuta signup with a manual CAPTCHA gate, queued and parallel. **Reading mail (verification codes) is not built.** Thesis describes own domain + IMAP; code uses Tuta. No status enum (active/blocked/expired), only `ever_blocked` + `blocked_on_platforms`, no reasons history. |
| 3.4.2 Proxy | ✅ 🟡 | `services/proxy_service.py`, `workers/proxy_refresher.py`, `services/run_proxy_service.py` | Webshare + free sources, health checks, one proxy claimed and consumed per identity. Missing: "platforms where detected" record; geo-matching proxy to the identity's declared region at identity creation. |
| 3.4.3 Identity | 🟡 | `services/identity_service.py`, `behaviour/fingerprint.py`, `behaviour/profile.py` | Technical layer is done and consistent (fingerprint and motor profile derived from identity). Personal layer lacks the persona model the thesis requires in 2.4.5: MBTI/OCEAN, speaking style, activity-time template. |
| 3.4.4 Monitoring | ❌ | `monitoring/health_checker.py` (all `NotImplementedError`), `models/log.py` | Pipeline logs are visible on the Monitoring page. No account health probe, no shadowban check, no karma tracking, no lifecycle state history. Thesis section is empty too. |

### 3.5 Pipelines

| Pipeline | State | Gap |
|---|---|---|
| Email creation (Tuta) | ✅ | Works end to end with a human solving the CAPTCHA. |
| 3.5.1 Reddit creation | 🟡 | Steps 1–7 in `pipelines/reddit/` (homepage → humanity check → signup → email → submit → **manual** wait for verification). Missing: thesis steps 7–9 (read code from mailbox, username/password, save session to DB, create `Bot` row, register in monitoring). **Not reachable from the API, the scheduler or the UI**; only from tests. |
| 3.5.2 Warm-up | ❌ | Nothing implemented. Table 3.3 schedule is not encoded anywhere. |
| "three pipelines" | ⚠️ | 3.5 says three, lists two. |

### 3.6 Sandbox — 🟡
`models/sandbox.py` stores name/group/password; CRUD + page exist. The private
subreddit itself is created by hand. Fine for the thesis; document the manual step.

### 3.7 Algorithm implementation — ⚠️
Thesis section is a placeholder ("what each algorithm do…"). The code here is the
most finished part. See "thesis gaps".

### 3.8 Data flow / experiment execution — ❌
No experiment definition, no runner, no results store. The account states in 3.8
(created → warm-up → active → restricted/banned → archived) do not match the
model enums (`BotState`, `BotStatus`, `BotMode` in `models/bot.py`), and transitions
are not recorded with timestamp and reason.

## Chapter 4 — Methodology

| Item | State | Notes |
|---|---|---|
| 4.1 Properties (cost, difficulty, sustainability, quality, compute) | ❌ | No instrumentation: no per-action cost, no CPU/RAM sampling, no survival time. Definitions exist only in README. |
| 4.2 Tasks: scraping / engagement / messaging | 🟡 | Only official API can do them. |
| 4.3.1 Throwaway vs 4.3.2 persona | ❌ | Needs warm-up + persona. |
| 4.3.3 Coordinated network | ❌ | `SyncMode.coordinated` exists as an enum only. |
| 4.3.4 LLM content | ❌ | No LLM integration anywhere. |
| 4.4 Five communication methods | 🟡 | 1 of 5 real. |
| Presentation's hypothesis axes (warm-up length, warm-up intensity, method + algorithm, content) | ❌ | All depend on warm-up and task execution. |

## Chapters 1, 5, 6, 7, front matter — ❌
Empty. Front matter also has: author/supervisor placeholders, empty abstract and
acknowledgements, and the declaration says *bakalársku prácu* (should be
*diplomovú*). All 11 figures in chapter 3 are placeholders.

## Thesis gaps: work that exists in code but not in the text

Write these up; they are finished, defensible contributions:

1. **Behaviour layer** (3.7): goal/profile/environment/executor split, per-identity
   motor profiles, primitives, simulator vs. real browser. Source docstrings in
   `app/behaviour/` are close to thesis-ready.
2. **Fingerprint coherence** (3.4.3 + 2.4.2): the "coherent beats random" and
   "only claim what the engine can back up" rules in `fingerprint.py` are a direct
   application of Venugopalan et al. [9].
3. **Evaluation harness** (new section in 3 or 4; fully documented, with literature and
   validation, in [TEST_ENVIRONMENT.md](TEST_ENVIRONMENT.md)): feed lab, robotic negative
   control (`behaviour/robotic.py`), manual human baseline, CreepJS + rebrowser,
   reCAPTCHA v3, run comparison (`behaviour_run_service.compare`).
4. **Mouse classifier** (4 or 5): random forest on SapiMouse + Iliou + synthetic,
   results in `backend/tests/behaviour/test_env/bot_model/REPORT.md`. This is
   already a result: you can report how the human-like algorithm and the robotic
   control score against an independent judge.
5. **Email pipeline automation** (3.4.1): Tuta, manual gate, scheduler with N
   concurrent slots, stall guard. Replaces the IMAP/own-domain description.

## Code health

- `pytest` (backend): **235 passed, 2 failed, 17 errors** on 2026-10-16.
  - 18 of them: the `platform` fixture in `tests/conftest.py` POSTs to `/api/platforms`,
    whose router was removed from `main.py` in commit `9eacbfb` ("platform removal").
    Fix the fixture (or the tests), not the app.
  - `test_proxies.py::test_test_proxy`: likely needs network; check.
- Large uncommitted change set (behaviour evaluation, robotic control, run proxy,
  classifier). Commit it before starting the next phase.
- Bibliography: [5] Nwala et al. is listed as `arXiv:2603.03128, 2023`; an arXiv
  id beginning `2603` is from March 2026. Check the year.
