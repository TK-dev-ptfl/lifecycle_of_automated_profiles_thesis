import pytest

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
