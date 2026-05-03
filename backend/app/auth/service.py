from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.auth import schemas, security


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def create_new_user(db: AsyncSession, user_in: schemas.UserCreate) -> User:
    hashed_pass = security.hash_password(user_in.password)
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_pass,
        role=user_in.role,
    )
    db.add(db_user)
    await db.flush()
    await db.refresh(db_user)
    return db_user


async def authenticate_user(db: AsyncSession, user_login: schemas.UserLogin) -> User | None:
    user = await get_user_by_username(db, user_login.username)
    if not user:
        return None
    if not security.verify_password(user_login.password, user.hashed_password):
        return None
    return user
