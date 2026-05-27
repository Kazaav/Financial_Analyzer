from __future__ import annotations

import time
from pathlib import Path

from .settings import (
    ANALYSIS_DIR,
    CLEANUP_INTERVAL_SECONDS,
    REPORT_DIR,
    RETENTION_DAYS,
    STORAGE_DIR,
    UPLOAD_DIR,
)

_last_cleanup = 0.0


def _safe_unlink(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        if resolved.exists() and resolved.is_file() and resolved.is_relative_to(root.resolve()):
            resolved.unlink()
            return True
    except OSError:
        return False
    return False


DEMO_PREFIX = "demo-"


def is_demo_id(record_id: str) -> bool:
    return record_id.startswith(DEMO_PREFIX)


def cleanup_expired_storage() -> int:
    if RETENTION_DAYS <= 0:
        return 0

    cutoff = time.time() - RETENTION_DAYS * 24 * 60 * 60
    removed = 0
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    expired_analysis_ids: set[str] = set()
    for record_path in ANALYSIS_DIR.glob("*.json"):
        if is_demo_id(record_path.stem):
            continue
        try:
            if record_path.stat().st_mtime < cutoff:
                expired_analysis_ids.add(record_path.stem)
                if _safe_unlink(record_path, ANALYSIS_DIR):
                    removed += 1
        except OSError:
            continue

    for upload_path in UPLOAD_DIR.glob("*"):
        if is_demo_id(upload_path.name):
            continue
        try:
            should_remove = upload_path.stat().st_mtime < cutoff or any(upload_path.name.startswith(f"{analysis_id}-") for analysis_id in expired_analysis_ids)
        except OSError:
            continue
        if should_remove and _safe_unlink(upload_path, UPLOAD_DIR):
            removed += 1

    for report_path in REPORT_DIR.glob("*"):
        if is_demo_id(report_path.name):
            continue
        try:
            should_remove = report_path.stat().st_mtime < cutoff or any(analysis_id in report_path.name for analysis_id in expired_analysis_ids)
        except OSError:
            continue
        if should_remove and _safe_unlink(report_path, REPORT_DIR):
            removed += 1

    return removed


def maybe_cleanup_expired_storage(force: bool = False) -> int:
    global _last_cleanup
    now = time.time()
    if not force and now - _last_cleanup < CLEANUP_INTERVAL_SECONDS:
        return 0
    _last_cleanup = now
    return cleanup_expired_storage()
