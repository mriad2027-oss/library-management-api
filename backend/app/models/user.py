"""
app/models/user.py
──────────────────
SQLAlchemy ORM model for the User entity.

Referenced by:  app/auth/service.py  →  from app.models.user import User
Also imported in main.py lifespan so Base.metadata.create_all() creates the table.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"),
        default=UserRole.member,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to borrows (used by M4)
    borrows: Mapped[list] = relationship("Borrow", back_populates="user", lazy="select")

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
