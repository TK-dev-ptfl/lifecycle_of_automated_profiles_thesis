import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import AsyncSessionLocal, engine, Base
import app.models  # noqa: F401 – register all ORM models
from app.auth.router import router as auth_router
from app.routers.bots import router as bots_router
from app.routers.tasks import router as tasks_router
from app.routers.identities import router as identities_router
from app.routers.proxies import router as proxies_router
from app.routers.fleet import router as fleet_router
from app.routers.ws import router as ws_router
from app.routers.algorithms import router as algorithms_router
from app.routers.email_platforms import router as email_platforms_router
from app.routers.emails import router as emails_router
from app.routers.sandboxes import router as sandboxes_router
from app.routers.workers import router as workers_router
from app.services import proxy_service
from app.utilities.runtime import browser_launch_blocked_reason
from app.services.identity_service import PROXY_TEST_BATCH_SIZE
from app.workers.pipeline_scheduler import DEFAULT_CONCURRENCY, pipeline_scheduler
from app.workers.proxy_refresher import proxy_refresher


async def _ensure_sqlite_compat_columns() -> None:
    # create_all() does not alter existing tables, so patch local SQLite schemas.
    if engine.dialect.name != "sqlite":
        return

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(bots)")
        columns = {row[1] for row in rows.fetchall()}
        if "password" not in columns:
            await conn.exec_driver_sql("ALTER TABLE bots ADD COLUMN password VARCHAR(256)")

        proxy_rows = await conn.exec_driver_sql("PRAGMA table_info(proxies)")
        proxy_columns = {row[1] for row in proxy_rows.fetchall()}
        if "consumed_at" not in proxy_columns:
            await conn.exec_driver_sql("ALTER TABLE proxies ADD COLUMN consumed_at DATETIME")
        if "is_rotating" not in proxy_columns:
            await conn.exec_driver_sql(
                "ALTER TABLE proxies ADD COLUMN is_rotating BOOLEAN NOT NULL DEFAULT 0"
            )

        # identities.email / email_provider used to be NOT NULL; identities can
        # now exist before their mailbox does, so relax that constraint on
        # existing local databases (SQLite has no ALTER COLUMN, so rebuild the
        # table - safe regardless of row count since column set/order/defaults
        # are all preserved from PRAGMA table_info).
        id_rows = await conn.exec_driver_sql("PRAGMA table_info(identities)")
        id_cols = id_rows.fetchall()  # (cid, name, type, notnull, dflt_value, pk)
        by_name = {row[1]: row for row in id_cols}
        needs_rebuild = by_name and (by_name["email"][3] == 1 or by_name["email_provider"][3] == 1)
        if needs_rebuild:
            names = [row[1] for row in id_cols]
            col_defs = []
            for _cid, name, ctype, notnull, dflt, pk in id_cols:
                force_nullable = name in ("email", "email_provider")
                parts = [name, ctype or "TEXT"]
                if pk:
                    parts.append("PRIMARY KEY")
                if notnull and not force_nullable:
                    parts.append("NOT NULL")
                if dflt is not None:
                    parts.append(f"DEFAULT {dflt}")
                col_defs.append(" ".join(parts))
            await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            await conn.exec_driver_sql(
                f"CREATE TABLE identities_new ({', '.join(col_defs)}, UNIQUE(username), UNIQUE(email))"
            )
            await conn.exec_driver_sql(
                f"INSERT INTO identities_new ({', '.join(names)}) SELECT {', '.join(names)} FROM identities"
            )
            await conn.exec_driver_sql("DROP TABLE identities")
            await conn.exec_driver_sql("ALTER TABLE identities_new RENAME TO identities")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_sqlite_compat_columns()
    # Provider rows back the Proxies page's per-source on/off switches. Seeded
    # here rather than by a migration so a new source added in code shows up on
    # the next boot; existing rows keep their is_enabled, since that's the
    # user's setting and a restart must not silently re-enable a source they
    # turned off.
    async with AsyncSessionLocal() as db:
        await proxy_service.seed_proxy_providers(db)

    # Proxy health checks are blocking socket work dispatched through
    # asyncio.to_thread, and this workload submits a great many of them at
    # once: each scheduler slot tests PROXY_TEST_BATCH_SIZE candidates
    # concurrently, so the default seven slots can have ~140 checks in flight,
    # each waiting up to its own 10s timeout. The default executor is only
    # min(32, cpu_count + 4) threads, which would queue most of those behind
    # each other and stretch a 10-second round into a minute or more. A thread
    # blocked on a socket costs almost nothing, so size the pool for the actual
    # concurrency. (Raising the scheduler's concurrency well past the default
    # via /api/workers would start queueing again - this is sized for the
    # default, not unbounded.)
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(
            max_workers=DEFAULT_CONCURRENCY * PROXY_TEST_BATCH_SIZE + 16,
            thread_name_prefix="blocking",
        )
    )

    # The refresher starts on its own: all it does is scrape two public lists
    # and keep the Proxies page current, which should be true whether or not
    # anyone is creating accounts right now. The scheduler does NOT - each of
    # its slots drives a real Chromium instance and registers a real mailbox,
    # so it waits for an explicit POST /api/workers/pipeline-scheduler/start.

    # Loud, once, at boot: every signup pipeline will fail without this, and the
    # exception it fails with explains nothing.
    blocked = browser_launch_blocked_reason()
    if blocked is not None:
        print(
            "\n*** WARNING: email signup pipelines cannot run - "
            f"{blocked}\n"
        )

    proxy_refresher.start()
    try:
        yield
    finally:
        await pipeline_scheduler.stop()
        await proxy_refresher.stop()


app = FastAPI(title="Bot Management Dashboard", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(bots_router)
app.include_router(tasks_router)
app.include_router(identities_router)
app.include_router(proxies_router)
app.include_router(fleet_router)
app.include_router(ws_router)
app.include_router(algorithms_router)
app.include_router(email_platforms_router)
app.include_router(emails_router)
app.include_router(sandboxes_router)
app.include_router(workers_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
