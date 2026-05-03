from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import time

from app.core.config import settings
from app.core.database import engine, Base
from app.system.logger import get_logger, log_request

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀  Starting %s  (env=%s)", settings.PROJECT_NAME, settings.ENVIRONMENT)
    logger.info("    Database : %s", settings.DATABASE_URL)

    import app.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅  Database tables verified / created.")

    yield

    await engine.dispose()
    logger.info("🛑  %s shut down cleanly.", settings.PROJECT_NAME)


# ── App factory ───────────────────────────────────────────────────────────────

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

    # ── CORS ──────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + metrics middleware ──────────────────────────────────
    @application.middleware("http")
    async def request_middleware(request: Request, call_next):
        from app.system.metrics import metrics  # import here to avoid circular

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            logger.error("Unhandled exception: %s", exc, exc_info=True)
            response = JSONResponse(
                status_code=500, content={"detail": "Internal server error"}
            )
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Skip logging for dashboard/health/docs noise
            path = request.url.path
            skip = path in ("/health", "/docs", "/openapi.json", "/redoc")

            if not skip:
                log_request(
                    method=request.method,
                    endpoint=path,
                    status_code=status_code,
                    response_ms=elapsed_ms,
                )
                metrics.record_request(
                    method=request.method,
                    endpoint=path,
                    status_code=status_code,
                    response_ms=elapsed_ms,
                )

            response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.auth.routes import router as auth_router
    from app.books.routes import router as books_router
    from app.borrow.routes import router as borrow_router
    from app.dashboard.routes import router as dashboard_router

    application.include_router(auth_router,      prefix="/api/v1/auth",      tags=["Authentication"])
    application.include_router(books_router,     prefix="/api/v1/books",     tags=["Books"])
    application.include_router(borrow_router,    prefix="/api/v1/borrow",    tags=["Borrow"])
    application.include_router(dashboard_router, prefix="/dashboard",        tags=["Dashboard"])

    # ── Health check ──────────────────────────────────────────────────────────
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
