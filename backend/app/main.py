from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
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


async def _ensure_sqlite_compat_columns() -> None:
    # create_all() does not alter existing tables, so patch local SQLite schemas.
    if engine.dialect.name != "sqlite":
        return

    async with engine.begin() as conn:
        rows = await conn.exec_driver_sql("PRAGMA table_info(bots)")
        columns = {row[1] for row in rows.fetchall()}
        if "password" not in columns:
            await conn.exec_driver_sql("ALTER TABLE bots ADD COLUMN password VARCHAR(256)")

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
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok"}
