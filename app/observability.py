"""Lightweight observability: structured logging + Prometheus metrics.

Logging:
- stdlib logging configured to emit JSON-ish single-line records for grep-friendly
  aggregation. No external dependency.

Metrics:
- prometheus_client. Optional — if not installed, the /metrics endpoint serves a
  short note and the rest of the app continues to work.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

try:
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

    def generate_latest(*_args, **_kwargs) -> bytes:  # type: ignore[no-redef]
        return b"# prometheus_client not installed\n"

    REGISTRY = None  # type: ignore[assignment]


# ─── Logging ───────────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Allow extra={...} args on log calls
        for k, v in record.__dict__.items():
            if k in {"args", "msg", "levelname", "name", "created", "msecs", "relativeCreated",
                     "exc_info", "exc_text", "stack_info", "pathname", "filename", "module",
                     "lineno", "funcName", "thread", "threadName", "processName", "process",
                     "taskName", "asctime", "message"}:
                continue
            if k.startswith("_"):
                continue
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: replaces handlers so multiple imports don't pile up output."""
    root = logging.getLogger()
    root.setLevel(level)
    # Remove any existing handlers (e.g. uvicorn's default)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    # Tame chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str = "financial_analyzer") -> logging.Logger:
    return logging.getLogger(name)


# ─── Metrics ───────────────────────────────────────────────────────
if _PROM_AVAILABLE:
    REQUESTS_TOTAL = Counter(
        "fa_http_requests_total",
        "HTTP requests by method, route and status class.",
        ["method", "route", "status"],
    )
    REQUEST_DURATION = Histogram(
        "fa_http_request_duration_seconds",
        "HTTP request duration in seconds.",
        ["method", "route"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    PARSE_TOTAL = Counter(
        "fa_pdf_parse_total",
        "PDF parse attempts by outcome.",
        ["outcome"],  # ok / error
    )
    PARSE_DURATION = Histogram(
        "fa_pdf_parse_duration_seconds",
        "PDF parse duration in seconds.",
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    )
    EXTRACTION_CONFIDENCE = Histogram(
        "fa_pdf_extraction_confidence",
        "Confidence score (0-1) of each successful PDF parse.",
        buckets=(0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0),
    )
else:  # pragma: no cover
    REQUESTS_TOTAL = REQUEST_DURATION = PARSE_TOTAL = PARSE_DURATION = EXTRACTION_CONFIDENCE = None


def record_parse(outcome: str, duration_seconds: float, confidence: float | None = None) -> None:
    if not _PROM_AVAILABLE:
        return
    PARSE_TOTAL.labels(outcome=outcome).inc()  # type: ignore[union-attr]
    PARSE_DURATION.observe(duration_seconds)  # type: ignore[union-attr]
    if confidence is not None and outcome == "ok":
        EXTRACTION_CONFIDENCE.observe(confidence)  # type: ignore[union-attr]


def metrics_response() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    if not _PROM_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain; charset=utf-8"
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def is_prometheus_available() -> bool:
    return _PROM_AVAILABLE
