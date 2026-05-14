import pytest


@pytest.mark.asyncio
async def test_create_task(client, auth_headers, platform):
    resp = await client.post(
        "/api/tasks",
        json={
            "name": "Scrape Reddit",
            "platform_id": platform["id"],
            "type": "scrape",
            "concurrency": 2,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Scrape Reddit"
    assert data["status"] == "idle"


@pytest.mark.asyncio
async def test_list_tasks(client, auth_headers, platform):
    await client.post(
        "/api/tasks",
        json={"name": "List Task", "platform_id": platform["id"], "type": "post"},
        headers=auth_headers,
    )
    resp = await client.get("/api/tasks", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_task_lifecycle(client, auth_headers, platform):
    create = await client.post(
        "/api/tasks",
        json={"name": "Lifecycle Task", "platform_id": platform["id"], "type": "engage"},
        headers=auth_headers,
    )
    task_id = create.json()["id"]

    run = await client.post(f"/api/tasks/{task_id}/run", headers=auth_headers)
    assert run.json()["status"] == "running"

    pause = await client.post(f"/api/tasks/{task_id}/pause", headers=auth_headers)
    assert pause.json()["status"] == "paused"

    stop = await client.post(f"/api/tasks/{task_id}/stop", headers=auth_headers)
    assert stop.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_assign_unassign_bots(client, auth_headers, platform):
    task = await client.post(
        "/api/tasks",
        json={"name": "AssignTask", "platform_id": platform["id"], "type": "scrape"},
        headers=auth_headers,
    )
    task_id = task.json()["id"]

    bot = await client.post(
        "/api/bots",
        json={"name": "AssignBot", "platform_id": platform["id"]},
        headers=auth_headers,
    )
    bot_id = bot.json()["id"]

    assign = await client.post(f"/api/tasks/{task_id}/assign", json={"bot_ids": [bot_id]}, headers=auth_headers)
    assert assign.status_code == 200

    bots_resp = await client.get(f"/api/tasks/{task_id}/bots", headers=auth_headers)
    assert len(bots_resp.json()) >= 1

    unassign = await client.post(f"/api/tasks/{task_id}/unassign", json={"bot_ids": [bot_id]}, headers=auth_headers)
    assert unassign.status_code == 200


@pytest.mark.asyncio
async def test_delete_task(client, auth_headers, platform):
    create = await client.post(
        "/api/tasks",
        json={"name": "DeleteTask", "platform_id": platform["id"], "type": "monitor"},
        headers=auth_headers,
    )
    task_id = create.json()["id"]
    resp = await client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_task_not_found(client, auth_headers):
    resp = await client.get("/api/tasks/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404
