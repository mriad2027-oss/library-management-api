"""
app/books/routes.py
───────────────────
FastAPI router for the Books module (M3).

Endpoints
---------
GET    /api/v1/books          – list all books   (any authenticated user)
GET    /api/v1/books/{id}     – get book by id   (any authenticated user)
POST   /api/v1/books          – create book      (Admin only)
PUT    /api/v1/books/{id}     – update book      (Admin only)
DELETE /api/v1/books/{id}     – delete book      (Admin only)

Authentication
--------------
All endpoints require a valid JWT Bearer token.
Write operations (POST / PUT / DELETE) additionally require the 'admin' role.

Caching
-------
GET endpoints use Redis Cache-Aside (handled in service.py).
Mutating endpoints invalidate the relevant cache keys.

Redis is optional – if the Redis connection is unavailable the routes
degrade gracefully and serve directly from the database.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.books import service
from app.books.schemas import BookCreate, BookListResponse, BookResponse, BookUpdate
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Redis dependency  (optional – falls back to None if Redis is not running)
# ─────────────────────────────────────────────────────────────────────────────

async def get_redis() -> Optional[Redis]:
    """
    Try to return a Redis client.
    Returns None silently if Redis is unavailable so the app keeps working.
    The system/cache.py module (M5) owns the shared Redis pool;
    we import it lazily so this module doesn't hard-depend on M5 being present.
    """
    try:
        from app.system.cache import get_redis_client  # M5 provides this
        return await get_redis_client()
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# GET /books  – list all books
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=BookListResponse,
    summary="List all books",
    description=(
        "Returns a paginated list of all books in the library. "
        "Results are cached in Redis. Any authenticated user can call this."
    ),
)
async def list_books(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=500, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    _current_user: User = Depends(get_current_user),
) -> BookListResponse:
    books, total = await service.get_all_books(db, redis, skip=skip, limit=limit)

    # books may be raw dicts (from cache) or ORM objects (from DB)
    book_responses = [
        BookResponse.model_validate(b) for b in books
    ]

    logger.info(
        "GET /books skip=%s limit=%s total=%s user=%s",
        skip, limit, total, _current_user.username,
    )
    return BookListResponse(total=total, skip=skip, limit=limit, books=book_responses)


# ─────────────────────────────────────────────────────────────────────────────
# GET /books/{book_id}  – get single book
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{book_id}",
    response_model=BookResponse,
    summary="Get a book by ID",
)
async def get_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    _current_user: User = Depends(get_current_user),
) -> BookResponse:
    book = await service.get_book_by_id(book_id, db, redis)
    logger.info("GET /books/%s user=%s", book_id, _current_user.username)
    return BookResponse.model_validate(book)


# ─────────────────────────────────────────────────────────────────────────────
# POST /books  – create book  [Admin only]
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=BookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new book  [Admin only]",
)
async def create_book(
    book_in: BookCreate,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    admin: User = Depends(require_admin),
) -> BookResponse:
    book = await service.create_book(book_in, db, redis)
    logger.info(
        "POST /books → id=%s title=%r admin=%s",
        book.id, book.title, admin.username,
    )
    return BookResponse.model_validate(book)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /books/{book_id}  – update book  [Admin only]
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{book_id}",
    response_model=BookResponse,
    summary="Update a book  [Admin only]",
)
async def update_book(
    book_id: int,
    book_in: BookUpdate,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    admin: User = Depends(require_admin),
) -> BookResponse:
    book = await service.update_book(book_id, book_in, db, redis)
    logger.info("PUT /books/%s admin=%s", book_id, admin.username)
    return BookResponse.model_validate(book)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /books/{book_id}  – delete book  [Admin only]
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a book  [Admin only]",
    description=(
        "Permanently removes the book from the library. "
        "Returns 409 Conflict if any copies are currently borrowed."
    ),
)
async def delete_book(
    book_id: int,
    db: AsyncSession = Depends(get_db),
    redis: Optional[Redis] = Depends(get_redis),
    admin: User = Depends(require_admin),
) -> None:
    await service.delete_book(book_id, db, redis)
    logger.info("DELETE /books/%s admin=%s", book_id, admin.username)
