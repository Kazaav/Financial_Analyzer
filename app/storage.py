from __future__ import annotations

import json
from pathlib import Path

from .models import AnalysisRecord
from .settings import ANALYSIS_DIR, ensure_storage


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


def list_records(limit: int = 12) -> list[dict[str, str]]:
    ensure_storage()
    rows: list[dict[str, str]] = []
    for path in sorted(Path(ANALYSIS_DIR).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "id": data["id"],
                "created_at": data.get("created_at", ""),
                "count": str(len(data.get("documents", []))),
            }
        )
        if len(rows) >= limit:
            break
    return rows

