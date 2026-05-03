"""
Tests for books endpoints:
  GET    /api/v1/books
  GET    /api/v1/books/{id}
  POST   /api/v1/books
  PUT    /api/v1/books/{id}
  DELETE /api/v1/books/{id}
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SAMPLE_BOOK = {
    "title": "Clean Code",
    "author": "Robert C. Martin",
    "isbn": "9780132350884",
    "description": "A handbook of agile software craftsmanship",
    "total_copies": 5,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_token(client: AsyncClient, role: str = "admin") -> str:
    username = f"{role}user_{role}"
    email = f"{role}@books-test.com"
    await client.post("/api/v1/auth/register", json={
        "username": username, "email": email,
        "password": "StrongPass123!", "role": role,
    })
    res = await client.post("/api/v1/auth/login", json={
        "username": username, "password": "StrongPass123!"
    })
    return res.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── GET /books ────────────────────────────────────────────────────────────────

class TestGetBooks:
    async def test_get_books_unauthenticated(self, client: AsyncClient):
        res = await client.get("/api/v1/books")
        assert res.status_code == 403  # requires login

    async def test_get_books_returns_list(self, client: AsyncClient):
        token = await get_token(client, "admin")
        await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))
        res = await client.get("/api/v1/books", headers=auth(token))
        assert res.status_code == 200
        body = res.json()
        assert "books" in body
        assert body["total"] >= 1

    async def test_get_books_empty(self, client: AsyncClient):
        token = await get_token(client, "member")
        res = await client.get("/api/v1/books", headers=auth(token))
        assert res.status_code == 200
        assert res.json()["total"] == 0


# ── GET /books/{id} ───────────────────────────────────────────────────────────

class TestGetBookById:
    async def test_get_existing_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))).json()
        res = await client.get(f"/api/v1/books/{created['id']}", headers=auth(token))
        assert res.status_code == 200
        assert res.json()["title"] == SAMPLE_BOOK["title"]

    async def test_get_nonexistent_book(self, client: AsyncClient):
        token = await get_token(client, "member")
        res = await client.get("/api/v1/books/99999", headers=auth(token))
        assert res.status_code == 404

    async def test_get_book_twice_same_result(self, client: AsyncClient):
        token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))).json()
        r1 = await client.get(f"/api/v1/books/{created['id']}", headers=auth(token))
        r2 = await client.get(f"/api/v1/books/{created['id']}", headers=auth(token))
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]


# ── POST /books ───────────────────────────────────────────────────────────────

class TestCreateBook:
    async def test_admin_can_create_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        res = await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))
        assert res.status_code == 201
        assert res.json()["title"] == SAMPLE_BOOK["title"]

    async def test_member_cannot_create_book(self, client: AsyncClient):
        token = await get_token(client, "member")
        res = await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))
        assert res.status_code == 403

    async def test_create_book_missing_title(self, client: AsyncClient):
        token = await get_token(client, "admin")
        payload = {k: v for k, v in SAMPLE_BOOK.items() if k != "title"}
        res = await client.post("/api/v1/books", json=payload, headers=auth(token))
        assert res.status_code == 422

    async def test_create_book_invalid_isbn(self, client: AsyncClient):
        token = await get_token(client, "admin")
        res = await client.post("/api/v1/books", json={**SAMPLE_BOOK, "isbn": "BADISBN"},
                                headers=auth(token))
        assert res.status_code == 422

    async def test_unauthenticated_cannot_create(self, client: AsyncClient):
        res = await client.post("/api/v1/books", json=SAMPLE_BOOK)
        assert res.status_code == 403

    async def test_duplicate_isbn_rejected(self, client: AsyncClient):
        token = await get_token(client, "admin")
        await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))
        res = await client.post("/api/v1/books",
                                json={**SAMPLE_BOOK, "title": "Other Book"},
                                headers=auth(token))
        assert res.status_code == 409


# ── PUT /books/{id} ───────────────────────────────────────────────────────────

class TestUpdateBook:
    async def test_admin_can_update_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))).json()
        res = await client.put(f"/api/v1/books/{created['id']}",
                               json={"title": "Clean Code Updated"},
                               headers=auth(token))
        assert res.status_code == 200
        assert res.json()["title"] == "Clean Code Updated"

    async def test_update_nonexistent_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        res = await client.put("/api/v1/books/99999", json={"title": "X"}, headers=auth(token))
        assert res.status_code == 404

    async def test_member_cannot_update_book(self, client: AsyncClient):
        admin_token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK,
                                     headers=auth(admin_token))).json()
        member_token = await get_token(client, "member")
        res = await client.put(f"/api/v1/books/{created['id']}",
                               json={"title": "Hacked"}, headers=auth(member_token))
        assert res.status_code == 403


# ── DELETE /books/{id} ────────────────────────────────────────────────────────

class TestDeleteBook:
    async def test_admin_can_delete_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))).json()
        res = await client.delete(f"/api/v1/books/{created['id']}", headers=auth(token))
        assert res.status_code == 204

    async def test_delete_then_404(self, client: AsyncClient):
        token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK, headers=auth(token))).json()
        await client.delete(f"/api/v1/books/{created['id']}", headers=auth(token))
        res = await client.get(f"/api/v1/books/{created['id']}", headers=auth(token))
        assert res.status_code == 404

    async def test_member_cannot_delete_book(self, client: AsyncClient):
        admin_token = await get_token(client, "admin")
        created = (await client.post("/api/v1/books", json=SAMPLE_BOOK,
                                     headers=auth(admin_token))).json()
        member_token = await get_token(client, "member")
        res = await client.delete(f"/api/v1/books/{created['id']}", headers=auth(member_token))
        assert res.status_code == 403

    async def test_delete_nonexistent_book(self, client: AsyncClient):
        token = await get_token(client, "admin")
        res = await client.delete("/api/v1/books/99999", headers=auth(token))
        assert res.status_code == 404
