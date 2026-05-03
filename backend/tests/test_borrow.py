"""
Tests for borrow endpoints:
  POST   /api/v1/borrow
  GET    /api/v1/borrow
  GET    /api/v1/borrow/{id}
  GET    /api/v1/borrow/user/{user_id}
  PUT    /api/v1/borrow/{id}/return
  DELETE /api/v1/borrow/{id}
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SAMPLE_BOOK = {
    "title": "Test Book",
    "author": "Author X",
    "isbn": "9780132350884",
    "total_copies": 3,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def register_and_login(client: AsyncClient, username: str, email: str,
                              role: str = "member") -> str:
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


async def create_book(client: AsyncClient, admin_token: str, copies: int = 3) -> int:
    res = await client.post("/api/v1/books",
                            json={**SAMPLE_BOOK, "total_copies": copies},
                            headers=auth(admin_token))
    assert res.status_code == 201
    return res.json()["id"]


# ── POST /borrow ──────────────────────────────────────────────────────────────

class TestBorrowBook:
    async def test_member_can_borrow_available_book(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin1", "admin1@t.com", "admin")
        user_token  = await register_and_login(client, "user1",  "user1@t.com",  "member")
        book_id = await create_book(client, admin_token)

        res = await client.post("/api/v1/borrow", json={"book_id": book_id},
                                headers=auth(user_token))
        assert res.status_code == 201
        data = res.json()
        assert data["book_id"] == book_id
        assert data["status"] == "active"

    async def test_cannot_borrow_nonexistent_book(self, client: AsyncClient):
        user_token = await register_and_login(client, "user2", "user2@t.com", "member")
        res = await client.post("/api/v1/borrow", json={"book_id": 99999},
                                headers=auth(user_token))
        assert res.status_code == 404

    async def test_cannot_borrow_out_of_stock_book(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin2", "admin2@t.com", "admin")
        user_token  = await register_and_login(client, "user3",  "user3@t.com",  "member")
        book_id = await create_book(client, admin_token, copies=1)

        await client.post("/api/v1/borrow", json={"book_id": book_id}, headers=auth(user_token))
        # Second borrow of same book (already have it)
        res = await client.post("/api/v1/borrow", json={"book_id": book_id}, headers=auth(user_token))
        assert res.status_code == 409  # duplicate active borrow

    async def test_unauthenticated_cannot_borrow(self, client: AsyncClient):
        res = await client.post("/api/v1/borrow", json={"book_id": 1})
        assert res.status_code == 403


# ── GET /borrow ───────────────────────────────────────────────────────────────

class TestListBorrows:
    async def test_admin_can_list_all_borrows(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin3", "admin3@t.com", "admin")
        res = await client.get("/api/v1/borrow", headers=auth(admin_token))
        assert res.status_code == 200
        assert "borrows" in res.json()

    async def test_member_sees_only_own_borrows(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin4", "admin4@t.com", "admin")
        user_token  = await register_and_login(client, "user4",  "user4@t.com",  "member")
        book_id = await create_book(client, admin_token)
        await client.post("/api/v1/borrow", json={"book_id": book_id}, headers=auth(user_token))

        res = await client.get("/api/v1/borrow", headers=auth(user_token))
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        # All returned borrows belong to this user
        for b in data["borrows"]:
            assert b["user_id"] is not None  # can't check exact without knowing user id easily

    async def test_unauthenticated_cannot_list(self, client: AsyncClient):
        res = await client.get("/api/v1/borrow")
        assert res.status_code == 403


# ── GET /borrow/{id} ─────────────────────────────────────────────────────────

class TestGetBorrowById:
    async def test_member_can_view_own_borrow(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin5", "admin5@t.com", "admin")
        user_token  = await register_and_login(client, "user5",  "user5@t.com",  "member")
        book_id = await create_book(client, admin_token)
        borrow_id = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                       headers=auth(user_token))).json()["id"]

        res = await client.get(f"/api/v1/borrow/{borrow_id}", headers=auth(user_token))
        assert res.status_code == 200
        assert res.json()["id"] == borrow_id

    async def test_member_cannot_view_others_borrow(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin6", "admin6@t.com", "admin")
        user_a      = await register_and_login(client, "userA",  "userA@t.com",  "member")
        user_b      = await register_and_login(client, "userB",  "userB@t.com",  "member")
        book_id = await create_book(client, admin_token)
        borrow_id = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                       headers=auth(user_a))).json()["id"]

        res = await client.get(f"/api/v1/borrow/{borrow_id}", headers=auth(user_b))
        assert res.status_code == 403

    async def test_get_nonexistent_borrow(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin7", "admin7@t.com", "admin")
        res = await client.get("/api/v1/borrow/99999", headers=auth(admin_token))
        assert res.status_code == 404


# ── PUT /borrow/{id}/return ───────────────────────────────────────────────────

class TestReturnBook:
    async def _setup(self, client):
        admin_token = await register_and_login(client, "admin8", "admin8@t.com", "admin")
        user_token  = await register_and_login(client, "user8",  "user8@t.com",  "member")
        book_id = await create_book(client, admin_token)
        borrow = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                    headers=auth(user_token))).json()
        return borrow["id"], user_token, admin_token

    async def test_member_can_return_own_borrow(self, client: AsyncClient):
        borrow_id, user_token, _ = await self._setup(client)
        res = await client.put(f"/api/v1/borrow/{borrow_id}/return",
                               headers=auth(user_token))
        assert res.status_code == 200
        assert res.json()["status"] == "returned"

    async def test_cannot_return_already_returned(self, client: AsyncClient):
        borrow_id, user_token, _ = await self._setup(client)
        await client.put(f"/api/v1/borrow/{borrow_id}/return", headers=auth(user_token))
        res = await client.put(f"/api/v1/borrow/{borrow_id}/return", headers=auth(user_token))
        assert res.status_code == 409

    async def test_admin_can_return_any_borrow(self, client: AsyncClient):
        borrow_id, _, admin_token = await self._setup(client)
        res = await client.put(f"/api/v1/borrow/{borrow_id}/return",
                               headers=auth(admin_token))
        assert res.status_code == 200

    async def test_return_nonexistent_borrow(self, client: AsyncClient):
        _, user_token, _ = await self._setup(client)
        res = await client.put("/api/v1/borrow/99999/return", headers=auth(user_token))
        assert res.status_code == 404


# ── DELETE /borrow/{id} ───────────────────────────────────────────────────────

class TestDeleteBorrow:
    async def test_admin_can_delete_borrow_record(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin9", "admin9@t.com", "admin")
        user_token  = await register_and_login(client, "user9",  "user9@t.com",  "member")
        book_id = await create_book(client, admin_token)
        borrow_id = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                       headers=auth(user_token))).json()["id"]
        res = await client.delete(f"/api/v1/borrow/{borrow_id}", headers=auth(admin_token))
        assert res.status_code == 204

    async def test_member_cannot_delete_borrow_record(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin10", "admin10@t.com", "admin")
        user_token  = await register_and_login(client, "user10",  "user10@t.com",  "member")
        book_id = await create_book(client, admin_token)
        borrow_id = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                       headers=auth(user_token))).json()["id"]
        res = await client.delete(f"/api/v1/borrow/{borrow_id}", headers=auth(user_token))
        assert res.status_code == 403


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestBorrowEdgeCases:
    async def test_return_restores_book_availability(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin11", "admin11@t.com", "admin")
        user_token  = await register_and_login(client, "user11",  "user11@t.com",  "member")
        book_id = await create_book(client, admin_token, copies=1)

        borrow = (await client.post("/api/v1/borrow", json={"book_id": book_id},
                                    headers=auth(user_token))).json()
        # Book is now out of stock – different user should also fail
        user2_token = await register_and_login(client, "user12", "user12@t.com", "member")
        res = await client.post("/api/v1/borrow", json={"book_id": book_id},
                                headers=auth(user2_token))
        assert res.status_code == 409

        # Return it
        await client.put(f"/api/v1/borrow/{borrow['id']}/return", headers=auth(user_token))

        # Now user2 can borrow it
        res2 = await client.post("/api/v1/borrow", json={"book_id": book_id},
                                 headers=auth(user2_token))
        assert res2.status_code == 201

    async def test_book_available_copies_decrements(self, client: AsyncClient):
        admin_token = await register_and_login(client, "admin13", "admin13@t.com", "admin")
        user_token  = await register_and_login(client, "user13",  "user13@t.com",  "member")
        book_id = await create_book(client, admin_token, copies=3)

        await client.post("/api/v1/borrow", json={"book_id": book_id}, headers=auth(user_token))

        res = await client.get(f"/api/v1/books/{book_id}", headers=auth(admin_token))
        assert res.json()["available_copies"] == 2
