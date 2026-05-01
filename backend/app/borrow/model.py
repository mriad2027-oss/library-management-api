"""
app/borrow/model.py
───────────────────
SQLAlchemy ORM model for the Borrow entity.

Columns
-------
id              Primary key
user_id         FK → users.id  (who borrowed the book)
book_id         FK → books.id  (which book was borrowed)
borrowed_at     Timestamp when the book was checked out (UTC)
due_date        Expected return date (borrowed_at + 14 days by default)
returned_at     Timestamp when the book was returned; NULL = still borrowed
status          Enum: 'active' | 'returned' | 'overdue'

Relationships
-------------
user  →  User (M1/M2 model – back_populates="borrows")
book  →  Book (M3 model  – back_populates="borrows")

Compatibility
-------------
• Uses the shared Base from app.core.database  (M1)
• References User from app.models.user         (M1)
• References Book from app.books.model         (M3)
Both User and Book already declare:
    borrows: Mapped[list] = relationship("Borrow", back_populates=...)
so no changes to those files are needed.
"""

import enum
from datetime import datetime, timezone, timedelta

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class BorrowStatus(str, enum.Enum):
    active   = "active"
    returned = "returned"
    overdue  = "overdue"


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Borrow(Base):
    __tablename__ = "borrows"

    # ── primary key ─────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ── foreign keys ────────────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("books.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── borrow lifecycle ────────────────────────────────────────────────────
    borrowed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    due_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=14),
        nullable=False,
    )
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # ── status ──────────────────────────────────────────────────────────────
    status: Mapped[BorrowStatus] = mapped_column(
        Enum(BorrowStatus, name="borrowstatus"),
        default=BorrowStatus.active,
        nullable=False,
        index=True,
    )

    # ── relationships ────────────────────────────────────────────────────────
    # Both sides already exist in User and Book – we just complete the pair.
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="borrows", lazy="select"
    )
    book: Mapped["Book"] = relationship(  # noqa: F821
        "Book", back_populates="borrows", lazy="select"
    )

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def is_overdue(self) -> bool:
        """True if the book has not been returned yet and is past its due date."""
        if self.status == BorrowStatus.returned:
            return False
        return datetime.now(timezone.utc) > self.due_date

    def __repr__(self) -> str:
        return (
            f"<Borrow id={self.id} user_id={self.user_id} "
            f"book_id={self.book_id} status={self.status}>"
        )
