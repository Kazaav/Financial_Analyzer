from __future__ import annotations


def fmt_number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def fmt_money(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{fmt_number(value, 0)} 百万円"


def fmt_percent(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"


def fmt_ratio(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}x"


def fmt_metric(value: float | int | None, key: str) -> str:
    if key == "employees":
        return f"{fmt_number(value, 0)} 人" if value is not None else "-"
    if key in {"asset_turnover", "current_ratio", "cf_quality", "debt_to_equity"}:
        return fmt_ratio(value)
    if key.endswith("_margin") or key in {"roa", "roe", "equity_ratio", "liability_ratio", "revenue_growth", "net_income_growth"}:
        return fmt_percent(value)
    if key in {"revenue_per_employee", "operating_income_per_employee"}:
        return f"{fmt_number(value, 1)} 百万円/人" if value is not None else "-"
    return fmt_money(value)


def score_label(score: int | float) -> str:
    score = float(score)
    if score >= 75:
        return "良好"
    if score >= 55:
        return "標準"
    if score >= 35:
        return "注意"
    return "要確認"
