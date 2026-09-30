import os
import tempfile

# Must happen before anything imports app.config/app.database, since
# app.database builds its engine (and AsyncSessionLocal) at import time from
# settings.DATABASE_URL, and pydantic-settings lets a real env var win over
# backend/.env.
#
# Several tests exercise code that opens its own session via AsyncSessionLocal
# rather than the injected request-scoped one (identity_service's pipeline
# paths, and both workers - they outlive any request, so they have to). Left
# pointing at the dev database, those tests operate on the developer's real
# data: in particular they mark every free proxy consumed to isolate
# themselves, and consumed is permanent by design (see the Proxy model) - the
# host:port dedup then blocks those IPs from ever being re-imported, so each
# full test run permanently burned a chunk of the usable proxy pool.
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "botdb_pytest.sqlite")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.database import Base, engine as app_engine, get_db
from app.auth.utils import hash_password
from app.workers.pipeline_scheduler import pipeline_scheduler

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    # Start from an empty file so a previous run's rows (consumed proxies
    # especially) can't influence this one.
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # The app's own engine (now the temp file above) needs the schema too:
    # anything that opens its own session instead of the injected one - a
    # BackgroundTask kicked off by a request, the workers - goes through it, and
    # there's no lifespan here to run create_all for us.
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def no_real_webshare_credentials(monkeypatch):
    """Blanks the Webshare settings for every test.

    backend/.env holds real credentials on a developer machine, and
    pydantic-settings reads them at import. Without this, what
    fetch_proxies_from_webshare returns depends on whose machine the suite runs
    on - three tests silently started failing the moment a rotating endpoint was
    configured - and a test could reach Webshare's live API. Tests that exercise
    a Webshare path patch in the specific values they need.
    """
    from app.services import proxy_service

    for name in (
        "WEBSHARE_API_KEY",
        "WEBSHARE_PROXY_USERNAME",
        "WEBSHARE_PROXY_PASSWORD",
    ):
        monkeypatch.setattr(proxy_service.settings, name, "")


@pytest.fixture(autouse=True)
def queued_pipelines(monkeypatch):
    """Records what would have been handed to the pipeline scheduler, instead of
    handing it over.

    Creating an identity that needs a mailbox queues it on the scheduler, and
    queueing starts that worker - which would reserve a real proxy, launch a
    real Chromium instance and register a real mailbox, from a test run. The
    scheduler's own behaviour is covered in tests/test_workers.py, against a
    stubbed pipeline; here we only care that the router queued the right thing.

    Autouse so this can't be forgotten: any test that creates an identity is one
    ALT+TAB away from a browser window otherwise.
    """
    queued: list[tuple] = []

    def fake_enqueue(identity_id, platform_id, display_name=None, provider_name=""):
        queued.append((identity_id, platform_id, provider_name))
        return len(queued)

    monkeypatch.setattr(pipeline_scheduler, "enqueue", fake_enqueue)
    return queued


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    resp = await client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def platform(client, auth_headers, db_session):
    resp = await client.post(
        "/api/platforms",
        json={"name": "simulation", "display_name": "Simulation", "is_enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()
