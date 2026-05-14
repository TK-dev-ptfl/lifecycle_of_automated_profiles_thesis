import pytest


@pytest.mark.asyncio
async def test_create_identity(client, auth_headers):
    resp = await client.post(
        "/api/identities",
        json={
            "display_name": "Alice Smith",
            "username": "alice_smith_001",
            "email": "alice@tempmail.fake",
            "email_provider": "mail.tm",
            "location": "US",
            "age": 28,
            "password": "secret123",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice_smith_001"
    assert data["status"] == "fresh"


@pytest.mark.asyncio
async def test_generate_identity(client, auth_headers):
    resp = await client.post("/api/identities/generate", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert "username" in data
    assert data["status"] == "fresh"


@pytest.mark.asyncio
async def test_list_identities(client, auth_headers):
    await client.post("/api/identities/generate", headers=auth_headers)
    resp = await client.get("/api/identities", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_filter_identities_by_status(client, auth_headers):
    resp = await client.get("/api/identities?status=fresh", headers=auth_headers)
    assert resp.status_code == 200
    for identity in resp.json():
        assert identity["status"] == "fresh"


@pytest.mark.asyncio
async def test_update_identity(client, auth_headers):
    create = await client.post("/api/identities/generate", headers=auth_headers)
    identity_id = create.json()["id"]
    resp = await client.patch(
        f"/api/identities/{identity_id}",
        json={"status": "active", "bio": "Updated bio"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_identity(client, auth_headers):
    create = await client.post("/api/identities/generate", headers=auth_headers)
    identity_id = create.json()["id"]
    resp = await client.delete(f"/api/identities/{identity_id}", headers=auth_headers)
    assert resp.status_code == 204
    get = await client.get(f"/api/identities/{identity_id}", headers=auth_headers)
    assert get.status_code == 404
