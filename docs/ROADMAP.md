# Roadmap

Drafted 2026-10-16 from [STATUS.md](STATUS.md). Weeks are counted from that date
(W1 = 19.10.2026). Set real dates once the submission deadline is fixed.

## The constraint that shapes everything

The experiments measure **how long accounts survive** and **how much trust they
build**. That takes calendar time: warm-up alone is 11+ days in table 3.3, and
each hypothesis needs several bots per condition observed for weeks. The coding is
not the bottleneck; the waiting is.

So:

1. Get the shortest path to "a real Reddit account in the sandbox, monitored" done
   first, and **start creating accounts early**, before the rest is polished.
2. Build the rest of the system while those accounts age.
3. Do not add more depth to the behaviour layer until the experiment loop runs.
   It is already ahead of everything else.

## Proposed scope

| Area | Keep | Reduce or cut |
|---|---|---|
| Communication methods | Official API, headless browser, headful browser, for all three tasks | Unofficial API and raw HTTP (`curl_cffi`) for **scraping only**: read-only, cheap to build, still gives the 5-method comparison on one axis |
| Strategies | Throwaway vs persona; warm-up length; warm-up intensity | Coordinated network: one small experiment at most, or move to "future work" |
| Content | Static templates vs LLM with persona (H2) | — |
| Evaluation | Account survival, shadowban, karma, own classifier, CreepJS/rebrowser | BLOC: use if time allows, otherwise justify in text why the classifier replaces it |

## Phases

### Phase 0 — housekeeping (W1)
- [ ] Commit the uncommitted behaviour/evaluation work.
- [ ] Fix `tests/conftest.py` `platform` fixture (18 failing tests after platform removal).
- [ ] Write thesis 3.7 (behaviour layer) and the evaluation-harness section now, while the
      design is fresh. Sources: module docstrings in `app/behaviour/`, `bot_model/REPORT.md`.
- [ ] Fix front matter: name, supervisor, *diplomovú*, reference [5] year.

### Phase 1 — a monitored Reddit account (W1–W3) **critical path**
- [ ] **Mailbox reading for Tuta** (`fetch_verification`), plugged into
      `reddit/steps/await_email_verification.py`. Until then keep the manual gate.
- [ ] Finish the Reddit creation pipeline: username, password, save session/cookies,
      create the `Bot` row linked to identity + proxy + email.
- [ ] Expose it: API endpoint + Pipelines page entry + scheduler job type.
- [ ] **Lifecycle state model**: one enum matching thesis 3.8
      (`created → warm_up → active → restricted | banned → archived`) and a
      `bot_state_transitions` table (time, from, to, reason). Alembic migration.
- [ ] **Monitoring v1** (`monitoring/health_checker.py`): per bot, logged-out profile
      fetch (exists / suspended / shadowbanned), karma, last action result. Periodic worker
      like `proxy_refresher`. Writes transitions.
- [ ] Start creating the first batch of accounts as soon as this works.

### Phase 2 — tasks that actually run (W3–W6)
- [ ] **Reddit goals on `app/behaviour`**: open subreddit, read feed (`ReadFeed` exists),
      upvote, comment, post, join/follow. Reddit `FeedSchema` + selectors.
- [ ] **Browser methods built on those goals**: `headless_browser` and `classical_browser`
      implement the same method interface as `official_api`, driving `app/behaviour`
      instead of returning stubs. One shared implementation, two launch modes.
- [ ] Add missing method operations: `submit_post`, `follow`/`subscribe`.
- [ ] **Task executor** (`app/tasks/types/`): scrape, engage, post. Takes a task + bot,
      picks the method from `bot.communication_mode`, logs every action with outcome to
      `logs`. Runs as a worker.
- [ ] **Warm-up pipeline**: a schedule of tasks (table 3.3) with `length_days` and
      `intensity` as parameters, since those are two hypothesis axes.
- [ ] Scraping via `unofficial_api` (`.json` endpoints) and `http_requests` (`curl_cffi`).

### Phase 3 — experiments as data (W5–W7)
- [ ] **Experiment definition**: name, hypothesis, conditions, bots per condition, task,
      duration. Stored in DB, created from the UI.
- [ ] **Metrics for 4.1**, recorded per action and per bot:
      cost (proxy + email + LLM per 1000 successful actions), compute (CPU/RAM sampled per
      browser process), sustainability (time to restriction/ban), quality (task success rate).
      Difficulty is qualitative: keep a log of implementation time per method.
- [ ] **Persona v2** on identity: MBTI + OCEAN + speaking style + activity hours (2.4.5).
- [ ] **LLM content module**: persona-conditioned comment/post generation, plus a
      template generator for the control group. Record tokens and cost.
- [ ] Export: one CSV/notebook per experiment, so chapter 5 tables come out of code.

### Phase 4 — run hypotheses (W6 onward, overlapping)
Each iteration: define → run ≥3–5 bots per condition in the sandbox → observe ≥2 weeks
→ record → adjust (README "iteratívna implementácia").

| ID | Hypothesis | Varies | Needs |
|---|---|---|---|
| H1 | Headless (no obfuscation) is restricted sooner than headful | method | Phase 2 |
| H2 | LLM + persona content is detected less than templates | content | Phase 3 |
| H3 | Accounts with warm-up survive longer than throwaway accounts | warm-up yes/no | Phase 2 |
| H4 | Longer warm-up → longer survival / more karma | warm-up length | Phase 2 |
| H5 | Lower warm-up intensity → longer survival | warm-up intensity | Phase 2 |
| H6 | Human-like input (app.behaviour) scores as human; robotic control does not | algorithm | **ready now** in the feed lab |

H6 can be written up immediately from existing runs.

### Phase 5 — writing (continuous, final push at the end)
- Ch 3: fill 3.4.4, 3.7, 3.8; replace all 11 figure placeholders.
- Ch 4: methodology from the experiment definitions and 4.1 metrics.
- Ch 5–6: from exported experiment data.
- Ch 1, 7, abstract (SK + EN).

## Decisions needed

1. **Submission deadline** — sets the real dates and how many hypothesis iterations fit.
2. **Scope cuts** above — especially unofficial API / raw HTTP limited to scraping, and coordinated networks.
3. **Email verification** — automate Tuta mailbox reading, or accept a manual click per account.
4. **LLM provider and budget** for H2.
