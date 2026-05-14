import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    resp = await client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    resp = await client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    resp = await client.post("/api/auth/login", data={"username": "ghost", "password": "pass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client):
    login = await client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_logout(client, auth_headers):
    resp = await client.post("/api/auth/logout", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_route_without_token(client):
    resp = await client.get("/api/bots")
    assert resp.status_code == 401
