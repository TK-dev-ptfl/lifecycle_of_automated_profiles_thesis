import pytest


@pytest.mark.asyncio
async def test_list_bots_empty(client, auth_headers):
    resp = await client.get("/api/bots", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_bot(client, auth_headers, platform):
    resp = await client.post(
        "/api/bots",
        json={
            "name": "TestBot",
            "platform_id": platform["id"],
            "skeleton": "engagement_farmer",
            "mode": "growing",
            "communication_mode": "official_api",
            "behaviour_pattern": "passive",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "TestBot"
    assert data["status"] == "stopped"
    assert data["mode"] == "growing"
    return data


@pytest.mark.asyncio
async def test_get_bot(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "GetBot", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]
    resp = await client.get(f"/api/bots/{bot_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == bot_id


@pytest.mark.asyncio
async def test_get_bot_not_found(client, auth_headers):
    resp = await client.get("/api/bots/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_bot(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "UpdateMe", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]
    resp = await client.patch(f"/api/bots/{bot_id}", json={"name": "Updated"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_run_pause_stop_bot(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "StatusBot", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]

    run = await client.post(f"/api/bots/{bot_id}/run", headers=auth_headers)
    assert run.json()["status"] == "running"

    pause = await client.post(f"/api/bots/{bot_id}/pause", headers=auth_headers)
    assert pause.json()["status"] == "paused"

    stop = await client.post(f"/api/bots/{bot_id}/stop", headers=auth_headers)
    assert stop.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_set_bot_mode(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "ModeBot", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]
    resp = await client.post(f"/api/bots/{bot_id}/set-mode", json={"mode": "executing"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["mode"] == "executing"


@pytest.mark.asyncio
async def test_delete_bot(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "DeleteMe", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]
    resp = await client.delete(f"/api/bots/{bot_id}", headers=auth_headers)
    assert resp.status_code == 204

    get = await client.get(f"/api/bots/{bot_id}", headers=auth_headers)
    assert get.status_code == 404


@pytest.mark.asyncio
async def test_bot_stats(client, auth_headers, platform):
    create = await client.post(
        "/api/bots",
        json={"name": "StatsBot", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = create.json()["id"]
    resp = await client.get(f"/api/bots/{bot_id}/stats", headers=auth_headers)
    assert resp.status_code == 200
    assert "actions_today" in resp.json()


@pytest.mark.asyncio
async def test_filter_bots_by_status(client, auth_headers, platform):
    await client.post("/api/bots", json={"name": "RunningBot", "platform_id": platform["id"]}, headers=auth_headers)
    bots = await client.get("/api/bots", headers=auth_headers)
    bot_id = bots.json()[0]["id"]
    await client.post(f"/api/bots/{bot_id}/run", headers=auth_headers)

    resp = await client.get("/api/bots?status=running", headers=auth_headers)
    assert resp.status_code == 200
    assert all(b["status"] == "running" for b in resp.json())
