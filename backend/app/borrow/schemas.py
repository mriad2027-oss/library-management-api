"""
app/borrow/schemas.py
─────────────────────
Pydantic v2 schemas (request bodies + response models) for the Borrow module.

Schema hierarchy
----------------
BorrowCreate       – body for POST /borrow          (member initiates borrow)
BorrowReturn       – body for PUT  /borrow/{id}/return (optional notes)
BorrowResponse     – full borrow record returned to the client
BorrowListResponse – paginated list wrapper

Compatibility
-------------
• Mirrors the style used in app/books/schemas.py   (M3)
• Uses from_attributes = True so FastAPI can serialise ORM objects directly
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.borrow.model import BorrowStatus


# ─────────────────────────────────────────────────────────────────────────────
# Nested sub-schemas (embedded in BorrowResponse for convenience)
# ─────────────────────────────────────────────────────────────────────────────

class BorrowBookInfo(BaseModel):
    """Minimal book info embedded inside a BorrowResponse."""
    id: int
    title: str
    author: str
    isbn: Optional[str] = None

    model_config = {"from_attributes": True}


class BorrowUserInfo(BaseModel):
    """Minimal user info embedded inside a BorrowResponse (Admin view)."""
    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────────────────────

class BorrowCreate(BaseModel):
    """
    Body for POST /borrow
    Members supply only the book_id they want to borrow.
    The user_id is taken from the authenticated JWT (current_user).
    """
    book_id: int = Field(..., gt=0, description="ID of the book to borrow")


class BorrowReturn(BaseModel):
    """
    Optional body for PUT /borrow/{id}/return
    Currently a placeholder; extend with notes/condition fields if needed.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class BorrowResponse(BaseModel):
    """
    Full borrow record returned by every endpoint.
    Includes nested book info and (for admins) user info.
    """
    id: int
    user_id: int
    book_id: int
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime] = None
    status: BorrowStatus
    is_overdue: bool

    # Nested objects – populated when the ORM relationship is loaded
    book: Optional[BorrowBookInfo] = None
    user: Optional[BorrowUserInfo] = None

    model_config = {"from_attributes": True}


class BorrowListResponse(BaseModel):
    """Paginated list wrapper – mirrors BookListResponse pattern (M3)."""
    total: int
    skip: int
    limit: int
    borrows: list[BorrowResponse]


def borrow_to_response(borrow) -> BorrowResponse:
    """
    Safely convert a Borrow ORM object to BorrowResponse.
    Accesses only scalar columns to avoid lazy-load MissingGreenlet errors.
    Nested book/user are included only if already loaded in memory.
    """
    from sqlalchemy.orm.base import instance_state
    from sqlalchemy.orm import RelationshipProperty

    book_info = None
    user_info = None

    try:
        state = instance_state(borrow)
        # Only access relationship if it is already in the dict_  (loaded)
        if "book" in state.dict and borrow.book is not None:
            book_info = BorrowBookInfo.model_validate(borrow.book)
    except Exception:
        pass

    try:
        state = instance_state(borrow)
        if "user" in state.dict and borrow.user is not None:
            user_info = BorrowUserInfo.model_validate(borrow.user)
    except Exception:
        pass

    return BorrowResponse(
        id=borrow.id,
        user_id=borrow.user_id,
        book_id=borrow.book_id,
        borrowed_at=borrow.borrowed_at,
        due_date=borrow.due_date,
        returned_at=borrow.returned_at,
        status=borrow.status,
        is_overdue=borrow.is_overdue,
        book=book_info,
        user=user_info,
    )
