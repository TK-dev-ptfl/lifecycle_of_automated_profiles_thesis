from unittest.mock import MagicMock, patch

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
         patch("app.services.proxy_service.fetch_proxies_from_proxyscrape", return_value=proxyscrape_data):
        result = await proxy_service.import_proxies_from_free_list(db_session)

    assert result["imported"] == 2
    assert result.get("error") is None

    all_proxies = await proxy_service.get_proxies(db_session)
    hosts = {p.host for p in all_proxies}
    assert "203.0.113.10" in hosts
    assert "203.0.113.20" in hosts
