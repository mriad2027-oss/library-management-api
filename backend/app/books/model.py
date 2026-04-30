"""
app/books/model.py
──────────────────
SQLAlchemy ORM model for the Book entity.

Columns
-------
id              Primary key
title           Book title (required)
author          Author name (required)
isbn            International Standard Book Number – unique identifier
description     Optional long-form description
published_year  Year the book was published
total_copies    How many physical copies the library owns
available_copies How many are on the shelf right now (not borrowed)
created_at      Row creation timestamp (UTC)
updated_at      Last-updated timestamp (UTC)

Relationships
-------------
borrows  →  Borrow (M4 will add this back-reference)
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Book(Base):
    __tablename__ = "books"

    # ── primary key ──────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # ── required fields ──────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # ── optional / metadata ──────────────────────────────────────────────────
    isbn: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── inventory ────────────────────────────────────────────────────────────
    total_copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    available_copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ── timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────────
    # M4 (borrow) will declare the other side; `back_populates="book"` there.
    borrows: Mapped[list] = relationship("Borrow", back_populates="book", lazy="select")

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self.available_copies > 0

    def __repr__(self) -> str:
        return (
            f"<Book id={self.id} title={self.title!r} "
            f"available={self.available_copies}/{self.total_copies}>"
        )
