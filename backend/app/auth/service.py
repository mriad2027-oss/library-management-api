from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.auth import schemas, security

async def get_user_by_username(db: AsyncSession, username: str):
    query = select(User).filter(User.username == username)
    result = await db.execute(query)
    return result.scalars().first()

async def create_new_user(db: AsyncSession, user_in: schemas.UserCreate):
    hashed_pass = security.hash_password(user_in.password)
    db_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_pass
    )
    db.add(db_user)
    await db.flush()
    await db.refresh(db_user)
    return db_user

async def authenticate_user(db: AsyncSession, user_login: schemas.UserLogin):
    user = await get_user_by_username(db, user_login.username)
    if not user:
        return None
    if not security.verify_password(user_login.password, user.hashed_password):
        return None
    return user