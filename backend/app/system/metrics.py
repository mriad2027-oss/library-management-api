"""
app/system/metrics.py
─────────────────────
In-memory metrics store for the monitoring dashboard.

Collects:
  • Request counts per endpoint + method
  • Response time per request (rolling last 1000)
  • HTTP status code distribution
  • Error log (last 100)
  • Auth events (success / failure)
  • CRUD operation counts

Thread-safe via asyncio — all mutations happen inside async context.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional


@dataclass
class RequestRecord:
    method: str
    endpoint: str
    status_code: int
    response_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ErrorRecord:
    timestamp: str
    method: str
    endpoint: str
    status_code: int
    detail: str


class MetricsStore:
    """Single in-memory store for all monitoring metrics."""

    def __init__(self, max_requests: int = 1000, max_errors: int = 100):
        self._requests: Deque[RequestRecord] = deque(maxlen=max_requests)
        self._errors: Deque[ErrorRecord] = deque(maxlen=max_errors)

        # Counters
        self._total_requests: int = 0
        self._status_counts: Dict[int, int] = defaultdict(int)
        self._endpoint_counts: Dict[str, int] = defaultdict(int)
        self._method_counts: Dict[str, int] = defaultdict(int)
        self._auth_success: int = 0
        self._auth_failure: int = 0
        self._crud_counts: Dict[str, int] = defaultdict(int)

        self._start_time: float = time.time()

    # ── Record a completed HTTP request ──────────────────────────────────────

    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        response_ms: float,
    ) -> None:
        rec = RequestRecord(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response_ms=response_ms,
        )
        self._requests.append(rec)
        self._total_requests += 1
        self._status_counts[status_code] += 1
        key = f"{method} {endpoint}"
        self._endpoint_counts[key] += 1
        self._method_counts[method] += 1

        if status_code >= 400:
            self._errors.append(
                ErrorRecord(
                    timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    method=method,
                    endpoint=endpoint,
                    status_code=status_code,
                    detail=f"HTTP {status_code}",
                )
            )

    # ── Auth events ───────────────────────────────────────────────────────────

    def record_auth(self, success: bool) -> None:
        if success:
            self._auth_success += 1
        else:
            self._auth_failure += 1

    # ── CRUD events ───────────────────────────────────────────────────────────

    def record_crud(self, operation: str, resource: str, resource_id: int | None = None) -> None:
        self._crud_counts[f"{operation}:{resource}"] += 1

    # ── Computed stats ────────────────────────────────────────────────────────

    def _recent_requests(self, seconds: int = 60) -> List[RequestRecord]:
        cutoff = time.time() - seconds
        return [r for r in self._requests if r.timestamp >= cutoff]

    def summary(self) -> dict:
        recent = self._recent_requests(60)
        all_reqs = list(self._requests)

        # Response time stats (all time)
        times = [r.response_ms for r in all_reqs]
        avg_ms = round(sum(times) / len(times), 2) if times else 0
        max_ms = round(max(times), 2) if times else 0
        min_ms = round(min(times), 2) if times else 0

        # Recent (last 60s)
        recent_times = [r.response_ms for r in recent]
        recent_avg = round(sum(recent_times) / len(recent_times), 2) if recent_times else 0

        # Error rate (last 60s)
        recent_errors = sum(1 for r in recent if r.status_code >= 400)
        error_rate = round((recent_errors / len(recent) * 100), 1) if recent else 0.0

        # Uptime
        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"

        # Top endpoints
        top_endpoints = sorted(
            self._endpoint_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Status breakdown
        status_breakdown = dict(sorted(self._status_counts.items()))

        return {
            "uptime": uptime_str,
            "total_requests": self._total_requests,
            "requests_last_60s": len(recent),
            "response_time": {
                "avg_ms": avg_ms,
                "min_ms": min_ms,
                "max_ms": max_ms,
                "recent_avg_ms": recent_avg,
            },
            "error_rate_percent": error_rate,
            "status_breakdown": status_breakdown,
            "top_endpoints": [
                {"endpoint": ep, "count": cnt} for ep, cnt in top_endpoints
            ],
            "method_counts": dict(self._method_counts),
            "auth": {
                "success": self._auth_success,
                "failure": self._auth_failure,
            },
            "crud_operations": dict(self._crud_counts),
            "recent_errors": [
                {
                    "timestamp": e.timestamp,
                    "method": e.method,
                    "endpoint": e.endpoint,
                    "status_code": e.status_code,
                    "detail": e.detail,
                }
                for e in list(self._errors)[-20:]  # last 20
            ],
        }


# ── Global singleton ──────────────────────────────────────────────────────────
metrics = MetricsStore()
