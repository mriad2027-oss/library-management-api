from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# ---------------------------------------------------------------------------
# SQLAlchemy async engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENVIRONMENT == "development"),   # log SQL only in dev
    future=True,
)

# Session factory – used everywhere via get_db()
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Declarative base – all models inherit from this
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """
    Shared base class for every SQLAlchemy model in the project.
    Import `Base` in each model file and inherit from it.
    """
    pass


# ---------------------------------------------------------------------------
# Dependency – inject an async DB session into route handlers
# ---------------------------------------------------------------------------

async def get_db() -> AsyncSession:          # type: ignore[return]
    """
    FastAPI dependency that yields an async database session.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()