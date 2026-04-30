"""
app/books/service.py
────────────────────
Business-logic layer for the Books module.

Responsibilities
----------------
• CRUD operations against the database (async SQLAlchemy)
• Cache-Aside pattern with Redis
  – GET all / GET by ID  →  read-through cache (TTL from settings)
  – POST / PUT / DELETE  →  invalidate affected cache keys
• Raises HTTPException (404 / 409) so routes stay thin

Cache key convention
--------------------
  books:all          – serialised list of all books
  books:{id}         – serialised single book
"""

import json
import logging
from typing import Optional

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.books.model import Book
from app.books.schemas import BookCreate, BookUpdate
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

CACHE_KEY_ALL = "books:all"


def _book_cache_key(book_id: int) -> str:
    return f"books:{book_id}"


async def _cache_get(redis: Optional[Redis], key: str) -> Optional[dict | list]:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        if raw:
            logger.debug("Cache HIT  key=%s", key)
            return json.loads(raw)
        logger.debug("Cache MISS key=%s", key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis GET failed key=%s error=%s", key, exc)
    return None


async def _cache_set(redis: Optional[Redis], key: str, data: dict | list) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(data, default=str), ex=settings.CACHE_EXPIRE_SECONDS)
        logger.debug("Cache SET  key=%s ttl=%ss", key, settings.CACHE_EXPIRE_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis SET failed key=%s error=%s", key, exc)


async def _cache_invalidate(redis: Optional[Redis], *keys: str) -> None:
    if redis is None:
        return
    try:
        await redis.delete(*keys)
        logger.debug("Cache DEL  keys=%s", keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis DEL failed keys=%s error=%s", keys, exc)


def _book_to_dict(book: Book) -> dict:
    """Convert ORM Book to a JSON-serialisable dict (matches BookResponse)."""
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "description": book.description,
        "published_year": book.published_year,
        "total_copies": book.total_copies,
        "available_copies": book.available_copies,
        "is_available": book.is_available,
        "created_at": book.created_at.isoformat(),
        "updated_at": book.updated_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Service functions
# ─────────────────────────────────────────────────────────────────────────────

async def get_all_books(
    db: AsyncSession,
    redis: Optional[Redis] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Book], int]:
    """
    Return (books, total_count).
    Caches the full list (skip=0, limit=20) only to avoid cache-key explosion.
    """
    use_cache = skip == 0 and limit == 20

    if use_cache:
        cached = await _cache_get(redis, CACHE_KEY_ALL)
        if cached is not None:
            # Return ORM-less dicts – routes will use BookResponse.model_validate()
            return cached["books"], cached["total"]  # type: ignore[return-value]

    # Database query
    count_result = await db.execute(select(func.count()).select_from(Book))
    total: int = count_result.scalar_one()

    result = await db.execute(select(Book).offset(skip).limit(limit))
    books: list[Book] = list(result.scalars().all())

    if use_cache:
        payload = {"total": total, "books": [_book_to_dict(b) for b in books]}
        await _cache_set(redis, CACHE_KEY_ALL, payload)

    return books, total


async def get_book_by_id(
    book_id: int,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Book:
    """Return a single Book or raise 404."""
    cached = await _cache_get(redis, _book_cache_key(book_id))
    if cached is not None:
        return cached  # type: ignore[return-value]  # route validates via BookResponse

    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalars().first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id={book_id} not found.",
        )

    await _cache_set(redis, _book_cache_key(book_id), _book_to_dict(book))
    return book


async def create_book(
    book_in: BookCreate,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Book:
    """Create a new book record. Raises 409 if ISBN already exists."""
    if book_in.isbn:
        existing = await db.execute(select(Book).where(Book.isbn == book_in.isbn))
        if existing.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A book with ISBN '{book_in.isbn}' already exists.",
            )

    book = Book(
        title=book_in.title,
        author=book_in.author,
        isbn=book_in.isbn,
        description=book_in.description,
        published_year=book_in.published_year,
        total_copies=book_in.total_copies,
        available_copies=book_in.total_copies,  # all copies start as available
    )
    db.add(book)
    await db.flush()
    await db.refresh(book)

    # Invalidate list cache; individual key doesn't exist yet
    await _cache_invalidate(redis, CACHE_KEY_ALL)
    logger.info("Book created id=%s title=%r", book.id, book.title)
    return book


async def update_book(
    book_id: int,
    book_in: BookUpdate,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Book:
    """Partial update. Raises 404 if book doesn't exist, 409 on ISBN clash."""
    book = await get_book_by_id(book_id, db)  # raises 404 if missing

    update_data = book_in.model_dump(exclude_unset=True)

    # Guard: can't have available_copies > total_copies after update
    new_total = update_data.get("total_copies", book.total_copies)
    new_avail = update_data.get("available_copies", book.available_copies)
    if new_avail > new_total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="available_copies cannot exceed total_copies.",
        )

    # ISBN uniqueness check
    new_isbn = update_data.get("isbn")
    if new_isbn and new_isbn != book.isbn:
        clash = await db.execute(select(Book).where(Book.isbn == new_isbn))
        if clash.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A book with ISBN '{new_isbn}' already exists.",
            )

    for field, value in update_data.items():
        setattr(book, field, value)

    await db.flush()
    await db.refresh(book)

    # Invalidate both caches
    await _cache_invalidate(redis, CACHE_KEY_ALL, _book_cache_key(book_id))
    logger.info("Book updated id=%s", book_id)
    return book


async def delete_book(
    book_id: int,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> None:
    """Delete a book. Raises 404 if not found, 409 if copies are currently borrowed."""
    book = await get_book_by_id(book_id, db)  # raises 404 if missing

    borrowed = book.total_copies - book.available_copies
    if borrowed > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot delete book id={book_id}: "
                f"{borrowed} copy/copies are currently borrowed."
            ),
        )

    await db.delete(book)
    await db.flush()

    # Invalidate both caches
    await _cache_invalidate(redis, CACHE_KEY_ALL, _book_cache_key(book_id))
    logger.info("Book deleted id=%s title=%r", book_id, book.title)
