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

# Upload / parse guard rails (override via env). Defend against OOM/DoS.
MAX_UPLOAD_MB = int(os.getenv("FINANCIAL_ANALYZER_MAX_UPLOAD_MB", "30"))
MAX_FILES_PER_UPLOAD = int(os.getenv("FINANCIAL_ANALYZER_MAX_FILES", "20"))
MAX_PDF_PAGES = int(os.getenv("FINANCIAL_ANALYZER_MAX_PDF_PAGES", "400"))

# Account / multi-user (override via env).
MIN_PASSWORD_LEN = int(os.getenv("FINANCIAL_ANALYZER_MIN_PASSWORD_LEN", "8"))
MAX_ANALYSES_PER_USER = int(os.getenv("FINANCIAL_ANALYZER_MAX_ANALYSES_PER_USER", "50"))  # 0 = unlimited
MAX_STORAGE_MB_PER_USER = int(os.getenv("FINANCIAL_ANALYZER_MAX_STORAGE_MB_PER_USER", "500"))  # 0 = unlimited
LOGIN_MAX_ATTEMPTS = int(os.getenv("FINANCIAL_ANALYZER_LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_WINDOW_SECONDS = int(os.getenv("FINANCIAL_ANALYZER_LOGIN_WINDOW_SECONDS", "300"))
REGISTER_MAX_ATTEMPTS = int(os.getenv("FINANCIAL_ANALYZER_REGISTER_MAX_ATTEMPTS", "5"))
REGISTER_WINDOW_SECONDS = int(os.getenv("FINANCIAL_ANALYZER_REGISTER_WINDOW_SECONDS", "3600"))


def ensure_storage() -> None:
    for path in (STORAGE_DIR, UPLOAD_DIR, REPORT_DIR, ANALYSIS_DIR):
        path.mkdir(parents=True, exist_ok=True)
