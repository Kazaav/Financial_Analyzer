from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MetricMap = dict[str, float | None]


@dataclass
class FinancialDocument:
    id: str
    filename: str
    stored_path: str
    company_name: str
    fiscal_year: int | None
    fiscal_period: str
    unit: str
    page_count: int
    char_count: int
    text_excerpt: str
    security_code: str = ""
    edinet_code: str = ""
    metrics: MetricMap = field(default_factory=dict)
    metric_sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    extraction_notes: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinancialDocument":
        return cls(
            id=data["id"],
            filename=data["filename"],
            stored_path=data["stored_path"],
            company_name=data.get("company_name", "未判定"),
            fiscal_year=data.get("fiscal_year"),
            fiscal_period=data.get("fiscal_period", ""),
            unit=data.get("unit", "百万円"),
            page_count=int(data.get("page_count", 0)),
            char_count=int(data.get("char_count", 0)),
            text_excerpt=data.get("text_excerpt", ""),
            security_code=str(data.get("security_code", "") or ""),
            edinet_code=str(data.get("edinet_code", "") or ""),
            metrics=data.get("metrics", {}),
            metric_sources=data.get("metric_sources", {}),
            extraction_notes=data.get("extraction_notes", []),
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass
class AnalysisRecord:
    id: str
    created_at: str
    documents: list[FinancialDocument]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "documents": [doc.to_dict() for doc in self.documents],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisRecord":
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            documents=[FinancialDocument.from_dict(item) for item in data.get("documents", [])],
        )

