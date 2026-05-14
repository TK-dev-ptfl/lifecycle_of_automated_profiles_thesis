import pytest


@pytest.mark.asyncio
async def test_fleet_summary(client, auth_headers):
    resp = await client.get("/api/fleet/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "by_status" in data
    assert "by_mode" in data


@pytest.mark.asyncio
async def test_fleet_health(client, auth_headers):
    resp = await client.get("/api/fleet/health", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_fleet_summary_with_bots(client, auth_headers, platform):
    await client.post(
        "/api/bots",
        json={"name": "FleetBot1", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    resp = await client.get("/api/fleet/summary", headers=auth_headers)
    assert resp.json()["total"] >= 1
