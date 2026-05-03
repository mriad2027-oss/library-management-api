"""
app/books/schemas.py
────────────────────
Pydantic v2 schemas (request bodies + response models) for the Books module.

Schema hierarchy
----------------
BookBase          – shared fields with validators
  BookCreate      – used in POST  /books
  BookUpdate      – used in PUT   /books/{id}  (all fields optional)
BookInDB          – ORM representation (includes DB-only fields)
BookResponse      – the shape returned to the client
BookListResponse  – wrapper for the paginated list endpoint
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Shared base
# ─────────────────────────────────────────────────────────────────────────────

class BookBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, examples=["Clean Code"])
    author: str = Field(..., min_length=1, max_length=255, examples=["Robert C. Martin"])
    isbn: Optional[str] = Field(
        None,
        max_length=20,
        examples=["978-0132350884"],
        description="ISBN-10 or ISBN-13 (optional but must be unique if provided)",
    )
    description: Optional[str] = Field(None, max_length=5000)
    published_year: Optional[int] = Field(None, ge=1000, le=2100)
    total_copies: int = Field(1, ge=1, description="Total physical copies owned by the library")

    @field_validator("title", "author", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator("isbn", mode="before")
    @classmethod
    def normalise_isbn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Remove spaces and hyphens, then validate length
        cleaned = v.replace("-", "").replace(" ", "")
        if cleaned and len(cleaned) not in (10, 13):
            raise ValueError("ISBN must be 10 or 13 digits (hyphens/spaces ignored)")
        return cleaned or None


# ─────────────────────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────────────────────

class BookCreate(BookBase):
    """Body for POST /books  –  Admin only."""
    pass


class BookUpdate(BaseModel):
    """
    Body for PUT /books/{id}  –  Admin only.
    Every field is optional so the client can send a partial update.
    """
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    author: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=5000)
    published_year: Optional[int] = Field(None, ge=1000, le=2100)
    total_copies: Optional[int] = Field(None, ge=1)
    available_copies: Optional[int] = Field(None, ge=0)

    @field_validator("title", "author", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class BookResponse(BookBase):
    """
    Full book representation returned by every read/write endpoint.
    Includes DB-managed fields not present in the request schemas.
    """
    id: int
    available_copies: int
    is_available: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookListResponse(BaseModel):
    """Paginated list wrapper."""
    total: int
    skip: int
    limit: int
    books: list[BookResponse]
