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
