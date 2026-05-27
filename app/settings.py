from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STORAGE_DIR = Path(os.getenv("FINANCIAL_ANALYZER_STORAGE", str(BASE_DIR / "storage"))).expanduser().resolve()
UPLOAD_DIR = STORAGE_DIR / "uploads"
REPORT_DIR = STORAGE_DIR / "reports"
ANALYSIS_DIR = STORAGE_DIR / "analyses"
RETENTION_DAYS = int(os.getenv("FINANCIAL_ANALYZER_RETENTION_DAYS", "7"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("FINANCIAL_ANALYZER_CLEANUP_INTERVAL_SECONDS", "3600"))
SESSION_MAX_AGE_SECONDS = int(os.getenv("FINANCIAL_ANALYZER_SESSION_MAX_AGE_SECONDS", str(12 * 60 * 60)))
COOKIE_SECURE = os.getenv("FINANCIAL_ANALYZER_COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}


def ensure_storage() -> None:
    for path in (STORAGE_DIR, UPLOAD_DIR, REPORT_DIR, ANALYSIS_DIR):
        path.mkdir(parents=True, exist_ok=True)
