"""
Tests for authentication endpoints:
  POST /api/v1/auth/register
  POST /api/v1/auth/login
  GET  /api/v1/auth/me
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "StrongPass123!",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["user"]["email"] == "alice@example.com"
        assert "access_token" in data
        assert "password" not in data["user"]

    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "bob", "email": "bob@example.com", "password": "StrongPass123!"}
        await client.post("/api/v1/auth/register", json=payload)
        res = await client.post("/api/v1/auth/register", json={**payload, "email": "bob2@example.com"})
        assert res.status_code == 400

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "charlie", "email": "same@example.com", "password": "StrongPass123!"
        })
        res = await client.post("/api/v1/auth/register", json={
            "username": "charlie2", "email": "same@example.com", "password": "StrongPass123!"
        })
        assert res.status_code == 400

    async def test_register_invalid_email(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "username": "dave", "email": "not-an-email", "password": "StrongPass123!"
        })
        assert res.status_code == 422

    async def test_register_weak_password(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "username": "eve", "email": "eve@example.com", "password": "123"
        })
        assert res.status_code == 422

    async def test_register_missing_fields(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={"email": "x@x.com"})
        assert res.status_code == 422

    async def test_default_role_is_member(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "username": "frank", "email": "frank@example.com", "password": "StrongPass123!"
        })
        assert res.status_code == 201
        assert res.json()["user"]["role"] == "member"

    async def test_admin_role_assigned(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/register", json={
            "username": "admin1", "email": "admin@example.com",
            "password": "StrongPass123!", "role": "admin"
        })
        assert res.status_code == 201
        assert res.json()["user"]["role"] == "admin"


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    async def _register(self, client, username="loginuser", email="login@example.com"):
        await client.post("/api/v1/auth/register", json={
            "username": username, "email": email, "password": "StrongPass123!"
        })

    async def test_login_success_returns_token(self, client: AsyncClient):
        await self._register(client)
        res = await client.post("/api/v1/auth/login", json={
            "username": "loginuser", "password": "StrongPass123!"
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await self._register(client)
        res = await client.post("/api/v1/auth/login", json={
            "username": "loginuser", "password": "wrongpass"
        })
        assert res.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/login", json={
            "username": "ghost", "password": "StrongPass123!"
        })
        assert res.status_code == 401

    async def test_login_missing_fields(self, client: AsyncClient):
        res = await client.post("/api/v1/auth/login", json={"username": "x"})
        assert res.status_code == 422


# ── GET /me ───────────────────────────────────────────────────────────────────

class TestGetMe:
    async def _get_token(self, client) -> str:
        await client.post("/api/v1/auth/register", json={
            "username": "meuser", "email": "me@example.com", "password": "StrongPass123!"
        })
        res = await client.post("/api/v1/auth/login", json={
            "username": "meuser", "password": "StrongPass123!"
        })
        return res.json()["access_token"]

    async def test_get_me_authenticated(self, client: AsyncClient):
        token = await self._get_token(client)
        res = await client.get("/api/v1/auth/me",
                               headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "me@example.com"

    async def test_get_me_no_token(self, client: AsyncClient):
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 403

    async def test_get_me_invalid_token(self, client: AsyncClient):
        res = await client.get("/api/v1/auth/me",
                               headers={"Authorization": "Bearer totally.fake.token"})
        assert res.status_code == 401
