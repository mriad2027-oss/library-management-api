"""
app/borrow/routes.py
────────────────────
FastAPI router for the Borrow module (M4).

Endpoints
---------
POST   /api/v1/borrow                      – borrow a book        (Member / Admin)
PUT    /api/v1/borrow/{id}/return          – return a book        (borrower or Admin)
GET    /api/v1/borrow                      – list borrows         (own for Member; all for Admin)
GET    /api/v1/borrow/{id}                 – get borrow by ID     (own for Member; any for Admin)
GET    /api/v1/borrow/user/{user_id}       – borrows by user      (Admin only)
DELETE /api/v1/borrow/{id}                 – hard-delete record   (Admin only)

Authentication
--------------
All endpoints require a valid JWT Bearer token (get_current_user from M2).
Role-based checks are enforced inside service / permissions (M4).

Caching
-------
GET endpoints use Redis Cache-Aside (handled in service.py).
Mutating endpoints invalidate relevant cache keys.
Redis is optional – graceful degradation to DB if unavailable.

Compatibility
-------------
• get_current_user / require_admin from app.auth.dependencies  (M2)
• get_db from app.core.database                                (M1)
• Redis via app.system.cache (M5) – same lazy import as books/routes.py
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.borrow import service
from app.borrow.model import BorrowStatus
from app.borrow.schemas import BorrowCreate, BorrowListResponse, BorrowResponse, borrow_to_response
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Redis dependency  (mirrors books/routes.py – M3)
# ─────────────────────────────────────────────────────────────────────────────

async def get_redis() -> Optional[Redis]:
    """
    Try to return a shared Redis client from M5.
    Returns None silently if Redis / M5 is unavailable.
    """
    try:
        from app.system.cache import get_redis_client  # M5
        return await get_redis_client()
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# POST /borrow  – borrow a book
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=BorrowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Borrow a book",
    description=(
        "Checks out a book for the authenticated user. "
        "Fails with 409 if the book has no available copies, "
        "the user has reached their borrow limit, or they already "
        "have an active borrow for the same book."
    ),
)
async def borrow_book(
    borrow_in: BorrowCreate,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> BorrowResponse:
    borrow = await service.borrow_book(borrow_in, current_user, db, redis)
    logger.info(
        "POST /borrow → id=%s user=%s book_id=%s",
        borrow.id, current_user.username, borrow_in.book_id,
    )
    return borrow_to_response(borrow)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /borrow/{borrow_id}/return  – return a book
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{borrow_id}/return",
    response_model=BorrowResponse,
    summary="Return a borrowed book",
    description=(
        "Marks the borrow as returned and restores the book's available copies. "
        "Members can only return their own borrows. Admins can return any."
    ),
)
async def return_book(
    borrow_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> BorrowResponse:
    borrow = await service.return_book(borrow_id, current_user, db, redis)
    logger.info(
        "PUT /borrow/%s/return user=%s",
        borrow_id, current_user.username,
    )
    return borrow_to_response(borrow)


# ─────────────────────────────────────────────────────────────────────────────
# GET /borrow  – list borrows
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=BorrowListResponse,
    summary="List borrow records",
    description=(
        "Admins receive all borrow records. "
        "Members receive only their own. "
        "Optionally filter by status: active | returned | overdue."
    ),
)
async def list_borrows(
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(20, ge=1, le=500, description="Max records to return"),
    filter_status: Optional[BorrowStatus] = Query(
        None, alias="status", description="Filter by borrow status"
    ),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> BorrowListResponse:
    borrows, total = await service.get_all_borrows(
        current_user, db, redis, skip=skip, limit=limit, filter_status=filter_status
    )
    borrow_responses = [borrow_to_response(b) for b in borrows]
    logger.info(
        "GET /borrow skip=%s limit=%s total=%s user=%s",
        skip, limit, total, current_user.username,
    )
    return BorrowListResponse(total=total, skip=skip, limit=limit, borrows=borrow_responses)


# ─────────────────────────────────────────────────────────────────────────────
# GET /borrow/user/{user_id}  – borrows by specific user  [Admin only]
# MUST be defined BEFORE /{borrow_id} to avoid route shadowing
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/user/{user_id}",
    response_model=BorrowListResponse,
    summary="List borrows for a specific user  [Admin only]",
    description="Returns all borrow records for the given user ID. Admin access required.",
)
async def list_user_borrows(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    admin: User = Depends(require_admin),
) -> BorrowListResponse:
    borrows, total = await service.get_user_borrows(user_id, admin, db, redis, skip, limit)
    borrow_responses = [borrow_to_response(b) for b in borrows]
    logger.info(
        "GET /borrow/user/%s skip=%s limit=%s admin=%s",
        user_id, skip, limit, admin.username,
    )
    return BorrowListResponse(total=total, skip=skip, limit=limit, borrows=borrow_responses)


# ─────────────────────────────────────────────────────────────────────────────
# GET /borrow/{borrow_id}  – get single borrow
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{borrow_id}",
    response_model=BorrowResponse,
    summary="Get a borrow record by ID",
    description=(
        "Members can only retrieve their own borrow records. "
        "Admins can retrieve any."
    ),
)
async def get_borrow(
    borrow_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> BorrowResponse:
    borrow = await service.get_borrow_by_id(borrow_id, current_user, db, redis)
    logger.info("GET /borrow/%s user=%s", borrow_id, current_user.username)
    return borrow_to_response(borrow)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /borrow/{borrow_id}  – hard-delete  [Admin only]
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{borrow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a borrow record  [Admin only]",
    description=(
        "Permanently removes the borrow record. "
        "If the borrow was still active, the book's available copies are restored. "
        "Admin access required."
    ),
)
async def delete_borrow(
    borrow_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    admin: User = Depends(require_admin),
) -> None:
    await service.delete_borrow(borrow_id, admin, db, redis)
    logger.info("DELETE /borrow/%s admin=%s", borrow_id, admin.username)
