import pytest


@pytest.mark.asyncio
async def test_create_platform(client, auth_headers):
    resp = await client.post(
        "/api/platforms",
        json={"name": "reddit", "display_name": "Reddit", "is_enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "reddit"
    assert data["is_enabled"] is True


@pytest.mark.asyncio
async def test_list_platforms(client, auth_headers, platform):
    resp = await client.get("/api/platforms", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_platform(client, auth_headers, platform):
    resp = await client.get(f"/api/platforms/{platform['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == platform["id"]


@pytest.mark.asyncio
async def test_update_platform(client, auth_headers, platform):
    resp = await client.patch(
        f"/api/platforms/{platform['id']}",
        json={"is_enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False


@pytest.mark.asyncio
async def test_platform_not_found(client, auth_headers):
    resp = await client.get("/api/platforms/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404
