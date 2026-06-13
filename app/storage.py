from __future__ import annotations

import json
from pathlib import Path

from .cleanup import is_demo_id
from .models import AnalysisRecord
from .settings import ANALYSIS_DIR, REPORT_DIR, UPLOAD_DIR, ensure_storage


def save_record(record: AnalysisRecord) -> None:
    ensure_storage()
    path = ANALYSIS_DIR / f"{record.id}.json"
    path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_record(analysis_id: str) -> AnalysisRecord:
    path = ANALYSIS_DIR / f"{analysis_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"analysis not found: {analysis_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalysisRecord.from_dict(data)


def list_records(
    limit: int = 12, include_demo: bool = False, owner: str | None = None, is_admin: bool = False
) -> list[dict[str, str]]:
    ensure_storage()
    rows: list[dict[str, str]] = []
    for path in sorted(Path(ANALYSIS_DIR).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not include_demo and is_demo_id(path.stem):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not is_admin and data.get("owner", "") != (owner or ""):
            continue
        rows.append(
            {
                "id": data["id"],
                "created_at": data.get("created_at", ""),
                "title": str(data.get("title", "") or ""),
                "count": str(len(data.get("documents", []))),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def delete_record(analysis_id: str) -> bool:
    """Delete an analysis record and its associated uploaded PDFs and reports.

    Returns True if the record JSON existed and was removed. Associated files
    (uploaded PDFs referenced by the record, and any generated reports whose
    filename embeds the analysis id) are removed best-effort, each guarded so a
    single failure never aborts the whole deletion. Path containment is checked
    so a tampered stored_path can't unlink outside the storage roots.
    """
    path = ANALYSIS_DIR / f"{analysis_id}.json"
    if not path.exists():
        return False

    # Remove uploaded PDFs referenced by this record.
    try:
        record = AnalysisRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        upload_root = UPLOAD_DIR.resolve()
        for doc in record.documents:
            try:
                resolved = Path(doc.stored_path).resolve()
                if resolved.exists() and resolved.is_file() and resolved.is_relative_to(upload_root):
                    resolved.unlink()
            except OSError:
                pass
    except (json.JSONDecodeError, OSError):
        pass

    # Remove generated reports embedding this analysis id (financial-report-{id}-*.html).
    try:
        report_root = REPORT_DIR.resolve()
        for report_path in REPORT_DIR.glob(f"*{analysis_id}*"):
            try:
                resolved = report_path.resolve()
                if resolved.is_file() and resolved.is_relative_to(report_root):
                    resolved.unlink()
            except OSError:
                pass
    except OSError:
        pass

    path.unlink()
    return True


def can_access(record: AnalysisRecord, user) -> bool:
    """Accessible if it's a demo record, the user is admin, or the user owns it."""
    if is_demo_id(record.id):
        return True
    if getattr(user, "is_admin", False):
        return True
    return record.owner == getattr(user, "username", None)


def count_owned(owner: str) -> int:
    ensure_storage()
    n = 0
    for path in Path(ANALYSIS_DIR).glob("*.json"):
        if is_demo_id(path.stem):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("owner", "") == owner:
            n += 1
    return n


def owned_storage_bytes(owner: str) -> int:
    """Total bytes of uploaded PDFs across the owner's (non-demo) analyses."""
    ensure_storage()
    ids: list[str] = []
    for path in Path(ANALYSIS_DIR).glob("*.json"):
        if is_demo_id(path.stem):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("owner", "") == owner:
            ids.append(data["id"])
    total = 0
    for up in Path(UPLOAD_DIR).glob("*"):
        if any(up.name.startswith(f"{aid}-") for aid in ids):
            try:
                total += up.stat().st_size
            except OSError:
                pass
    return total

