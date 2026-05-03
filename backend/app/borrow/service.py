"""
app/borrow/service.py
─────────────────────
Business-logic layer for the Borrow module.

Responsibilities
----------------
• Borrow a book        – check availability, borrow limit, create record
• Return a book        – mark returned, restore book.available_copies
• List borrows         – with optional filters (user_id, status, overdue)
• Get borrow by ID     – single record lookup
• Delete borrow record – admin hard-delete
• Sync overdue status  – update status field when due_date has passed
• Cache-Aside pattern  – same approach as books/service.py  (M3)

Cache key convention
--------------------
  borrows:all              – serialised list (skip=0, limit=20, no filters)
  borrows:user:{user_id}   – borrows for a specific user (skip=0, limit=20)
  borrows:{id}             – single borrow record

All mutating operations invalidate relevant keys.

Compatibility
-------------
• AsyncSession from app.core.database   (M1)
• settings from app.core.config         (M1)  – MAX_BORROW_LIMIT, CACHE_EXPIRE_SECONDS
• User from app.models.user             (M1)
• Book from app.books.model             (M3)
• Borrow / BorrowStatus from .model     (M4)
• Permission helpers from .permissions  (M4)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.books.model import Book
from app.borrow.model import Borrow, BorrowStatus
from app.borrow.permissions import (
    assert_borrow_limit_not_reached,
    assert_can_delete_borrow,
    assert_can_return_borrow,
    assert_can_view_borrow,
)
from app.borrow.schemas import BorrowCreate
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers  (mirrors books/service.py style – M3)
# ─────────────────────────────────────────────────────────────────────────────

CACHE_KEY_ALL = "borrows:all"


def _borrow_cache_key(borrow_id: int) -> str:
    return f"borrows:{borrow_id}"


def _user_borrows_cache_key(user_id: int) -> str:
    return f"borrows:user:{user_id}"


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
        await redis.set(
            key,
            json.dumps(data, default=str),
            ex=settings.CACHE_EXPIRE_SECONDS,
        )
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


def _borrow_to_dict(borrow: Borrow) -> dict:
    """Convert ORM Borrow (with loaded relationships) to a JSON-serialisable dict."""
    book_info = None
    if borrow.book:
        book_info = {
            "id": borrow.book.id,
            "title": borrow.book.title,
            "author": borrow.book.author,
            "isbn": borrow.book.isbn,
        }
    user_info = None
    if borrow.user:
        user_info = {
            "id": borrow.user.id,
            "username": borrow.user.username,
            "email": borrow.user.email,
        }
    return {
        "id": borrow.id,
        "user_id": borrow.user_id,
        "book_id": borrow.book_id,
        "borrowed_at": borrow.borrowed_at.isoformat(),
        "due_date": borrow.due_date.isoformat(),
        "returned_at": borrow.returned_at.isoformat() if borrow.returned_at else None,
        "status": borrow.status,
        "is_overdue": borrow.is_overdue,
        "book": book_info,
        "user": user_info,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_borrow_or_404(borrow_id: int, db: AsyncSession) -> Borrow:
    """Fetch a single Borrow with relationships loaded; raise 404 if missing."""
    result = await db.execute(
        select(Borrow)
        .options(selectinload(Borrow.book), selectinload(Borrow.user))
        .where(Borrow.id == borrow_id)
    )
    borrow = result.scalars().first()
    if not borrow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Borrow record with id={borrow_id} not found.",
        )
    return borrow


async def _sync_overdue(db: AsyncSession) -> None:
    """
    Bulk-update any 'active' borrows whose due_date has passed to 'overdue'.
    Called at the start of list/get operations to keep status accurate.
    """
    # Use naive UTC datetime for SQLite compatibility (SQLite stores naive datetimes)
    from datetime import timezone as _tz
    now_aware = datetime.now(timezone.utc)
    now = now_aware.replace(tzinfo=None)  # SQLite stores naive; compare without tzinfo
    await db.execute(
        update(Borrow)
        .where(Borrow.status == BorrowStatus.active, Borrow.due_date < now)
        .values(status=BorrowStatus.overdue)
        .execution_options(synchronize_session=False)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Service functions
# ─────────────────────────────────────────────────────────────────────────────

async def borrow_book(
    borrow_in: BorrowCreate,
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Borrow:
    """
    Check out a book for the authenticated member.

    Rules
    -----
    1. Book must exist and have available_copies > 0
    2. User must not exceed MAX_BORROW_LIMIT active borrows
    3. User must not already have an active borrow of the same book
    """
    # 1. Book availability
    result = await db.execute(select(Book).where(Book.id == borrow_in.book_id))
    book = result.scalars().first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id={borrow_in.book_id} not found.",
        )
    if book.available_copies < 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Book '{book.title}' has no available copies at this time.",
        )

    # 2. Borrow limit check
    active_count_result = await db.execute(
        select(func.count())
        .select_from(Borrow)
        .where(
            Borrow.user_id == current_user.id,
            Borrow.status.in_([BorrowStatus.active, BorrowStatus.overdue]),
        )
    )
    active_count: int = active_count_result.scalar_one()
    assert_borrow_limit_not_reached(active_count, settings.MAX_BORROW_LIMIT)

    # 3. Duplicate active borrow check
    duplicate_result = await db.execute(
        select(Borrow).where(
            Borrow.user_id == current_user.id,
            Borrow.book_id == borrow_in.book_id,
            Borrow.status.in_([BorrowStatus.active, BorrowStatus.overdue]),
        )
    )
    if duplicate_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have an active borrow for book id={borrow_in.book_id}.",
        )

    # Create borrow record
    borrow = Borrow(user_id=current_user.id, book_id=borrow_in.book_id)
    db.add(borrow)

    # Decrement available copies
    book.available_copies -= 1

    await db.flush()

    # Reload with relationships
    borrow = await _get_borrow_or_404(borrow.id, db)

    # Invalidate caches
    await _cache_invalidate(
        redis,
        CACHE_KEY_ALL,
        _user_borrows_cache_key(current_user.id),
    )

    logger.info(
        "BORROW created id=%s user=%s book_id=%s",
        borrow.id, current_user.username, borrow_in.book_id,
    )
    return borrow


async def return_book(
    borrow_id: int,
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Borrow:
    """
    Mark a borrow as returned and restore the book's available_copies.
    """
    borrow = await _get_borrow_or_404(borrow_id, db)
    assert_can_return_borrow(borrow, current_user)  # raises 403/409 if not allowed

    # Mark returned
    borrow.returned_at = datetime.now(timezone.utc)
    borrow.status = BorrowStatus.returned

    # Restore copy
    result = await db.execute(select(Book).where(Book.id == borrow.book_id))
    book = result.scalars().first()
    if book:
        book.available_copies = min(book.available_copies + 1, book.total_copies)

    await db.flush()
    await db.refresh(borrow)

    # Invalidate caches
    await _cache_invalidate(
        redis,
        CACHE_KEY_ALL,
        _borrow_cache_key(borrow_id),
        _user_borrows_cache_key(borrow.user_id),
    )

    logger.info(
        "BORROW returned id=%s user=%s book_id=%s",
        borrow.id, current_user.username, borrow.book_id,
    )
    return borrow


async def get_borrow_by_id(
    borrow_id: int,
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> Borrow:
    """Return a single borrow record (permission-checked)."""
    # Try cache first
    cached = await _cache_get(redis, _borrow_cache_key(borrow_id))
    if cached is not None:
        # Build a lightweight object for permission check
        if not current_user.is_admin and cached.get("user_id") != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this borrow record.",
            )
        return cached  # type: ignore[return-value]  # route validates via BorrowResponse

    await _sync_overdue(db)
    borrow = await _get_borrow_or_404(borrow_id, db)
    assert_can_view_borrow(borrow, current_user)

    await _cache_set(redis, _borrow_cache_key(borrow_id), _borrow_to_dict(borrow))
    return borrow


async def get_all_borrows(
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
    skip: int = 0,
    limit: int = 20,
    filter_status: Optional[BorrowStatus] = None,
) -> tuple[list[Borrow], int]:
    """
    List borrow records.

    • Admin → all borrows (optionally filtered by status)
    • Member → only their own borrows

    Default pagination (skip=0, limit=20) is cached per user / global.
    """
    is_admin = current_user.is_admin
    use_cache = skip == 0 and limit == 20 and filter_status is None

    cache_key = CACHE_KEY_ALL if is_admin else _user_borrows_cache_key(current_user.id)

    if use_cache:
        cached = await _cache_get(redis, cache_key)
        if cached is not None:
            return cached["borrows"], cached["total"]  # type: ignore[return-value]

    await _sync_overdue(db)

    stmt = (
        select(Borrow)
        .options(selectinload(Borrow.book), selectinload(Borrow.user))
    )
    count_stmt = select(func.count()).select_from(Borrow)

    if not is_admin:
        stmt = stmt.where(Borrow.user_id == current_user.id)
        count_stmt = count_stmt.where(Borrow.user_id == current_user.id)

    if filter_status:
        stmt = stmt.where(Borrow.status == filter_status)
        count_stmt = count_stmt.where(Borrow.status == filter_status)

    stmt = stmt.order_by(Borrow.borrowed_at.desc()).offset(skip).limit(limit)

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    result = await db.execute(stmt)
    borrows: list[Borrow] = list(result.scalars().all())

    if use_cache:
        payload = {"total": total, "borrows": [_borrow_to_dict(b) for b in borrows]}
        await _cache_set(redis, cache_key, payload)

    return borrows, total


async def get_user_borrows(
    target_user_id: int,
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Borrow], int]:
    """
    Admin-only: list all borrows for a specific user.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to view another user's borrows.",
        )

    await _sync_overdue(db)

    stmt = (
        select(Borrow)
        .options(selectinload(Borrow.book), selectinload(Borrow.user))
        .where(Borrow.user_id == target_user_id)
        .order_by(Borrow.borrowed_at.desc())
        .offset(skip)
        .limit(limit)
    )
    count_stmt = (
        select(func.count())
        .select_from(Borrow)
        .where(Borrow.user_id == target_user_id)
    )

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    result = await db.execute(stmt)
    borrows: list[Borrow] = list(result.scalars().all())

    return borrows, total


async def delete_borrow(
    borrow_id: int,
    current_user: User,
    db: AsyncSession,
    redis: Optional[Redis] = None,
) -> None:
    """
    Hard-delete a borrow record.  Admin only.
    If the borrow was still active, restores the book's available_copies.
    """
    assert_can_delete_borrow(current_user)  # raises 403 if not admin

    borrow = await _get_borrow_or_404(borrow_id, db)

    # If borrow was active, restore copy count
    if borrow.status in (BorrowStatus.active, BorrowStatus.overdue):
        result = await db.execute(select(Book).where(Book.id == borrow.book_id))
        book = result.scalars().first()
        if book:
            book.available_copies = min(book.available_copies + 1, book.total_copies)

    user_id = borrow.user_id
    await db.delete(borrow)
    await db.flush()

    await _cache_invalidate(
        redis,
        CACHE_KEY_ALL,
        _borrow_cache_key(borrow_id),
        _user_borrows_cache_key(user_id),
    )

    logger.info("BORROW deleted id=%s by admin=%s", borrow_id, current_user.username)
