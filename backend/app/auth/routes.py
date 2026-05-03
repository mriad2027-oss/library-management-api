"""
app/auth/routes.py
──────────────────
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.core.database import get_db
from app.auth import schemas, security, service
from app.auth.dependencies import get_current_user
from app.models.user import User, UserRole
from app.system.logger import get_logger, log_auth_attempt

logger = get_logger(__name__)
router = APIRouter()


# ── Response schema ───────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ── Register ──────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    request: Request,
    user_in: schemas.UserCreate,
    db: AsyncSession = Depends(get_db),
):
    from app.system.metrics import metrics

    existing = await service.get_user_by_username(db, user_in.username)
    if existing:
        metrics.record_auth(success=False)
        log_auth_attempt(user_in.username, success=False, ip=_get_ip(request))
        raise HTTPException(status_code=400, detail="Username already registered.")

    existing_email = await service.get_user_by_email(db, user_in.email)
    if existing_email:
        metrics.record_auth(success=False)
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = await service.create_new_user(db, user_in)
    access_token = security.create_access_token(data={"sub": user.username})

    metrics.record_auth(success=True)
    metrics.record_crud("CREATE", "user")
    log_auth_attempt(user_in.username, success=True, ip=_get_ip(request))
    logger.info("New user registered: %s (role=%s)", user.username, user.role)

    return RegisterResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=schemas.Token,
    summary="Login and get a JWT token",
)
async def login(
    request: Request,
    user_in: schemas.UserLogin,
    db: AsyncSession = Depends(get_db),
):
    from app.system.metrics import metrics

    user = await service.authenticate_user(db, user_in)
    if not user:
        metrics.record_auth(success=False)
        log_auth_attempt(user_in.username, success=False, ip=_get_ip(request))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        metrics.record_auth(success=False)
        raise HTTPException(status_code=403, detail="User account is disabled.")

    access_token = security.create_access_token(data={"sub": user.username})
    metrics.record_auth(success=True)
    log_auth_attempt(user_in.username, success=True, ip=_get_ip(request))
    logger.info("User logged in: %s", user.username)

    return {"access_token": access_token, "token_type": "bearer"}


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    logger.debug("GET /me  user=%s", current_user.username)
    return UserResponse.model_validate(current_user)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
