import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Log directory ─────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"

# ── Formatter ─────────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler — INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Rotating file handler — DEBUG and above (all logs)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Separate rotating file for ERROR+ only
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.addHandler(error_handler)

    # Silence noisy third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.  Call once per module:
        logger = get_logger(__name__)
    """
    _configure_root_logger()
    return logging.getLogger(name)


# ── Request logging helper (used by middleware in main.py) ────────────────────

def log_request(
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: float,
    user_id: int | None = None,
) -> None:
    """Log an API request in a structured one-liner."""
    logger = get_logger("api.request")
    level = logging.WARNING if status_code >= 400 else logging.INFO
    user_part = f" | user_id={user_id}" if user_id else ""
    logger.log(
        level,
        f"{method:6} {endpoint} → {status_code} ({response_time_ms:.1f}ms){user_part}",
    )


def log_auth_attempt(username: str, success: bool, ip: str = "unknown") -> None:
    """Log login / register attempts."""
    logger = get_logger("api.auth")
    if success:
        logger.info(f"AUTH SUCCESS — user='{username}' ip={ip}")
    else:
        logger.warning(f"AUTH FAILURE — user='{username}' ip={ip}")


def log_crud(
    operation: str,
    resource: str,
    resource_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """Log CRUD operations."""
    logger = get_logger("api.crud")
    id_part = f" id={resource_id}" if resource_id else ""
    user_part = f" by user_id={user_id}" if user_id else ""
    logger.info(f"{operation.upper():6} {resource}{id_part}{user_part}")


# ── Context manager for timing blocks ────────────────────────────────────────

class Timer:
    """
    Simple context manager that logs elapsed time.

    Usage:
        with Timer("heavy_query", logger):
            result = db.query(...)
    """

    def __init__(self, label: str, logger: logging.Logger | None = None):
        self.label = label
        self.logger = logger or get_logger("timer")
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self.elapsed_ms = elapsed_ms
        self.logger.debug(f"TIMER [{self.label}] took {elapsed_ms:.2f}ms")
