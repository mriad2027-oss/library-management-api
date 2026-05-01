"""
Tests for books endpoints:
  GET    /books
  GET    /books/{id}
  POST   /books
  PUT    /books/{id}
  DELETE /books/{id}
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.system.cache import cache_flush_all

SQLALCHEMY_TEST_URL = "sqlite:///./test_books.db"

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
    cache_flush_all()  # clear cache between tests
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_token(client: TestClient, role: str = "admin") -> str:
    email = f"{role}@books-test.com"
    client.post("/auth/register", json={
        "username": f"{role}user",
        "email": email,
        "password": "StrongPass123!",
        "role": role,
    })
    res = client.post("/auth/login", json={
        "email": email,
        "password": "StrongPass123!",
    })
    return res.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SAMPLE_BOOK = {
    "title": "Clean Code",
    "author": "Robert C. Martin",
    "isbn": "9780132350884",
    "description": "A handbook of agile software craftsmanship",
    "quantity": 5,
}


# ── GET /books ────────────────────────────────────────────────────────────────

class TestGetBooks:
    def test_get_books_unauthenticated(self, client):
        res = client.get("/books")
        assert res.status_code == 200  # public endpoint

    def test_get_books_returns_list(self, client):
        token = get_token(client)
        client.post("/books", json=SAMPLE_BOOK, headers=auth_headers(token))
        res = client.get("/books")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list) or "items" in body

    def test_get_books_empty(self, client):
        res = client.get("/books")
        assert res.status_code == 200


# ── GET /books/{id} ───────────────────────────────────────────────────────────

class TestGetBookById:
    def test_get_existing_book(self, client):
        token = get_token(client)
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(token)).json()
        res = client.get(f"/books/{created['id']}")
        assert res.status_code == 200
        assert res.json()["title"] == SAMPLE_BOOK["title"]

    def test_get_nonexistent_book(self, client):
        res = client.get("/books/99999")
        assert res.status_code == 404

    def test_get_book_cache_hit(self, client):
        """Second identical request should be served from cache."""
        token = get_token(client)
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(token)).json()
        book_id = created["id"]
        res1 = client.get(f"/books/{book_id}")
        res2 = client.get(f"/books/{book_id}")
        assert res1.status_code == res2.status_code == 200
        assert res1.json() == res2.json()


# ── POST /books ───────────────────────────────────────────────────────────────

class TestCreateBook:
    def test_admin_can_create_book(self, client):
        token = get_token(client, role="admin")
        res = client.post("/books", json=SAMPLE_BOOK,
                          headers=auth_headers(token))
        assert res.status_code == 201
        assert res.json()["title"] == SAMPLE_BOOK["title"]

    def test_user_cannot_create_book(self, client):
        token = get_token(client, role="user")
        res = client.post("/books", json=SAMPLE_BOOK,
                          headers=auth_headers(token))
        assert res.status_code == 403

    def test_create_book_missing_title(self, client):
        token = get_token(client, role="admin")
        payload = {k: v for k, v in SAMPLE_BOOK.items() if k != "title"}
        res = client.post("/books", json=payload,
                          headers=auth_headers(token))
        assert res.status_code == 422

    def test_create_book_invalid_isbn(self, client):
        token = get_token(client, role="admin")
        payload = {**SAMPLE_BOOK, "isbn": "BADISBN"}
        res = client.post("/books", json=payload,
                          headers=auth_headers(token))
        assert res.status_code == 422

    def test_unauthenticated_cannot_create(self, client):
        res = client.post("/books", json=SAMPLE_BOOK)
        assert res.status_code == 401


# ── PUT /books/{id} ───────────────────────────────────────────────────────────

class TestUpdateBook:
    def test_admin_can_update_book(self, client):
        token = get_token(client, role="admin")
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(token)).json()
        res = client.put(f"/books/{created['id']}",
                         json={**SAMPLE_BOOK, "title": "Clean Code Updated"},
                         headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["title"] == "Clean Code Updated"

    def test_update_nonexistent_book(self, client):
        token = get_token(client, role="admin")
        res = client.put("/books/99999", json=SAMPLE_BOOK,
                         headers=auth_headers(token))
        assert res.status_code == 404

    def test_user_cannot_update_book(self, client):
        admin_token = get_token(client, role="admin")
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(admin_token)).json()
        user_token = get_token(client, role="user")
        res = client.put(f"/books/{created['id']}", json=SAMPLE_BOOK,
                         headers=auth_headers(user_token))
        assert res.status_code == 403


# ── DELETE /books/{id} ────────────────────────────────────────────────────────

class TestDeleteBook:
    def test_admin_can_delete_book(self, client):
        token = get_token(client, role="admin")
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(token)).json()
        res = client.delete(f"/books/{created['id']}",
                            headers=auth_headers(token))
        assert res.status_code == 200 or res.status_code == 204

    def test_delete_clears_cache(self, client):
        token = get_token(client, role="admin")
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(token)).json()
        book_id = created["id"]
        client.get(f"/books/{book_id}")           # populate cache
        client.delete(f"/books/{book_id}",
                      headers=auth_headers(token))  # should bust cache
        res = client.get(f"/books/{book_id}")
        assert res.status_code == 404

    def test_user_cannot_delete_book(self, client):
        admin_token = get_token(client, role="admin")
        created = client.post("/books", json=SAMPLE_BOOK,
                              headers=auth_headers(admin_token)).json()
        user_token = get_token(client, role="user")
        res = client.delete(f"/books/{created['id']}",
                            headers=auth_headers(user_token))
        assert res.status_code == 403

    def test_delete_nonexistent_book(self, client):
        token = get_token(client, role="admin")
        res = client.delete("/books/99999", headers=auth_headers(token))
        assert res.status_code == 404
