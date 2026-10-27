# Architecture and code map

How the thesis's chapter 3 design maps onto the repository. For what is finished
and what is not, see [STATUS.md](STATUS.md).

## Separate projects

- **`social-lab/`**: a standalone dummy social network for collecting human interaction data (Node, no dependencies). It shares no code with `backend/` or `frontend/`; data moves through exported files. See [social-lab/README.md](../social-lab/README.md).

## Stack

- **Backend**: FastAPI + SQLAlchemy (async) + Alembic, `backend/app/`. SQLite by default
  (`backend/.env.example`), Postgres via `docker-compose.yml`.
- **Frontend**: React + Vite + Tailwind, `frontend/src/`. One page per area under `pages/`.
- **Background work**: asyncio tasks inside the FastAPI process (`app/workers/`), not
  Redis/arq. Redis is in compose and requirements but unused by the workers.
- **Browser automation**: Playwright (Chromium, installed Chrome/Edge for fingerprinted runs).

## Running

```bash
# backend (Windows: use run.py, not `uvicorn --reload`; see its docstring)
cd backend
cp .env.example .env
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe run.py            # http://localhost:8000

# frontend
cd frontend && npm install && npm run dev  # http://localhost:5173

# feed lab, needed by behaviour runs
cd backend/tests/behaviour/test_env/feed-lab && node server.mjs   # http://localhost:8080

# tests
cd backend && .venv/Scripts/python.exe -m pytest -q
cd frontend && npm test
```

Default login: `admin` / `admin123` (from `.env`).

## Control hierarchy (thesis 3.3)

```
Pipeline layer   app/pipelines/          creation pipelines (email, reddit); warm-up: not yet
     │
Task layer       app/models/task.py      task definitions; executor: not yet (app/tasks/types/)
     │
Algorithm layer  app/behaviour/          human-like input: goals, profiles, executor
                 app/algorithm/skeletons example composition over methods
     │
Method layer     app/algorithm/methods/  official_api | unofficial_api | http_requests
                                         | headless_browser | classical_browser
                                         selected through MethodWrapper("official"), ...
```

`app/algorithm` and `app/behaviour` are not connected yet. The intended link: the two
browser methods implement the method interface by running `app/behaviour` goals.

### Method layer — `app/algorithm/methods/`
Each method type is a package exposing the same function names
(`get_data`, `get_post`, `get_comments`, `reply_comment`, `upvote_post`) via `__all__`
and an optional `build_context()`. `MethodWrapper` imports the package by name and binds
the functions, injecting the context when the first parameter is `context`.
Results use one shape: `{"ok", "status_code", "data" | "error"}`.

### Algorithm layer — `app/behaviour/`
Four parts, each usable alone (package docstring in `app/behaviour/__init__.py`):

| File | Role |
|---|---|
| `profile.py` | **Who**: typing speed, hesitancy, aim scatter, patience. `derive_for(identity)` gives a stable, distinct profile per identity. |
| `goals.py` | **What**: `ClickOn`, `TypeInto`, `ScrollTo`, `Wander`, `Dwell`, `WaitFor`, `ReadFeed` + `FeedSchema`. No coordinates or timings. |
| `environment.py` | **Where**: the port (viewport, observe target, scroll, sleep, mouse, keyboard). |
| `executor.py` | **How**: `Actor` pursues goals in an environment with a profile. |
| `primitives/` | One physical act each: mouse paths, keystroke rhythm, wheel notches, timing distributions. |
| `adapters/` | `SimulatedEnvironment` (in-memory, virtual clock) and `PlaywrightEnvironment` (real page). |
| `fingerprint.py` | What the machine says about itself, derived per identity; rules: coherence over randomness, only claim what the engine backs up in every frame and worker. |
| `robotic.py` | Deliberately robotic reader: the negative control for every check. |
| `evaluation/` | Independent judges: `detectors.py` (CreepJS, rebrowser, public pages), `mouse_features.py` + `mouse_model.py` (random-forest classifier, pure-Python inference), `trace_stats.py` (raw input statistics). |

Behaviour runs are started from the Algorithm page and executed by
`services/behaviour_run_service.py` (scenarios: feed lab with the human-like algorithm,
the robotic control, or a person driving manually). `services/run_proxy_service.py`
picks a working proxy read-only, without touching the identity pool.

Classifier training lives outside `app/`: `backend/tests/behaviour/test_env/bot_model/`
(see its README and REPORT). Training needs `requirements-eval.txt`; scoring does not.
How the whole test environment measures human-likeness, and why that is valid:
[TEST_ENVIRONMENT.md](TEST_ENVIRONMENT.md).

### Task layer — `app/models/task.py`, `routers/tasks.py`
`TaskType` (scrape, post, engage, monitor, seed, vote), `SyncMode`
(independent, sharded, coordinated), payload, schedule, success criteria. CRUD only.

### Pipeline layer — `app/pipelines/`
| Pipeline | Entry | Notes |
|---|---|---|
| Email (Tuta) | `email_pool/providers/tuta.py`, started by `identity_service.start_email_pipeline_for_identity` | Named steps that verify their own outcome; manual CAPTCHA gate (`email_pool/manual_gate.py`); live progress (`email_pool/progress.py`). |
| Reddit signup | `reddit/pipeline.py` (`PIPELINE_STEPS`) | One module per step in `reddit/steps/`; step order lives only in `pipeline.py`. Stops at email verification. `reddit/blocks.py` detects IP refusal. |
| Warm-up | — | Not implemented. |

## Support services (thesis 3.4)

| Service | Code |
|---|---|
| Email | `models/email.py`, `models/email_platform.py`, `services/email_service.py`, `routers/emails.py`, Emails page |
| Proxy | `models/proxy.py`, `models/proxy_provider.py`, `services/proxy_service.py` (Webshare + free sources), `utilities/proxy_health.py`, `workers/proxy_refresher.py`, Proxies page |
| Identity | `models/identity.py`, `services/identity_service.py` (generation, proxy claim/consume, email pipeline orchestration, stall guard), Identities page |
| Monitoring | `models/log.py`, `monitoring/health_checker.py` (stub), Monitoring page (pipeline logs) |
| Sandbox | `models/sandbox.py`, `services/sandbox_service.py`, Sandboxes page |

## Workers — `app/workers/`
`base.LoopWorker` is a single asyncio task on the app's event loop, controlled through
`/api/workers`.

- `proxy_refresher` starts with the app and re-scrapes free proxy sources on an interval.
- `pipeline_scheduler` starts only on `POST /api/workers/pipeline-scheduler/start`; runs up
  to N email pipelines at once, each slot with its own DB session, identity and proxy;
  in continuous mode it generates identities to keep slots busy.

## Proxy rule
A proxy used by an identity pipeline is claimed by exactly one identity and marked
consumed; it is never handed to another account (thesis 2.4.2: one account, one proxy).
Behaviour test runs are not accounts and only read the pool.

## Data model (main tables)
`identities` ─1:1─ `bots` ─n:1─ `tasks`; `bots` ─1:1─ `proxies` (`assigned_bot_id`);
`emails` (`used_by_bot_id`); `logs` (bot, task, level, category, metadata); `sandboxes`.
Migrations in `backend/alembic/versions/`.
