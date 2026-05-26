from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .analysis import build_analysis
from .formatting import fmt_metric, fmt_money, fmt_number, fmt_percent, fmt_ratio, score_label
from .models import AnalysisRecord
from .settings import REPORT_DIR, STATIC_DIR, TEMPLATES_DIR, ensure_storage


def make_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["number"] = fmt_number
    env.filters["money"] = fmt_money
    env.filters["percent"] = fmt_percent
    env.filters["ratio"] = fmt_ratio
    env.filters["metric"] = fmt_metric
    env.filters["score_label"] = score_label
    return env


def generate_report(
    record: AnalysisRecord,
    mode: str,
    selected_year: int | None = None,
    selected_company: str | None = None,
    selected_doc_ids: list[str] | None = None,
    chart_type: str | None = None,
) -> Path:
    ensure_storage()
    analysis = build_analysis(record, mode, selected_year, selected_company, selected_doc_ids, chart_type)
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    env = make_environment()
    html = env.get_template("report.html").render(
        analysis=analysis,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        embedded_css=css,
    )
    filename = f"financial-report-{record.id}-{uuid4().hex[:8]}.html"
    path = REPORT_DIR / filename
    path.write_text(html, encoding="utf-8")
    return path

