"""
Tests for borrow endpoints:
  POST   /borrow          — borrow a book
  GET    /borrow          — list all borrows (admin)
  GET    /borrow/my       — list current user's borrows
  GET    /borrow/{id}     — get single borrow record
  PUT    /borrow/{id}/return  — return a book
  DELETE /borrow/{id}     — admin hard-delete
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.system.cache import cache_flush_all

SQLALCHEMY_TEST_URL = "sqlite:///./test_borrow.db"

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
    cache_flush_all()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ── Auth / resource helpers ───────────────────────────────────────────────────

def register_and_login(client: TestClient,
                       username: str, email: str,
                       password: str = "StrongPass123!",
                       role: str = "user") -> str:
    client.post("/auth/register", json={
        "username": username, "email": email,
        "password": password, "role": role,
    })
    res = client.post("/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_book(client: TestClient, admin_token: str, quantity: int = 3) -> int:
    res = client.post("/books", json={
        "title": "Test Book",
        "author": "Author X",
        "isbn": "9780132350884",
        "description": "A test book",
        "quantity": quantity,
    }, headers=auth_headers(admin_token))
    assert res.status_code == 201
    return res.json()["id"]


# ── POST /borrow ──────────────────────────────────────────────────────────────

class TestBorrowBook:
    def test_user_can_borrow_available_book(self, client):
        admin_token = register_and_login(
            client, "admin1", "admin1@test.com", role="admin")
        user_token = register_and_login(
            client, "user1", "user1@test.com", role="user")
        book_id = create_book(client, admin_token)

        res = client.post("/borrow", json={"book_id": book_id},
                          headers=auth_headers(user_token))
        assert res.status_code == 201
        data = res.json()
        assert data["book_id"] == book_id
        assert data["returned"] is False

    def test_cannot_borrow_nonexistent_book(self, client):
        user_token = register_and_login(
            client, "user2", "user2@test.com", role="user")
        res = client.post("/borrow", json={"book_id": 99999},
                          headers=auth_headers(user_token))
        assert res.status_code == 404

    def test_cannot_borrow_out_of_stock_book(self, client):
        admin_token = register_and_login(
            client, "admin2", "admin2@test.com", role="admin")
        user_token = register_and_login(
            client, "user3", "user3@test.com", role="user")
        book_id = create_book(client, admin_token, quantity=1)

        client.post("/borrow", json={"book_id": book_id},
                    headers=auth_headers(user_token))
        # second borrow when quantity=1 should fail
        res = client.post("/borrow", json={"book_id": book_id},
                          headers=auth_headers(user_token))
        assert res.status_code == 400

    def test_unauthenticated_cannot_borrow(self, client):
        res = client.post("/borrow", json={"book_id": 1})
        assert res.status_code == 401


# ── GET /borrow (admin) ───────────────────────────────────────────────────────

class TestListBorrows:
    def test_admin_can_list_all_borrows(self, client):
        admin_token = register_and_login(
            client, "admin3", "admin3@test.com", role="admin")
        res = client.get("/borrow", headers=auth_headers(admin_token))
        assert res.status_code == 200
        assert isinstance(res.json(), list) or "items" in res.json()

    def test_user_cannot_list_all_borrows(self, client):
        user_token = register_and_login(
            client, "user4", "user4@test.com", role="user")
        res = client.get("/borrow", headers=auth_headers(user_token))
        assert res.status_code == 403

    def test_unauthenticated_cannot_list(self, client):
        res = client.get("/borrow")
        assert res.status_code == 401


# ── GET /borrow/my ────────────────────────────────────────────────────────────

class TestMyBorrows:
    def test_user_sees_own_borrows(self, client):
        admin_token = register_and_login(
            client, "admin4", "admin4@test.com", role="admin")
        user_token = register_and_login(
            client, "user5", "user5@test.com", role="user")
        book_id = create_book(client, admin_token)
        client.post("/borrow", json={"book_id": book_id},
                    headers=auth_headers(user_token))

        res = client.get("/borrow/my", headers=auth_headers(user_token))
        assert res.status_code == 200
        borrows = res.json() if isinstance(res.json(), list) else res.json()["items"]
        assert len(borrows) >= 1

    def test_user_does_not_see_others_borrows(self, client):
        admin_token = register_and_login(
            client, "admin5", "admin5@test.com", role="admin")
        user_a = register_and_login(
            client, "userA", "userA@test.com", role="user")
        user_b = register_and_login(
            client, "userB", "userB@test.com", role="user")
        book_id = create_book(client, admin_token)
        client.post("/borrow", json={"book_id": book_id},
                    headers=auth_headers(user_a))

        res = client.get("/borrow/my", headers=auth_headers(user_b))
        assert res.status_code == 200
        borrows = res.json() if isinstance(res.json(), list) else res.json()["items"]
        assert len(borrows) == 0


# ── PUT /borrow/{id}/return ───────────────────────────────────────────────────

class TestReturnBook:
    def _setup_borrow(self, client):
        admin_token = register_and_login(
            client, "admin6", "admin6@test.com", role="admin")
        user_token = register_and_login(
            client, "user6", "user6@test.com", role="user")
        book_id = create_book(client, admin_token)
        borrow = client.post("/borrow", json={"book_id": book_id},
                             headers=auth_headers(user_token)).json()
        return borrow["id"], user_token, admin_token

    def test_user_can_return_own_borrow(self, client):
        borrow_id, user_token, _ = self._setup_borrow(client)
        res = client.put(f"/borrow/{borrow_id}/return",
                         headers=auth_headers(user_token))
        assert res.status_code == 200
        assert res.json()["returned"] is True

    def test_cannot_return_already_returned(self, client):
        borrow_id, user_token, _ = self._setup_borrow(client)
        client.put(f"/borrow/{borrow_id}/return",
                   headers=auth_headers(user_token))
        res = client.put(f"/borrow/{borrow_id}/return",
                         headers=auth_headers(user_token))
        assert res.status_code == 400

    def test_return_nonexistent_borrow(self, client):
        _, user_token, _ = self._setup_borrow(client)
        res = client.put("/borrow/99999/return",
                         headers=auth_headers(user_token))
        assert res.status_code == 404

    def test_admin_can_return_any_borrow(self, client):
        borrow_id, _, admin_token = self._setup_borrow(client)
        res = client.put(f"/borrow/{borrow_id}/return",
                         headers=auth_headers(admin_token))
        assert res.status_code == 200


# ── DELETE /borrow/{id} (admin hard-delete) ───────────────────────────────────

class TestDeleteBorrow:
    def test_admin_can_delete_borrow_record(self, client):
        admin_token = register_and_login(
            client, "admin7", "admin7@test.com", role="admin")
        user_token = register_and_login(
            client, "user7", "user7@test.com", role="user")
        book_id = create_book(client, admin_token)
        borrow = client.post("/borrow", json={"book_id": book_id},
                             headers=auth_headers(user_token)).json()
        res = client.delete(f"/borrow/{borrow['id']}",
                            headers=auth_headers(admin_token))
        assert res.status_code in (200, 204)

    def test_user_cannot_delete_borrow_record(self, client):
        admin_token = register_and_login(
            client, "admin8", "admin8@test.com", role="admin")
        user_token = register_and_login(
            client, "user8", "user8@test.com", role="user")
        book_id = create_book(client, admin_token)
        borrow = client.post("/borrow", json={"book_id": book_id},
                             headers=auth_headers(user_token)).json()
        res = client.delete(f"/borrow/{borrow['id']}",
                            headers=auth_headers(user_token))
        assert res.status_code == 403


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestBorrowEdgeCases:
    def test_borrow_increases_active_borrow_count(self, client):
        admin_token = register_and_login(
            client, "admin9", "admin9@test.com", role="admin")
        user_token = register_and_login(
            client, "user9", "user9@test.com", role="user")
        book_id = create_book(client, admin_token, quantity=5)

        client.post("/borrow", json={"book_id": book_id},
                    headers=auth_headers(user_token))
        res = client.get("/borrow/my", headers=auth_headers(user_token))
        borrows = res.json() if isinstance(res.json(), list) else res.json()["items"]
        active = [b for b in borrows if not b.get("returned", True)]
        assert len(active) == 1

    def test_return_restores_book_availability(self, client):
        admin_token = register_and_login(
            client, "admin10", "admin10@test.com", role="admin")
        user_token = register_and_login(
            client, "user10", "user10@test.com", role="user")
        book_id = create_book(client, admin_token, quantity=1)

        borrow = client.post("/borrow", json={"book_id": book_id},
                             headers=auth_headers(user_token)).json()
        # book now unavailable
        res = client.post("/borrow", json={"book_id": book_id},
                          headers=auth_headers(user_token))
        assert res.status_code == 400

        # return it
        client.put(f"/borrow/{borrow['id']}/return",
                   headers=auth_headers(user_token))

        # should be borrowable again
        res2 = client.post("/borrow", json={"book_id": book_id},
                           headers=auth_headers(user_token))
        assert res2.status_code == 201
