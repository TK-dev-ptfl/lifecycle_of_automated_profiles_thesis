import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import proxy_service

PROXY_DATA = {
    "host": "192.168.1.1",
    "port": 8080,
    "protocol": "http",
    "type": "residential",
    "country": "US",
    "provider": "oxylabs",
}


@pytest.mark.asyncio
async def test_create_proxy(client, auth_headers):
    resp = await client.post("/api/proxies", json=PROXY_DATA, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["host"] == "192.168.1.1"
    assert data["is_healthy"] is True


@pytest.mark.asyncio
async def test_list_proxies(client, auth_headers):
    await client.post("/api/proxies", json=PROXY_DATA, headers=auth_headers)
    resp = await client.get("/api/proxies", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_bulk_create_proxies(client, auth_headers):
    resp = await client.post(
        "/api/proxies/bulk",
        json={"proxies": [
            {**PROXY_DATA, "host": "10.0.0.1"},
            {**PROXY_DATA, "host": "10.0.0.2"},
        ]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_test_proxy(client, auth_headers):
    create = await client.post("/api/proxies", json=PROXY_DATA, headers=auth_headers)
    proxy_id = create.json()["id"]
    resp = await client.post(f"/api/proxies/{proxy_id}/test", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_healthy"] is True


@pytest.mark.asyncio
async def test_test_all_proxies(client, auth_headers):
    resp = await client.post("/api/proxies/test-all", headers=auth_headers)
    assert resp.status_code == 200
    assert "tested" in resp.json()


@pytest.mark.asyncio
async def test_filter_proxies_by_health(client, auth_headers):
    resp = await client.get("/api/proxies?is_healthy=true", headers=auth_headers)
    assert resp.status_code == 200
    for proxy in resp.json():
        assert proxy["is_healthy"] is True


@pytest.mark.asyncio
async def test_delete_proxy(client, auth_headers):
    create = await client.post("/api/proxies", json=PROXY_DATA, headers=auth_headers)
    proxy_id = create.json()["id"]
    resp = await client.delete(f"/api/proxies/{proxy_id}", headers=auth_headers)
    assert resp.status_code == 204


def test_fetch_proxies_from_proxyscrape_parses_protocolipport_text():
    """proxyscrape.com's protocolipport text format is one "protocol://ip:port"
    per line with no country/anonymity data at all - unlike free-proxy-list.net,
    which is an HTML table. Confirms the parser handles the supported
    protocols correctly and skips what it can't/shouldn't represent: socks4
    (not one of our ProxyProtocol values), a malformed line, a blank line,
    and a non-numeric port."""
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.text = (
        "http://1.2.3.4:8080\n"
        "socks5://5.6.7.8:1080\n"
        "socks4://9.10.11.12:1081\n"
        "not-a-valid-line\n"
        "\n"
        "http://13.14.15.16:notaport\n"
    )
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = fake_response

    with patch("app.services.proxy_service.httpx.Client", return_value=fake_client):
        result = proxy_service.fetch_proxies_from_proxyscrape()

    assert result == [
        {"host": "1.2.3.4", "port": 8080, "protocol": "http", "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
        {"host": "5.6.7.8", "port": 1080, "protocol": "socks5", "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
    ]


def test_fetch_proxies_from_proxyscrape_returns_empty_on_request_failure():
    """Same "log and return [] rather than raise" contract as
    fetch_proxies_from_free_proxy_list - a fetch failure here must not blow
    up the whole scrape+import flow, just contribute nothing this round."""
    with patch("app.services.proxy_service.httpx.Client", side_effect=Exception("network down")):
        assert proxy_service.fetch_proxies_from_proxyscrape() == []


@pytest.mark.asyncio
async def test_cleanup_never_deletes_a_retired_proxy(db_session):
    """A retired proxy's row is the only thing stopping a later scrape from
    re-importing that address and handing it to another run, so cleanup must
    leave it alone even though it is unhealthy and unassigned - the exact
    combination it otherwise deletes."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    retired = Proxy(
        host="198.51.100.121", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="cleanup-test", is_healthy=False,
        consumed_at=datetime.now(timezone.utc),
    )
    plain_dead = Proxy(
        host="198.51.100.122", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="cleanup-test", is_healthy=False,
    )
    db_session.add_all([retired, plain_dead])
    await db_session.commit()
    retired_id, plain_dead_id = retired.id, plain_dead.id

    await proxy_service.cleanup_unhealthy_proxies(db_session)
    await db_session.commit()

    rows = (await db_session.execute(
        select(Proxy).where(Proxy.id.in_([retired_id, plain_dead_id]))
    )).scalars().all()
    surviving = {row.id for row in rows}
    assert retired_id in surviving, "a retired proxy must survive cleanup"
    assert plain_dead_id not in surviving, "an ordinary dead proxy should still be cleaned up"


@pytest.mark.asyncio
async def test_get_proxies_can_hide_retired_ones(db_session):
    """What the Proxies page relies on: the retired set grows without bound by
    design, so the live pool has to be askable for on its own."""
    from datetime import datetime, timezone
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    live = Proxy(
        host="198.51.100.131", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="filter-test",
    )
    retired = Proxy(
        host="198.51.100.132", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="filter-test", consumed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([live, retired])
    await db_session.commit()

    available = {p.id for p in await proxy_service.get_proxies(db_session, retired=False)}
    gone = {p.id for p in await proxy_service.get_proxies(db_session, retired=True)}
    assert live.id in available and retired.id not in available
    assert retired.id in gone and live.id not in gone

    stats = await proxy_service.count_proxies(db_session)
    assert stats["total"] == stats["available"] + stats["retired"]
    assert stats["retired"] >= 1


@pytest.mark.asyncio
async def test_import_proxies_from_free_list_merges_both_sources(db_session):
    """import_proxies_from_free_list must pull from free-proxy-list.net AND
    proxyscrape.com and import both, not just whichever one happens to be
    checked first - and must still succeed if only one of the two actually
    returns anything."""
    free_proxy_list_data = [
        {"host": "203.0.113.10", "port": 8080, "protocol": "http", "type": "residential", "country": "US", "provider": "free-proxy-list"},
    ]
    proxyscrape_data = [
        {"host": "203.0.113.20", "port": 1080, "protocol": "socks5", "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
    ]

    with patch("app.services.proxy_service.fetch_proxies_from_free_proxy_list", return_value=free_proxy_list_data), \
         patch("app.services.proxy_service.fetch_proxies_from_proxyscrape", return_value=proxyscrape_data), \
         patch("app.services.proxy_service.fetch_proxies_from_webshare", return_value=[]):
        result = await proxy_service.import_proxies_from_free_list(db_session)

    assert result["imported"] == 2
    assert result.get("error") is None

    all_proxies = await proxy_service.get_proxies(db_session)
    hosts = {p.host for p in all_proxies}
    assert "203.0.113.10" in hosts
    assert "203.0.113.20" in hosts


# --- Per-provider on/off ------------------------------------------------------

async def _all_providers_on(db):
    """Provider toggles are committed, so they outlive the db_session fixture's
    rollback and leak into whatever test runs next. Each provider test therefore
    states the starting point it needs instead of inheriting one."""
    await proxy_service.seed_proxy_providers(db)
    for provider in await proxy_service.get_proxy_providers(db):
        if not provider["is_enabled"]:
            await proxy_service.set_proxy_provider_enabled(db, provider["key"], True)


@pytest.mark.asyncio
async def test_seed_proxy_providers_is_idempotent_and_keeps_user_choices(db_session):
    """Seeding runs on every boot. It must create missing rows and leave
    is_enabled alone on rows that exist - a restart silently re-enabling a
    source someone turned off would be the worst kind of surprise."""
    await _all_providers_on(db_session)
    keys = {p["key"] for p in await proxy_service.get_proxy_providers(db_session)}
    assert {"free-proxy-list", "proxyscrape", "webshare"} <= keys

    await proxy_service.set_proxy_provider_enabled(db_session, "proxyscrape", False)
    await proxy_service.seed_proxy_providers(db_session)

    by_key = {p["key"]: p for p in await proxy_service.get_proxy_providers(db_session)}
    assert by_key["proxyscrape"]["is_enabled"] is False
    assert by_key["free-proxy-list"]["is_enabled"] is True

    await _all_providers_on(db_session)


@pytest.mark.asyncio
async def test_disabled_provider_is_excluded_from_identity_candidates(db_session):
    """The whole point of the switch: a disabled provider's proxies stay in the
    pool but stop being offered to new identities."""
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.services import identity_service

    await _all_providers_on(db_session)
    kept = Proxy(
        host="198.51.100.201", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="free-proxy-list",
    )
    excluded = Proxy(
        host="198.51.100.202", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="proxyscrape",
    )
    db_session.add_all([kept, excluded])
    await db_session.commit()

    both = {c.id for c in await identity_service.list_free_proxy_candidates(db_session)}
    assert kept.id in both and excluded.id in both

    await proxy_service.set_proxy_provider_enabled(db_session, "proxyscrape", False)
    after = {c.id for c in await identity_service.list_free_proxy_candidates(db_session)}
    assert kept.id in after
    assert excluded.id not in after

    # Not deleted, and not hidden from the page - only from selection.
    assert excluded.id in {p.id for p in await proxy_service.get_proxies(db_session)}

    # Turning it back on makes them eligible again with no re-fetch.
    await proxy_service.set_proxy_provider_enabled(db_session, "proxyscrape", True)
    assert excluded.id in {c.id for c in await identity_service.list_free_proxy_candidates(db_session)}


@pytest.mark.asyncio
async def test_a_provider_with_no_row_is_treated_as_enabled(db_session):
    """disabled_provider_keys returns what to EXCLUDE, so a provider nobody has
    ever recorded - a one-off name typed into the Add Proxy form - stays usable
    instead of silently vanishing from selection."""
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.services import identity_service

    ad_hoc = Proxy(
        host="198.51.100.210", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="US", provider="some-provider-nobody-registered",
    )
    db_session.add(ad_hoc)
    await db_session.commit()

    assert ad_hoc.id in {c.id for c in await identity_service.list_free_proxy_candidates(db_session)}


@pytest.mark.asyncio
async def test_disabled_provider_is_not_fetched_on_refresh(db_session):
    """A source switched off must also stop refilling the pool every two
    minutes, or the toggle would only be half a switch."""
    await _all_providers_on(db_session)
    for key in ("proxyscrape", "webshare"):
        await proxy_service.set_proxy_provider_enabled(db_session, key, False)

    free_list = MagicMock(return_value=[])
    scrape = MagicMock(return_value=[])
    webshare = MagicMock(return_value=[])
    with patch("app.services.proxy_service.fetch_proxies_from_free_proxy_list", free_list), \
         patch("app.services.proxy_service.fetch_proxies_from_proxyscrape", scrape), \
         patch("app.services.proxy_service.fetch_proxies_from_webshare", webshare):
        await proxy_service.fetch_all_free_proxies(db_session)

    free_list.assert_called_once()
    scrape.assert_not_called()
    webshare.assert_not_called()

    await _all_providers_on(db_session)


@pytest.mark.asyncio
async def test_provider_counts_are_reported_per_provider(db_session):
    """What the Proxies page groups by - each source's own share of the pool,
    counted in the database rather than by fetching every row."""
    from datetime import datetime, timezone
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    await _all_providers_on(db_session)
    db_session.add_all([
        Proxy(host="198.51.100.221", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
              country="US", provider="webshare"),
        Proxy(host="198.51.100.222", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
              country="US", provider="webshare", is_healthy=False),
        Proxy(host="198.51.100.223", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
              country="US", provider="webshare", consumed_at=datetime.now(timezone.utc)),
    ])
    await db_session.commit()

    webshare = next(p for p in await proxy_service.get_proxy_providers(db_session) if p["key"] == "webshare")
    assert webshare["total"] == 3
    assert webshare["retired"] == 1
    assert webshare["available"] == 2
    assert webshare["available_healthy"] == 1
    assert webshare["kind"] == "paid"
    assert webshare["can_fetch"] is True


@pytest.mark.asyncio
async def test_toggling_an_unknown_provider_is_a_404(client, auth_headers):
    resp = await client.patch(
        "/api/proxies/providers/not-a-real-provider",
        json={"is_enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_webshare_fetcher_skips_itself_without_an_api_key():
    """No key is a normal, expected state - it must contribute nothing and say
    why, not fail the whole refresh the other sources are part of."""
    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", ""):
        assert proxy_service.fetch_proxies_from_webshare() == []


def test_webshare_fetcher_parses_credentials_and_skips_invalid_entries():
    """Webshare is the only source that returns per-proxy credentials, and
    without them its proxies authenticate as nobody and fail every check. It
    also marks proxies it knows to be down - no reason to import one just to
    health-check it and throw it away."""
    page = {
        "next": None,
        "results": [
            {
                "proxy_address": "45.1.2.3", "port": 5555, "username": "u1", "password": "p1",
                "country_code": "de", "valid": True,
            },
            {"proxy_address": "45.1.2.4", "port": 5555, "username": "u2", "password": "p2", "valid": False},
            {"proxy_address": None, "port": 5555, "valid": True},
            {"proxy_address": "45.1.2.5", "port": "not-an-int", "valid": True},
        ],
    }
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(return_value=page)
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = fake_response

    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", "test-key"), \
         patch("app.services.proxy_service.httpx.Client", return_value=fake_client):
        result = proxy_service.fetch_proxies_from_webshare()

    assert result == [{
        "host": "45.1.2.3", "port": 5555, "username": "u1", "password": "p1",
        "protocol": "http", "type": "residential", "country": "DE", "provider": "webshare",
        "is_rotating": False,
    }]


def test_webshare_fetcher_returns_empty_on_request_failure():
    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", "test-key"), \
         patch("app.services.proxy_service.httpx.Client", side_effect=Exception("401 unauthorized")):
        assert proxy_service.fetch_proxies_from_webshare() == []


@pytest.mark.asyncio
async def test_imported_proxies_keep_their_credentials(db_session):
    """Webshare's username/password have to survive the import, or its proxies
    are imported as unauthenticated and fail every health check."""
    from sqlalchemy import select
    from app.models.proxy import Proxy

    scraped = [{
        "host": "45.9.9.9", "port": 5555, "username": "wsuser", "password": "wspass",
        "protocol": "http", "type": "residential", "country": "DE", "provider": "webshare",
    }]
    with patch("app.services.proxy_service.fetch_all_free_proxies", return_value=scraped):
        result = await proxy_service.import_proxies_from_free_list(db_session)
    assert result.get("error") is None

    row = (await db_session.execute(select(Proxy).where(Proxy.host == "45.9.9.9"))).scalar_one()
    assert row.username == "wsuser"
    assert row.password == "wspass"


# --- Rotating endpoint --------------------------------------------------------

def test_rotating_endpoint_is_none_without_proxy_credentials():
    with patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", ""), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", ""):
        assert proxy_service.webshare_rotating_endpoint() is None


def test_rotating_endpoint_is_flagged_and_carries_its_credentials():
    """is_rotating is what stops the pipeline retiring this after one signup, and
    the credentials are what make it authenticate at all."""
    with patch("app.services.proxy_service.settings.WEBSHARE_PROXY_HOST", "p.webshare.io"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PORT", 80), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "u"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "p"):
        entry = proxy_service.webshare_rotating_endpoint()

    assert entry == {
        "host": "p.webshare.io", "port": 80, "username": "u", "password": "p",
        "protocol": "http", "type": "residential", "country": "UN",
        "provider": "webshare", "is_rotating": True,
    }


def test_webshare_returns_the_rotating_endpoint_without_an_api_key():
    """The two Webshare modes are independent - proxy credentials alone are
    enough, no API key needed."""
    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", ""), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_HOST", "p.webshare.io"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "u"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "p"):
        rows = proxy_service.fetch_proxies_from_webshare()

    assert len(rows) == 1
    assert rows[0]["is_rotating"] is True


def test_a_failing_api_key_still_leaves_the_rotating_endpoint():
    """An expired API key must not take the rest of Webshare down with it."""
    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", "expired"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_HOST", "p.webshare.io"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "u"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "p"), \
         patch("app.services.proxy_service.httpx.Client", side_effect=Exception("401")):
        rows = proxy_service.fetch_proxies_from_webshare()

    assert len(rows) == 1 and rows[0]["is_rotating"] is True


@pytest.mark.asyncio
async def test_a_rotating_endpoint_serves_many_identities_without_being_retired(db_session):
    """The one exception to "one proxy, one identity, then retired". Every
    connection through a rotating endpoint exits from a different IP, so reusing
    the row does not reuse an address - and retiring it after the first signup
    would make the whole subscription useless."""
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.services import identity_service

    rotating = Proxy(
        host="p.webshare.io", port=80, username="u", password="p",
        protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="UN", provider="webshare", is_rotating=True,
    )
    db_session.add(rotating)
    await db_session.commit()

    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    # Three different identities all succeed in claiming it...
    for identity_id in (first, second, third):
        assert await identity_service._claim_and_consume_free_proxy(db_session, rotating.id, identity_id) is True

    await db_session.refresh(rotating)
    # ...and it is neither locked to any of them nor retired.
    assert rotating.assigned_bot_id is None
    assert rotating.consumed_at is None

    # Reserving is the same story.
    assert await identity_service._reserve_free_proxy_for(db_session, rotating.id, first) is True
    await db_session.refresh(rotating)
    assert rotating.assigned_bot_id is None

    # And it is still offered as a candidate afterwards.
    assert rotating.id in {c.id for c in await identity_service.list_free_proxy_candidates(db_session)}


@pytest.mark.asyncio
async def test_a_fixed_proxy_is_still_exclusive(db_session):
    """The rotating exemption must not leak into ordinary proxies - two
    identities sharing a fixed IP is exactly what the whole scheme prevents."""
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.services import identity_service

    fixed = Proxy(
        host="203.0.113.240", port=8080, protocol=ProxyProtocol.http,
        type=ProxyType.residential, country="US", provider="webshare", is_rotating=False,
    )
    db_session.add(fixed)
    await db_session.commit()

    assert await identity_service._claim_and_consume_free_proxy(db_session, fixed.id, uuid.uuid4()) is True
    assert await identity_service._claim_and_consume_free_proxy(db_session, fixed.id, uuid.uuid4()) is False

    await db_session.refresh(fixed)
    assert fixed.consumed_at is not None


@pytest.mark.asyncio
async def test_pool_refresh_leaves_the_rotating_endpoint_alone(db_session):
    """A rotating endpoint is a standing subscription, not a scraped address that
    goes stale - churning the row every two minutes could pull it out from under
    a run mid-flight."""
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    rotating = Proxy(
        host="p.webshare.io", port=80, username="u", password="p",
        protocol=ProxyProtocol.http, type=ProxyType.residential,
        country="UN", provider="webshare", is_rotating=True,
    )
    scraped = Proxy(
        host="203.0.113.241", port=8080, protocol=ProxyProtocol.http,
        type=ProxyType.datacenter, country="UN", provider="proxyscrape",
    )
    db_session.add_all([rotating, scraped])
    await db_session.commit()
    rotating_id, scraped_id = rotating.id, scraped.id

    with patch("app.services.proxy_service.fetch_all_free_proxies", return_value=[
        {"host": "203.0.113.242", "port": 8080, "protocol": "http",
         "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
    ]):
        result = await proxy_service.replace_free_proxy_pool(db_session)

    assert result.get("error") is None
    assert await db_session.get(Proxy, rotating_id) is not None, "the rotating endpoint must survive a refresh"
    assert await db_session.get(Proxy, scraped_id) is None, "an ordinary stale row should still be replaced"


@pytest.mark.asyncio
async def test_import_preserves_the_rotating_flag(db_session):
    from sqlalchemy import select
    from app.models.proxy import Proxy

    entry = {
        "host": "p.webshare.io", "port": 80, "username": "u", "password": "p",
        "protocol": "http", "type": "residential", "country": "UN",
        "provider": "webshare", "is_rotating": True,
    }
    with patch("app.services.proxy_service.fetch_all_free_proxies", return_value=[entry]):
        await proxy_service.import_proxies_from_free_list(db_session)

    row = (await db_session.execute(
        select(Proxy).where(Proxy.host == "p.webshare.io")
    )).scalars().first()
    assert row is not None and row.is_rotating is True


# --- Explicitly pasted Webshare list -----------------------------------------

def test_webshare_list_parses_the_dashboard_download_format():
    """Webshare's Dashboard -> Proxy -> List -> Download gives
    "ip:port:username:password" per line. Pasting that verbatim has to work,
    since enumerating an account otherwise needs an API key."""
    raw = (
        "31.59.20.176:6754:cfewspic:secret\n"
        "45.38.107.97:6014:cfewspic:secret\n"
    )
    with patch("app.services.proxy_service.settings.WEBSHARE_PROXY_LIST", raw):
        entries = proxy_service.parse_webshare_proxy_list(raw)

    assert [(e["host"], e["port"], e["username"], e["password"]) for e in entries] == [
        ("31.59.20.176", 6754, "cfewspic", "secret"),
        ("45.38.107.97", 6014, "cfewspic", "secret"),
    ]
    # Fixed addresses, so each is used once and retired like any other proxy.
    assert all(e["is_rotating"] is False for e in entries)
    assert all(e["provider"] == "webshare" for e in entries)


def test_webshare_list_accepts_bare_host_port_and_shared_credentials():
    with patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "shared-user"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "shared-pass"):
        entries = proxy_service.parse_webshare_proxy_list("31.59.20.176:6754")

    assert entries[0]["username"] == "shared-user"
    assert entries[0]["password"] == "shared-pass"


def test_webshare_list_tolerates_commas_comments_schemes_and_duplicates():
    raw = (
        "# my proxies\n"
        "http://31.59.20.176:6754, 45.38.107.97:6014\n"
        "\n"
        "31.59.20.176:6754\n"          # duplicate of the first
        "not-a-proxy\n"
        "9.9.9.9:notaport\n"
    )
    entries = proxy_service.parse_webshare_proxy_list(raw)
    assert [(e["host"], e["port"]) for e in entries] == [
        ("31.59.20.176", 6754),
        ("45.38.107.97", 6014),
    ]


def test_rotating_endpoint_needs_a_host_not_just_credentials():
    """An empty host used to yield a bogus ":80" proxy that got imported and then
    failed every health check - credentials alone are not an endpoint."""
    with patch("app.services.proxy_service.settings.WEBSHARE_PROXY_HOST", ""), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "u"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "p"):
        assert proxy_service.webshare_rotating_endpoint() is None


def test_every_webshare_entry_declares_is_rotating():
    """Anything reading entry["is_rotating"] directly blew up on API entries,
    which never set the key."""
    page = {"next": None, "results": [
        {"proxy_address": "45.1.2.3", "port": 5555, "username": "u", "password": "p",
         "country_code": "de", "valid": True},
    ]}
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(return_value=page)
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = fake_response

    with patch("app.services.proxy_service.settings.WEBSHARE_API_KEY", "k"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_LIST", "31.59.20.176:6754"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_USERNAME", "u"), \
         patch("app.services.proxy_service.settings.WEBSHARE_PROXY_PASSWORD", "p"), \
         patch("app.services.proxy_service.httpx.Client", return_value=fake_client):
        rows = proxy_service.fetch_proxies_from_webshare()

    assert rows, "expected the list entry and the API entry"
    assert all("is_rotating" in r for r in rows)
    # One row per address, even though both sources can name the same proxy.
    assert len({(r["host"], r["port"]) for r in rows}) == len(rows)


@pytest.mark.asyncio
async def test_listed_webshare_proxies_are_offered_to_identities(db_session):
    """End of the chain: a pasted proxy ends up as a residential candidate an
    identity can be given, with its credentials intact."""
    from app.services import identity_service

    await _all_providers_on(db_session)
    entries = [{
        "host": "31.59.20.176", "port": 6754, "username": "u", "password": "p",
        "protocol": "http", "type": "residential", "country": "GB",
        "provider": "webshare", "is_rotating": False,
    }]
    with patch("app.services.proxy_service.fetch_all_free_proxies", return_value=entries):
        result = await proxy_service.import_proxies_from_free_list(db_session)
    assert result.get("error") is None

    candidate = next(
        c for c in await identity_service.list_free_proxy_candidates(db_session)
        if c.host == "31.59.20.176"
    )
    # Credentials have to survive all the way here, or Playwright gets a 407.
    assert candidate.username == "u" and candidate.password == "p"
