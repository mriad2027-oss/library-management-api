import re
import time
import math
from typing import Any
from datetime import datetime, timezone

from app.system.logger import get_logger

logger = get_logger(__name__)


# ── Pagination ────────────────────────────────────────────────────────────────

def paginate(items: list[Any], page: int, page_size: int) -> dict:
    """
    Slice a list and return pagination metadata.

    Returns:
        {
            "items": [...],
            "total": int,
            "page": int,
            "page_size": int,
            "total_pages": int,
            "has_next": bool,
            "has_prev": bool,
        }
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))  # cap at 100

    total = len(items)
    total_pages = math.ceil(total / page_size) if total else 1
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


# ── Validation helpers ────────────────────────────────────────────────────────

ISBN_RE = re.compile(r"^(?:\d{9}[\dXx]|\d{13})$")


def is_valid_isbn(isbn: str) -> bool:
    """Return True if the string looks like a valid ISBN-10 or ISBN-13."""
    cleaned = isbn.replace("-", "").replace(" ", "")
    return bool(ISBN_RE.match(cleaned))


def sanitize_string(value: str, max_length: int = 500) -> str:
    """Strip whitespace and truncate to max_length."""
    return value.strip()[:max_length]


# ── Date / time helpers ───────────────────────────────────────────────────────

def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def is_overdue(due_date: datetime) -> bool:
    """Return True if due_date is in the past."""
    now = utcnow()
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    return now > due_date


def days_until_due(due_date: datetime) -> int:
    """Return number of days remaining (negative if overdue)."""
    now = utcnow()
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    delta = due_date - now
    return delta.days


# ── Response formatters ───────────────────────────────────────────────────────

def success_response(data: Any = None, message: str = "Success") -> dict:
    return {"success": True, "message": message, "data": data}


def error_response(message: str, details: Any = None) -> dict:
    return {"success": False, "message": message, "details": details}


# ── Performance timer ─────────────────────────────────────────────────────────

class PerformanceTracker:
    """
    Measures and logs cache vs DB response times to demonstrate
    the caching speed improvement required by the project spec.
    """

    def __init__(self):
        self._records: list[dict] = []

    def record(self, source: str, endpoint: str, elapsed_ms: float) -> None:
        self._records.append(
            {
                "source": source,       # "cache" | "db"
                "endpoint": endpoint,
                "elapsed_ms": elapsed_ms,
                "ts": time.time(),
            }
        )
        logger.debug(
            f"PERF [{source.upper():5}] {endpoint} — {elapsed_ms:.2f}ms"
        )

    def summary(self) -> dict:
        """Return average times grouped by source."""
        groups: dict[str, list[float]] = {}
        for r in self._records:
            groups.setdefault(r["source"], []).append(r["elapsed_ms"])
        return {
            src: {
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "count": len(times),
            }
            for src, times in groups.items()
        }


# Singleton instance used across the app
perf_tracker = PerformanceTracker()
