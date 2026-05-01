"""
Tests for authentication endpoints:
  POST /auth/register
  POST /auth/login
  GET  /auth/me  (protected)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db

# ── In-memory SQLite test database ───────────────────────────────────────────
SQLALCHEMY_TEST_URL = "sqlite:///./test_auth.db"

engine = create_engine(
    SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def register_user(client: TestClient, username: str = "testuser",
                  email: str = "test@example.com",
                  password: str = "StrongPass123!",
                  role: str = "user"):
    return client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
        "role": role,
    })


def login_user(client: TestClient, email: str = "test@example.com",
               password: str = "StrongPass123!"):
    return client.post("/auth/login", json={
        "email": email,
        "password": password,
    })


# ── Registration tests ────────────────────────────────────────────────────────

class TestRegister:
    def test_register_success(self, client):
        res = register_user(client)
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "test@example.com"
        assert "password" not in data  # password must never be returned

    def test_register_duplicate_email(self, client):
        register_user(client)
        res = register_user(client)
        assert res.status_code == 400

    def test_register_invalid_email(self, client):
        res = register_user(client, email="not-an-email")
        assert res.status_code == 422

    def test_register_weak_password(self, client):
        res = register_user(client, password="123")
        assert res.status_code == 422

    def test_register_missing_fields(self, client):
        res = client.post("/auth/register", json={"email": "x@x.com"})
        assert res.status_code == 422


# ── Login tests ───────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_success_returns_token(self, client):
        register_user(client)
        res = login_user(client)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        register_user(client)
        res = login_user(client, password="wrongpass")
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = login_user(client, email="ghost@example.com")
        assert res.status_code == 401

    def test_login_missing_fields(self, client):
        res = client.post("/auth/login", json={"email": "test@example.com"})
        assert res.status_code == 422


# ── Protected endpoint /auth/me ───────────────────────────────────────────────

class TestGetMe:
    def _get_token(self, client) -> str:
        register_user(client)
        res = login_user(client)
        return res.json()["access_token"]

    def test_get_me_authenticated(self, client):
        token = self._get_token(client)
        res = client.get("/auth/me",
                         headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "test@example.com"

    def test_get_me_no_token(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401

    def test_get_me_invalid_token(self, client):
        res = client.get("/auth/me",
                         headers={"Authorization": "Bearer totally_fake_token"})
        assert res.status_code == 401


# ── Role-based tests ──────────────────────────────────────────────────────────

class TestRoles:
    def test_admin_role_assigned(self, client):
        res = register_user(client, username="admin1",
                            email="admin@example.com", role="admin")
        assert res.status_code == 201
        assert res.json()["role"] == "admin"

    def test_default_role_is_user(self, client):
        res = client.post("/auth/register", json={
            "username": "plain",
            "email": "plain@example.com",
            "password": "StrongPass123!",
        })
        assert res.status_code == 201
        assert res.json()["role"] == "user"
