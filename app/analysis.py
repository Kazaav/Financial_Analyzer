from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from math import isfinite
from typing import Any

from .formatting import fmt_money_compact, fmt_number, fmt_percent, fmt_ratio
from .models import AnalysisRecord, FinancialDocument
from .pdf_parser import DISPLAY_NAMES

MODE_LABELS = {
    "same_year": "多社同年度比較",
    "same_company": "同一企業の時系列分析",
    "custom": "カスタム比較",
}


METRIC_ORDER = [
    "revenue",
    "gross_profit",
    "operating_income",
    "ordinary_income",
    "net_income",
    "total_assets",
    "net_assets",
    "current_assets",
    "current_liabilities",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "employees",
]


DERIVED_LABELS = {
    "gross_margin": "売上総利益率",
    "operating_margin": "営業利益率",
    "ordinary_margin": "経常利益率",
    "net_margin": "純利益率",
    "roa": "ROA",
    "roe": "ROE",
    "equity_ratio": "自己資本比率",
    "liability_ratio": "負債比率",
    "debt_to_equity": "負債資本倍率",
    "asset_turnover": "総資産回転率",
    "current_ratio": "流動比率",
    "cf_quality": "営業CF/純利益",
    "operating_cf_margin": "営業CFマージン",
    "free_cash_flow": "フリーCF",
    "fcf_margin": "フリーCFマージン",
    "revenue_per_employee": "一人当たり売上高",
    "operating_income_per_employee": "一人当たり営業利益",
    "revenue_growth": "売上成長率",
    "net_income_growth": "純利益成長率",
}


FORMULAS = {
    "avg_confidence": "主要5項目（売上高、純利益、総資産、純資産、営業CF）のうち自動抽出できた項目数 ÷ 5 の平均値です。",
    "gross_margin": "売上総利益 ÷ 売上高",
    "operating_margin": "営業利益 ÷ 売上高",
    "ordinary_margin": "経常利益 ÷ 売上高",
    "net_margin": "当期純利益 ÷ 売上高",
    "roa": "当期純利益 ÷ 総資産",
    "roe": "当期純利益 ÷ 純資産",
    "equity_ratio": "純資産 ÷ 総資産",
    "liability_ratio": "(総資産 - 純資産) ÷ 総資産",
    "debt_to_equity": "(総資産 - 純資産) ÷ 純資産",
    "asset_turnover": "売上高 ÷ 総資産",
    "current_ratio": "流動資産 ÷ 流動負債",
    "cf_quality": "営業活動によるキャッシュ・フロー ÷ 当期純利益",
    "operating_cf_margin": "営業活動によるキャッシュ・フロー ÷ 売上高",
    "free_cash_flow": "営業活動によるキャッシュ・フロー + 投資活動によるキャッシュ・フロー",
    "fcf_margin": "フリーCF ÷ 売上高",
    "revenue_per_employee": "売上高 ÷ 従業員数",
    "operating_income_per_employee": "営業利益 ÷ 従業員数",
    "revenue_growth": "(当期売上高 - 前期売上高) ÷ 前期売上高",
    "net_income_growth": "(当期純利益 - 前期純利益) ÷ 前期純利益",
}


CHART_METRICS = [
    ("revenue", "売上高", "metrics"),
    ("operating_income", "営業利益", "metrics"),
    ("net_income", "純利益", "metrics"),
    ("operating_margin", "営業利益率", "derived"),
    ("roa", "ROA", "derived"),
    ("roe", "ROE", "derived"),
    ("equity_ratio", "自己資本比率", "derived"),
    ("current_ratio", "流動比率", "derived"),
    ("operating_cash_flow", "営業CF", "metrics"),
    ("cf_quality", "営業CF/純利益", "derived"),
    ("asset_turnover", "総資産回転率", "derived"),
]



CHART_METRIC_HINTS = {
    "revenue": "規模",
    "operating_income": "本業利益",
    "net_income": "最終利益",
    "operating_margin": "収益性",
    "roa": "収益性",
    "roe": "資本効率",
    "equity_ratio": "安全性",
    "current_ratio": "短期安全性",
    "operating_cash_flow": "CF",
    "cf_quality": "CF品質",
    "asset_turnover": "効率性",
}


def metric_spec(key: str, source: str, rank: bool = True, formula_key: str | None = None) -> dict[str, Any]:
    labels = {
        **DISPLAY_NAMES,
        **DERIVED_LABELS,
    }
    return {
        "key": key,
        "source": source,
        "label": labels.get(key, key),
        "formula_key": formula_key if formula_key is not None else key,
        "rank": rank,
    }


METRIC_CATEGORIES = [
    {
        "key": "operating",
        "label": "経営・成長性",
        "short_label": "経営",
        "description": "売上規模、利益水準、年度成長率から事業の拡大状況を確認します。",
        "metrics": [
            metric_spec("revenue", "metrics"),
            metric_spec("gross_profit", "metrics"),
            metric_spec("operating_income", "metrics"),
            metric_spec("ordinary_income", "metrics"),
            metric_spec("net_income", "metrics"),
            metric_spec("revenue_growth", "growth"),
            metric_spec("net_income_growth", "growth"),
        ],
    },
    {
        "key": "profitability",
        "label": "収益性",
        "short_label": "収益",
        "description": "利益率、ROA、ROEを中心に、売上や資産に対する利益創出力を見ます。",
        "metrics": [
            metric_spec("gross_margin", "derived"),
            metric_spec("operating_margin", "derived"),
            metric_spec("ordinary_margin", "derived"),
            metric_spec("net_margin", "derived"),
            metric_spec("roa", "derived"),
            metric_spec("roe", "derived"),
            metric_spec("operating_income", "metrics"),
            metric_spec("net_income", "metrics"),
        ],
    },
    {
        "key": "safety",
        "label": "安全性",
        "short_label": "安全",
        "description": "自己資本、流動性、負債依存度から財務耐久力を確認します。",
        "metrics": [
            metric_spec("total_assets", "metrics"),
            metric_spec("net_assets", "metrics"),
            metric_spec("current_assets", "metrics"),
            metric_spec("current_liabilities", "metrics", rank=False),
            metric_spec("equity_ratio", "derived"),
            metric_spec("current_ratio", "derived"),
            metric_spec("liability_ratio", "derived", rank=False),
            metric_spec("debt_to_equity", "derived", rank=False),
        ],
    },
    {
        "key": "cashflow",
        "label": "キャッシュフロー",
        "short_label": "CF",
        "description": "営業CF、投資CF、フリーCFと利益に対するキャッシュ創出品質を確認します。",
        "metrics": [
            metric_spec("operating_cash_flow", "metrics"),
            metric_spec("investing_cash_flow", "metrics", rank=False),
            metric_spec("financing_cash_flow", "metrics", rank=False),
            metric_spec("free_cash_flow", "derived"),
            metric_spec("operating_cf_margin", "derived"),
            metric_spec("fcf_margin", "derived"),
            metric_spec("cf_quality", "derived"),
        ],
    },
    {
        "key": "efficiency",
        "label": "効率性・生産性",
        "short_label": "効率",
        "description": "資産回転率と従業員当たり指標から、資産・人員の使い方を見ます。",
        "metrics": [
            metric_spec("asset_turnover", "derived"),
            metric_spec("revenue_per_employee", "derived"),
            metric_spec("operating_income_per_employee", "derived"),
            metric_spec("employees", "metrics"),
            metric_spec("revenue", "metrics"),
            metric_spec("operating_income", "metrics"),
        ],
    },
]

def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    value = numerator / denominator
    if not isfinite(value):
        return None
    return value


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)



COMPANY_NAME_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "UNKNOWN",
    "未判定",
    "不明",
    "該当なし",
}

CORPORATE_PREFIXES = (
    "株式会社",
    "有限会社",
    "合同会社",
)
CORPORATE_SUFFIXES = CORPORATE_PREFIXES + (
    "CO.,LTD.",
    "CO.LTD.",
    "COLTD.",
    "COLTD",
    "INC.",
    "INC",
    "LTD.",
    "LTD",
    "CORPORATION",
    "CORP.",
    "CORP",
)
DOCUMENT_CODE_RE = re.compile(r"(?<![0-9A-Z])S[0-9A-Z]{6,}(?![0-9A-Z])", re.IGNORECASE)


def normalize_identity(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"[\s　]+", "", text)
    text = text.strip("-_??/\\|:;,.????()[]{}<>????????")  # noqa: B005
    return text.upper()


def normalize_code(value: str | None) -> str:
    code = normalize_identity(value)
    return "" if code in COMPANY_NAME_PLACEHOLDERS else code


def company_name_identity_values(company_name: str | None) -> list[str]:
    normalized = normalize_identity(company_name)
    if normalized in COMPANY_NAME_PLACEHOLDERS:
        return []
    values = [normalized]
    core = normalized
    changed = True
    while changed:
        changed = False
        for prefix in CORPORATE_PREFIXES:
            if core.startswith(prefix) and len(core) > len(prefix):
                core = core[len(prefix):]
                changed = True
        for suffix in CORPORATE_SUFFIXES:
            if core.endswith(suffix) and len(core) > len(suffix):
                core = core[: -len(suffix)]
                changed = True
    core = normalize_identity(core)
    if core and core not in COMPANY_NAME_PLACEHOLDERS and core not in values:
        values.append(core)
    return values


def document_codes(doc: FinancialDocument) -> list[str]:
    codes: list[str] = []
    for source in (doc.filename, doc.stored_path):
        for match in DOCUMENT_CODE_RE.findall(source or ""):
            code = normalize_code(match)
            if code and code not in codes:
                codes.append(code)
    return codes


def enterprise_identity_tokens(doc: FinancialDocument) -> list[str]:
    tokens: list[str] = []
    security_code = normalize_code(doc.security_code)
    if security_code:
        tokens.append(f"security:{security_code}")
    edinet_code = normalize_code(doc.edinet_code)
    if edinet_code:
        tokens.append(f"edinet:{edinet_code}")
    for document_code in document_codes(doc):
        tokens.append(f"document:{document_code}")
    for company_name in company_name_identity_values(doc.company_name):
        tokens.append(f"company:{company_name}")
    return tokens


def document_key(doc: FinancialDocument) -> str:
    for value in (normalize_code(doc.security_code), normalize_code(doc.edinet_code)):
        if value:
            return value
    codes = document_codes(doc)
    if codes:
        return codes[0]
    names = company_name_identity_values(doc.company_name)
    if names:
        return names[0]
    return doc.id


def display_code(doc: FinancialDocument) -> str:
    if doc.security_code:
        return normalize_code(doc.security_code)
    if doc.edinet_code:
        return normalize_code(doc.edinet_code)
    codes = document_codes(doc)
    return codes[0] if codes else "-"


def latest_docs_first(docs: list[FinancialDocument]) -> list[FinancialDocument]:
    return sorted(docs, key=lambda doc: (doc.fiscal_year or -1, doc.filename), reverse=True)


def latest_group_value(docs: list[FinancialDocument], getter: Any) -> str:
    for doc in latest_docs_first(docs):
        value = getter(doc)
        if value:
            return value
    return ""


def enterprise_group_key(docs: list[FinancialDocument]) -> str:
    return (
        latest_group_value(docs, lambda doc: normalize_code(doc.security_code))
        or latest_group_value(docs, lambda doc: normalize_code(doc.edinet_code))
        or latest_group_value(docs, lambda doc: document_codes(doc)[0] if document_codes(doc) else "")
        or latest_group_value(docs, lambda doc: company_name_identity_values(doc.company_name)[0] if company_name_identity_values(doc.company_name) else "")
        or (docs[0].id if docs else "")
    )


def enterprise_alias_values(doc: FinancialDocument) -> set[str]:
    values = {document_key(doc), doc.security_code, doc.edinet_code, doc.company_name}
    values.update(document_codes(doc))
    values.update(company_name_identity_values(doc.company_name))
    values.update(token.split(":", 1)[1] for token in enterprise_identity_tokens(doc) if ":" in token)
    return {normalize_identity(value) for value in values if normalize_identity(value)}


def enterprise_identity_index(record: AnalysisRecord) -> dict[str, Any]:
    doc_ids = [doc.id for doc in record.documents]
    parent = {doc_id: doc_id for doc_id in doc_ids}

    def find(doc_id: str) -> str:
        while parent[doc_id] != doc_id:
            parent[doc_id] = parent[parent[doc_id]]
            doc_id = parent[doc_id]
        return doc_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    token_owner: dict[str, str] = {}
    for doc in record.documents:
        for token in enterprise_identity_tokens(doc):
            owner = token_owner.get(token)
            if owner is None:
                token_owner[token] = doc.id
            else:
                union(doc.id, owner)

    grouped_by_root: dict[str, list[FinancialDocument]] = defaultdict(list)
    for doc in record.documents:
        grouped_by_root[find(doc.id)].append(doc)

    groups: dict[str, list[FinancialDocument]] = {}
    doc_to_key: dict[str, str] = {}
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    for docs in grouped_by_root.values():
        base_key = enterprise_group_key(docs)
        key = base_key
        suffix = 2
        while key in groups:
            key = f"{base_key}#{suffix}"
            suffix += 1
        groups[key] = docs
        alias_candidates[normalize_identity(key)].add(key)
        for doc in docs:
            doc_to_key[doc.id] = key
            for alias in enterprise_alias_values(doc):
                alias_candidates[alias].add(key)

    aliases = {alias: next(iter(keys)) for alias, keys in alias_candidates.items() if alias and len(keys) == 1}
    return {"groups": groups, "doc_to_key": doc_to_key, "aliases": aliases}


def resolve_company_key(record: AnalysisRecord, selected_company: str | None = None) -> str:
    index = enterprise_identity_index(record)
    groups = index["groups"]
    if not groups:
        return ""
    if selected_company:
        if selected_company in groups:
            return selected_company
        alias = normalize_identity(selected_company)
        if alias in index["aliases"]:
            return index["aliases"][alias]
    return default_company_key(record)


def company_label_for_docs(docs: list[FinancialDocument]) -> str:
    if not docs:
        return ""
    latest = latest_docs_first(docs)[0]
    code = display_code(latest)
    label = f"{code} / {latest.company_name}" if code != "-" else latest.company_name
    identifiers = []
    security_codes = sorted({normalize_code(doc.security_code) for doc in docs if normalize_code(doc.security_code)})
    edinet_codes = sorted({normalize_code(doc.edinet_code) for doc in docs if normalize_code(doc.edinet_code)})
    if len(security_codes) > 1:
        identifiers.append("codes " + ", ".join(security_codes))
    if len(edinet_codes) > 1:
        identifiers.append("EDINET " + ", ".join(edinet_codes))
    return label + (" (" + "; ".join(identifiers) + ")" if identifiers else "")


def enrich_document(doc: FinancialDocument, company_key: str | None = None) -> dict[str, Any]:
    m = doc.metrics
    total_liabilities = None
    if m.get("total_assets") is not None and m.get("net_assets") is not None:
        total_liabilities = m["total_assets"] - m["net_assets"]  # type: ignore[operator]
    free_cash_flow = None
    if m.get("operating_cash_flow") is not None and m.get("investing_cash_flow") is not None:
        free_cash_flow = m["operating_cash_flow"] + m["investing_cash_flow"]  # type: ignore[operator]

    derived = {
        "gross_margin": safe_div(m.get("gross_profit"), m.get("revenue")),
        "operating_margin": safe_div(m.get("operating_income"), m.get("revenue")),
        "ordinary_margin": safe_div(m.get("ordinary_income"), m.get("revenue")),
        "net_margin": safe_div(m.get("net_income"), m.get("revenue")),
        "roa": safe_div(m.get("net_income"), m.get("total_assets")),
        "roe": safe_div(m.get("net_income"), m.get("net_assets")),
        "equity_ratio": safe_div(m.get("net_assets"), m.get("total_assets")),
        "liability_ratio": safe_div(total_liabilities, m.get("total_assets")),
        "debt_to_equity": safe_div(total_liabilities, m.get("net_assets")),
        "asset_turnover": safe_div(m.get("revenue"), m.get("total_assets")),
        "current_ratio": safe_div(m.get("current_assets"), m.get("current_liabilities")),
        "cf_quality": safe_div(m.get("operating_cash_flow"), m.get("net_income")),
        "operating_cf_margin": safe_div(m.get("operating_cash_flow"), m.get("revenue")),
        "free_cash_flow": free_cash_flow,
        "fcf_margin": safe_div(free_cash_flow, m.get("revenue")),
        "revenue_per_employee": safe_div(m.get("revenue"), m.get("employees")),
        "operating_income_per_employee": safe_div(m.get("operating_income"), m.get("employees")),
    }

    return {
        "doc": doc,
        "id": doc.id,
        "filename": doc.filename,
        "company_name": doc.company_name,
        "company_key": company_key or document_key(doc),
        "display_code": display_code(doc),
        "security_code": doc.security_code,
        "edinet_code": doc.edinet_code,
        "fiscal_year": doc.fiscal_year,
        "unit": doc.unit,
        "metrics": m,
        "derived": derived,
    }


def grouped_documents(record: AnalysisRecord) -> dict[str, list[FinancialDocument]]:
    return enterprise_identity_index(record)["groups"]


def document_options(record: AnalysisRecord) -> dict[str, list[Any]]:
    years = sorted({doc.fiscal_year for doc in record.documents if doc.fiscal_year is not None}, reverse=True)
    groups = grouped_documents(record)
    companies = [
        {"key": key, "label": company_label_for_docs(docs)}
        for key, docs in sorted(groups.items(), key=lambda item: company_label_for_docs(item[1]))
    ]
    return {"years": years, "companies": companies}


def default_year(record: AnalysisRecord) -> int | None:
    years = [doc.fiscal_year for doc in record.documents if doc.fiscal_year is not None]
    if not years:
        return None
    counts = Counter(years)
    return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]


def default_company_key(record: AnalysisRecord) -> str:
    groups = grouped_documents(record)
    if not groups:
        return ""
    return sorted(groups.items(), key=lambda item: (len(item[1]), item[0]), reverse=True)[0][0]


def select_documents(
    record: AnalysisRecord,
    mode: str,
    selected_year: int | None = None,
    selected_company: str | None = None,
    selected_doc_ids: list[str] | None = None,
) -> list[FinancialDocument]:
    docs = record.documents
    if mode == "same_year":
        year = selected_year if selected_year is not None else default_year(record)
        return [doc for doc in docs if doc.fiscal_year == year]
    if mode == "same_company":
        company_key = resolve_company_key(record, selected_company)
        return sorted(
            grouped_documents(record).get(company_key, []),
            key=lambda doc: (doc.fiscal_year or 0, doc.filename),
        )
    if selected_doc_ids:
        allowed = set(selected_doc_ids)
        return [doc for doc in docs if doc.id in allowed]
    return docs


def add_growth(rows: list[dict[str, Any]]) -> None:
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_company[row["company_key"]].append(row)

    for company_rows in by_company.values():
        company_rows.sort(key=lambda row: (row["fiscal_year"] or 0, row["filename"]))
        previous: dict[str, Any] | None = None
        for row in company_rows:
            row["growth"] = {"revenue_growth": None, "net_income_growth": None}
            if previous:
                row["growth"]["revenue_growth"] = pct_change(row["metrics"].get("revenue"), previous["metrics"].get("revenue"))
                row["growth"]["net_income_growth"] = pct_change(row["metrics"].get("net_income"), previous["metrics"].get("net_income"))
            previous = row


def sort_rows(mode: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if mode == "same_year":
        return sorted(rows, key=lambda row: (row["metrics"].get("revenue") is None, -(row["metrics"].get("revenue") or 0), row["company_key"]))
    if mode == "same_company":
        return sorted(rows, key=lambda row: (row["fiscal_year"] or 0, row["filename"]))
    return sorted(rows, key=lambda row: (row["company_key"], row["fiscal_year"] or 0, row["filename"]))


def metric_value(row: dict[str, Any], key: str, source: str) -> float | int | None:
    if source == "growth":
        return row.get("growth", {}).get(key)
    values = row.get(source, {})
    return values.get(key) if isinstance(values, dict) else None


def ranked_metric_items(rows: list[dict[str, Any]], metric: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    ranked_values = sorted(
        [(row, value) for row in rows if (value := metric_value(row, metric["key"], metric["source"])) is not None],
        key=lambda item: item[1],
        reverse=True,
    )[:limit]
    max_value = max((abs(value) for _, value in ranked_values), default=0)
    return [
        {
            "rank": index,
            "row": row,
            "value": value,
            "width": round(0 if max_value == 0 else min(100, abs(value) / max_value * 100), 1),
        }
        for index, (row, value) in enumerate(ranked_values, start=1)
    ]


def build_metric_categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for category in METRIC_CATEGORIES:
        metrics = [dict(metric) for metric in category["metrics"]]
        rankings = []
        for metric in metrics:
            if not metric.get("rank", True):
                continue
            items = ranked_metric_items(rows, metric)
            if items:
                rankings.append(
                    {
                        **metric,
                        "panel_key": f"{category['key']}-{metric['key']}",
                        "items": items,
                    }
                )
        categories.append(
            {
                "key": category["key"],
                "label": category["label"],
                "short_label": category["short_label"],
                "description": category["description"],
                "metrics": metrics,
                "rankings": rankings,
            }
        )
    return categories


def build_rankings(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    def rank(key: str, source: str = "metrics") -> list[dict[str, Any]]:
        return sorted(
            [row for row in rows if metric_value(row, key, source) is not None],
            key=lambda row: metric_value(row, key, source) or 0,
            reverse=True,
        )[:8]

    return {
        "revenue": rank("revenue"),
        "net_income": rank("net_income"),
        "roa": rank("roa", "derived"),
        "equity_ratio": rank("equity_ratio", "derived"),
    }


def _sparkline_path(series: list[float], width: int = 80, height: int = 28, padding: int = 3) -> str | None:
    """Generate SVG polyline points string for a sparkline; returns None if not enough data."""
    if len(series) < 2:
        return None
    mn = min(series)
    mx = max(series)
    rng = mx - mn or 1
    n = len(series)
    points = []
    for i, v in enumerate(series):
        x = padding + (width - 2 * padding) * i / (n - 1)
        y = height - padding - (height - 2 * padding) * (v - mn) / rng
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _yoy(series: list[float]) -> float | None:
    if len(series) < 2 or series[-2] == 0:
        return None
    return (series[-1] - series[-2]) / abs(series[-2])


def summary_kpis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    companies = {row["company_key"] for row in rows}
    years = sorted({row["fiscal_year"] for row in rows if row["fiscal_year"] is not None})
    avg_conf = sum(row["doc"].confidence for row in rows) / len(rows) if rows else 0

    # Per-year aggregates for sparklines (sum across companies/PDFs by year)
    by_year: dict[int, dict[str, float]] = {}
    for row in rows:
        year = row["fiscal_year"]
        if year is None:
            continue
        bucket = by_year.setdefault(year, {"revenue": 0.0, "net_income": 0.0, "operating_income": 0.0, "count": 0})
        for key in ("revenue", "net_income", "operating_income"):
            v = row["metrics"].get(key)
            if v is not None:
                bucket[key] += v
        bucket["count"] += 1

    sorted_years = sorted(by_year.keys())
    revenue_series = [by_year[y]["revenue"] for y in sorted_years]
    net_income_series = [by_year[y]["net_income"] for y in sorted_years]
    operating_series = [by_year[y]["operating_income"] for y in sorted_years]

    return {
        "document_count": len(rows),
        "company_count": len(companies),
        "year_range": f"{years[0]}-{years[-1]}" if len(years) > 1 else (str(years[0]) if years else "未判定"),
        "avg_confidence": avg_conf,
        "total_revenue": sum(row["metrics"].get("revenue") or 0 for row in rows),
        "total_net_income": sum(row["metrics"].get("net_income") or 0 for row in rows),
        # Sparkline data
        "trend_years": sorted_years,
        "revenue_series": revenue_series,
        "revenue_spark": _sparkline_path(revenue_series),
        "revenue_yoy": _yoy(revenue_series),
        "net_income_series": net_income_series,
        "net_income_spark": _sparkline_path(net_income_series),
        "net_income_yoy": _yoy(net_income_series),
        "operating_spark": _sparkline_path(operating_series),
    }


def bar_items(rows: list[dict[str, Any]], key: str, source: str = "metrics", limit: int = 8) -> list[dict[str, Any]]:
    return ranked_metric_items(rows, metric_spec(key, source), limit=limit)


CHART_TYPE_LABELS = {
    "scatter": "散点図",
    "line": "折れ線図",
    "bar": "柱状図",
}


def resolve_chart_type(mode: str, chart_type: str | None = None, rows: list[dict[str, Any]] | None = None) -> str:
    if mode == "same_year":
        return "bar"
    if mode == "same_company":
        return "line"
    resolved = chart_type if chart_type in CHART_TYPE_LABELS else "scatter"
    if resolved == "scatter" and rows is not None:
        years = {row["fiscal_year"] for row in rows if row["fiscal_year"] is not None}
        companies = {row["company_key"] for row in rows}
        if len(years) <= 1 and len(companies) > 1:
            return "bar"
    return resolved


def chart_value_extent(values: list[float]) -> tuple[float, float]:
    min_value = min(values)
    max_value = max(values)
    if max_value == min_value:
        padding = abs(max_value) * 0.08 or 1
        return min_value - padding, max_value + padding
    padding = (max_value - min_value) * 0.08
    return min_value - padding, max_value + padding


def chart_y(value: float, min_value: float, max_value: float) -> float:
    return 132 - (value - min_value) / (max_value - min_value) * 104


def _compact_label(value: float, metric_key: str) -> str:
    if metric_key == "employees":
        return f"{fmt_number(value, 0)}人"
    if metric_key in {"asset_turnover", "current_ratio", "cf_quality", "debt_to_equity"}:
        return fmt_ratio(value)
    if metric_key.endswith("_margin") or metric_key in {"roa", "roe", "equity_ratio", "liability_ratio", "revenue_growth", "net_income_growth"}:
        return fmt_percent(value)
    return fmt_money_compact(value)


def _y_ticks(min_v: float, max_v: float, metric_key: str) -> list[dict]:
    mid_v = min_v + (max_v - min_v) * 0.5
    return [
        {"y": 28,  "label": _compact_label(max_v, metric_key)},
        {"y": 80,  "label": _compact_label(mid_v, metric_key)},
        {"y": 132, "label": _compact_label(min_v, metric_key)},
    ]


def row_chart_label(row: dict[str, Any]) -> str:
    code = row.get("display_code") or "-"
    name = row.get("company_name") or ""
    return f"{code} {name}".strip()


def chart_metric_defs(category: dict[str, Any]) -> list[dict[str, Any]]:
    return list(category["metrics"])


def metric_charts(rows: list[dict[str, Any]], chart_type: str, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if chart_type == "line":
        return line_charts(rows, metrics)
    if chart_type == "bar":
        return bar_charts(rows, metrics)
    return scatter_charts(rows, metrics)


def _format_hint(metric_key: str) -> str:
    """Return a format hint for client-side number formatting in charts."""
    if metric_key == "employees":
        return "people"
    if metric_key in {"asset_turnover", "current_ratio", "cf_quality", "debt_to_equity"}:
        return "ratio"
    if metric_key.endswith("_margin") or metric_key in {"roa", "roe", "equity_ratio", "liability_ratio", "revenue_growth", "net_income_growth"}:
        return "percent"
    if metric_key in {"revenue_per_employee", "operating_income_per_employee"}:
        return "money_per_person"
    return "money"


def build_echarts_payload(chart: dict[str, Any]) -> dict[str, Any]:
    """Reduce internal chart dict to a JSON payload consumable by ECharts client code."""
    chart_type = chart["type"]
    metric_key = chart["key"]
    fmt = _format_hint(metric_key)

    if chart_type == "line":
        years = chart["years"]
        series = []
        for s in chart["series"]:
            value_by_year = {p["year"]: p["value"] for p in s["raw_points"]}
            series.append({
                "name": s["label"],
                "data": [value_by_year.get(y) for y in years],
                "color": s["color"],
            })
        return {"type": "line", "format": fmt, "categories": years, "series": series}

    if chart_type == "bar":
        return {
            "type": "bar",
            "format": fmt,
            "categories": [b.get("label", "") for b in chart["bars"]],
            "years": [b.get("year") for b in chart["bars"]],
            "values": [b["value"] for b in chart["bars"]],
            "colors": [b.get("color", "#6ea8ff") for b in chart["bars"]],
        }

    if chart_type == "scatter":
        points = chart["series"][0]["raw_points"] if chart["series"] else []
        return {
            "type": "scatter",
            "format": fmt,
            "points": [
                {"label": p["label"], "year": p["year"], "value": p["value"], "color": p["color"]}
                for p in points
            ],
        }

    return {"type": chart_type, "format": fmt}


def metric_chart_categories(rows: list[dict[str, Any]], chart_type: str) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for category in METRIC_CATEGORIES:
        metrics = chart_metric_defs(category)
        charts = metric_charts(rows, chart_type, metrics)
        if not charts:
            continue
        for chart in charts:
            chart["panel_key"] = f"{category['key']}-{chart['key']}"
            chart["category_key"] = category["key"]
            chart["category_label"] = category["label"]
            chart["echarts"] = build_echarts_payload(chart)
        categories.append(
            {
                "key": category["key"],
                "label": category["label"],
                "short_label": category["short_label"],
                "description": category["description"],
                "charts": charts,
            }
        )
    return categories


def line_charts(rows: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    charts: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["fiscal_year"] is not None:
            grouped[row["company_key"]].append(row)

    palette = ["#3db8a0", "#4e8ee8", "#d4893a", "#9472d4", "#2cb8cc", "#d95050"]
    for metric in metrics:
        metric_key = metric["key"]
        metric_label = metric["label"]
        source = metric["source"]
        points: list[tuple[dict[str, Any], float]] = []
        for row in rows:
            value = metric_value(row, metric_key, source)
            if value is not None and row["fiscal_year"] is not None:
                points.append((row, value))
        if not points:
            continue
        years = sorted({row["fiscal_year"] for row, _ in points})
        values = [value for _, value in points]
        min_value, max_value = chart_value_extent(values)

        series = []
        for index, (key, company_rows) in enumerate(sorted(grouped.items())):
            company_rows = sorted(company_rows, key=lambda row: row["fiscal_year"])
            coords = []
            raw_points = []
            color = palette[index % len(palette)]
            for row in company_rows:
                value = metric_value(row, metric_key, source)
                if value is None or row["fiscal_year"] is None:
                    continue
                x = 150 if len(years) == 1 else 24 + years.index(row["fiscal_year"]) / (len(years) - 1) * 252
                y = chart_y(value, min_value, max_value)
                point_label = row_chart_label(row)
                coords.append(f"{x:.1f},{y:.1f}")
                raw_points.append({"x": round(x, 1), "y": round(y, 1), "year": row["fiscal_year"], "value": value, "label": point_label, "color": color})
            if coords:
                first = company_rows[-1]
                series.append({"key": key, "label": f"{first['display_code']} {first['company_name']}", "color": color, "points": " ".join(coords), "raw_points": raw_points})
        charts.append({"key": metric_key, "label": metric_label, "hint": CHART_METRIC_HINTS.get(metric_key, ""), "source": source, "formula_key": metric.get("formula_key", metric_key), "type": "line", "type_label": CHART_TYPE_LABELS["line"], "subtitle": f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0]), "years": years, "x_ticks": [], "series": series, "bars": [], "y_ticks": _y_ticks(min_value, max_value, metric_key)})
    return charts


def scatter_charts(rows: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    charts: list[dict[str, Any]] = []
    palette = ["#3db8a0", "#4e8ee8", "#d4893a", "#9472d4", "#2cb8cc", "#d95050", "#8ab83d", "#d45e8a"]
    for metric in metrics:
        metric_key = metric["key"]
        metric_label = metric["label"]
        source = metric["source"]
        chart_rows = [(row, metric_value(row, metric_key, source)) for row in rows if metric_value(row, metric_key, source) is not None]
        if not chart_rows:
            continue
        values = [value for _, value in chart_rows if value is not None]
        min_value, max_value = chart_value_extent(values)
        count = len(chart_rows)
        raw_points = []
        x_ticks = []
        label_step = max(1, count // 6)
        for index, (row, value) in enumerate(chart_rows):
            if value is None:
                continue
            x = 150 if count == 1 else 24 + index / (count - 1) * 252
            y = chart_y(value, min_value, max_value)
            color = palette[index % len(palette)]
            label_text = row_chart_label(row)
            short_label = row.get("display_code") or str(index + 1)
            raw_points.append({"x": round(x, 1), "y": round(y, 1), "year": row["fiscal_year"] or "年度不明", "value": value, "label": label_text, "color": color})
            x_ticks.append({"x": round(x, 1), "label": short_label, "show": count <= 8 or index == 0 or index == count - 1 or index % label_step == 0})
        years = sorted({row["fiscal_year"] for row, _ in chart_rows if row["fiscal_year"] is not None})
        subtitle = f"{years[0]}-{years[-1]}" if len(years) > 1 else (str(years[0]) if years else "年度混在")
        charts.append({"key": metric_key, "label": metric_label, "hint": CHART_METRIC_HINTS.get(metric_key, ""), "source": source, "formula_key": metric.get("formula_key", metric_key), "type": "scatter", "type_label": CHART_TYPE_LABELS["scatter"], "subtitle": subtitle, "years": years, "x_ticks": x_ticks, "series": [{"key": "scatter", "label": "データ点", "color": "#2f6f62", "points": "", "raw_points": raw_points}], "bars": [], "y_ticks": _y_ticks(min_value, max_value, metric_key)})
    return charts


def bar_charts(rows: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    charts: list[dict[str, Any]] = []
    palette = ["#3db8a0", "#4e8ee8", "#d4893a", "#9472d4", "#2cb8cc", "#d95050", "#8ab83d", "#d45e8a"]
    for metric in metrics:
        metric_key = metric["key"]
        metric_label = metric["label"]
        source = metric["source"]
        chart_rows = [(row, metric_value(row, metric_key, source)) for row in rows if metric_value(row, metric_key, source) is not None]
        if not chart_rows:
            continue
        values = [value for _, value in chart_rows if value is not None]
        min_value, max_value = chart_value_extent(values + [0])
        baseline = chart_y(0, min_value, max_value)
        count = len(chart_rows)
        label_step = max(1, count // 6)
        bar_width = max(8, min(24, 190 / max(count, 1)))
        bars = []
        x_ticks = []
        for index, (row, value) in enumerate(chart_rows):
            if value is None:
                continue
            x = 150 if count == 1 else 24 + index / (count - 1) * 252
            y = chart_y(value, min_value, max_value)
            top = min(y, baseline)
            height = max(1.5, abs(baseline - y))
            color = palette[index % len(palette)]
            label_text = row_chart_label(row)
            short_label = row.get("display_code") or str(index + 1)
            bars.append(
                {
                    "x": round(x - bar_width / 2, 1),
                    "center_x": round(x, 1),
                    "y": round(top, 1),
                    "width": round(bar_width, 1),
                    "height": round(height, 1),
                    "baseline": round(baseline, 1),
                    "year": row["fiscal_year"] or "年度不明",
                    "value": value,
                    "label": label_text,
                    "color": color,
                }
            )
            x_ticks.append({"x": round(x, 1), "label": short_label, "show": count <= 8 or index == 0 or index == count - 1 or index % label_step == 0})
        years = sorted({row["fiscal_year"] for row, _ in chart_rows if row["fiscal_year"] is not None})
        subtitle = f"{years[0]}-{years[-1]}" if len(years) > 1 else (str(years[0]) if years else "年度混在")
        charts.append({"key": metric_key, "label": metric_label, "hint": CHART_METRIC_HINTS.get(metric_key, ""), "source": source, "formula_key": metric.get("formula_key", metric_key), "type": "bar", "type_label": CHART_TYPE_LABELS["bar"], "subtitle": subtitle, "years": years, "x_ticks": x_ticks, "series": [], "bars": bars, "baseline": round(baseline, 1), "y_ticks": _y_ticks(min_value, max_value, metric_key)})
    return charts

def build_analysis(
    record: AnalysisRecord,
    mode: str = "same_year",
    selected_year: int | None = None,
    selected_company: str | None = None,
    selected_doc_ids: list[str] | None = None,
    chart_type: str | None = None,
) -> dict[str, Any]:
    if mode not in MODE_LABELS:
        mode = "same_year"
    if mode == "same_year" and selected_year is None:
        selected_year = default_year(record)
    if mode == "same_company":
        selected_company = resolve_company_key(record, selected_company)

    docs = select_documents(record, mode, selected_year, selected_company, selected_doc_ids)
    doc_to_company_key = enterprise_identity_index(record)["doc_to_key"]
    rows = [enrich_document(doc, doc_to_company_key.get(doc.id)) for doc in docs]
    add_growth(rows)
    rows = sort_rows(mode, rows)
    chart_type = resolve_chart_type(mode, chart_type, rows)
    chart_categories = metric_chart_categories(rows, chart_type)
    trend_charts = [chart for category in chart_categories for chart in category["charts"]]

    return {
        "record": record,
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "selected_year": selected_year,
        "selected_company": selected_company,
        "selected_doc_ids": selected_doc_ids or [],
        "chart_type": chart_type,
        "chart_type_label": CHART_TYPE_LABELS[chart_type],
        "chart_type_labels": CHART_TYPE_LABELS,
        "options": document_options(record),
        "rows": rows,
        "kpis": summary_kpis(rows),
        "rankings": build_rankings(rows),
        "metric_categories": build_metric_categories(rows),
        "bar_revenue": bar_items(rows, "revenue"),
        "bar_roa": bar_items(rows, "roa", "derived"),
        "chart_categories": chart_categories,
        "trend_charts": trend_charts,
        "metric_order": METRIC_ORDER,
        "metric_labels": DISPLAY_NAMES,
        "derived_labels": DERIVED_LABELS,
        "mode_labels": MODE_LABELS,
        "formulas": FORMULAS,
    }
