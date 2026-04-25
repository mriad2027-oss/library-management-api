from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

from app.core.config import settings
from app.core.database import engine, Base


# ---------------------------------------------------------------------------
# Lifespan – runs once on startup and once on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    # Full structured logging is handled by M5 (system/logger.py)
    print(f"🚀  Starting {settings.PROJECT_NAME} ...")
    print(f"    Environment : {settings.ENVIRONMENT}")
    print(f"    Database URL: {settings.DATABASE_URL}")

    # Create all tables that don't exist yet (models imported elsewhere)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅  Database tables verified / created.")

    yield  # ── Application running ──────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await engine.dispose()
    print("🛑  Library Management API shut down cleanly.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "A RESTful backend for managing a library system. "
            "Includes book CRUD, borrow / return tracking, JWT auth, "
            "role-based access control, Redis caching, and structured logging."
        ),
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Basic request timing middleware ──────────────────────────────────────
    # NOTE: Full structured logging middleware is handled by M5 (system/logger.py)
    @application.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
        return response

    # ── Routers (imported lazily to avoid circular imports at startup) ────────
    from app.auth.routes import router as auth_router
    from app.books.routes import router as books_router
    from app.borrow.routes import router as borrow_router

    application.include_router(auth_router,   prefix="/api/v1/auth",   tags=["Authentication"])
    application.include_router(books_router,  prefix="/api/v1/books",  tags=["Books"])
    application.include_router(borrow_router, prefix="/api/v1/borrow", tags=["Borrow"])

    # ── Health-check ─────────────────────────────────────────────────────────
    @application.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "project": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    return application


app = create_application()