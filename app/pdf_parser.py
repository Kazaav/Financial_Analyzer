from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import fitz

from .models import FinancialDocument


DISPLAY_NAMES = {
    "revenue": "売上高",
    "gross_profit": "売上総利益",
    "operating_income": "営業利益",
    "ordinary_income": "経常利益",
    "net_income": "親会社株主に帰属する当期純利益",
    "total_assets": "総資産",
    "net_assets": "純資産",
    "current_assets": "流動資産",
    "current_liabilities": "流動負債",
    "operating_cash_flow": "営業CF",
    "investing_cash_flow": "投資CF",
    "financing_cash_flow": "財務CF",
    "employees": "従業員数",
}


NUMBER_RE = re.compile(r"[△▲(（-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*[)）]?")
UNIT_RE = re.compile(r"[（(]\s*(百万円|千円|円|人|%|％|倍)\s*[)）]")
EDINET_PAGE_RE = re.compile(r"\s+\d+/\d+\s*$")


@dataclass
class PageText:
    page: int
    text: str
    lines: list[str]


@dataclass
class ExtractedValue:
    value: float
    label: str
    page: int
    source: str


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    text = text.replace("▲", "△")
    text = text.replace("−", "-").replace("―", "-")
    return text


def normalize_identity(value: str) -> str:
    value = normalize_text(value).upper()
    value = re.sub(r"株式会社|有限会社|合同会社|株式會社|INC\.?|CORP\.?|CO\.?LTD\.?|CO\.?,?\s*LTD\.?", "", value)
    value = re.sub(r"[^0-9A-Z一-龥ぁ-んァ-ヶー]", "", value)
    return value


def clean_line(line: str) -> str:
    line = normalize_text(line).strip()
    line = re.sub(r"\s+", " ", line)
    return line


def extract_pdf_pages(path: Path) -> tuple[list[PageText], int]:
    doc = fitz.open(path)
    pages: list[PageText] = []
    for index, page in enumerate(doc, start=1):
        text = normalize_text(page.get_text("text"))
        lines = [clean_line(line) for line in text.splitlines() if clean_line(line)]
        pages.append(PageText(page=index, text=text, lines=lines))
    return pages, doc.page_count


def extract_pdf_text(path: Path) -> tuple[str, int]:
    pages, page_count = extract_pdf_pages(path)
    return "\n".join(page.text for page in pages), page_count


def parse_number(token: str) -> float | None:
    token = normalize_text(token)
    if token in {"", "-", "－"}:
        return None
    negative = "△" in token or token.strip().startswith("-") or token.strip().startswith("(")
    token = token.replace(",", "")
    token = re.sub(r"[^\d.]", "", token)
    if not token:
        return None
    try:
        value = float(token)
    except ValueError:
        return None
    return -value if negative else value


def numeric_values(line: str) -> list[float]:
    values: list[float] = []
    for match in NUMBER_RE.finditer(line):
        value = parse_number(match.group(0))
        if value is not None:
            values.append(value)
    return values


def is_unit_line(line: str) -> bool:
    return bool(UNIT_RE.search(line)) or line in {"百万円", "千円", "円", "人", "%", "％", "倍"}


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if EDINET_PAGE_RE.match(line):
        return True
    return line.startswith("EDINET提出書類") or line == "有価証券報告書"


def looks_numeric_line(line: str) -> bool:
    stripped = line.strip()
    if stripped in {"-", "－"}:
        return True
    if re.fullmatch(r"[△▲(（-]?\s*\d[\d,]*(?:\.\d+)?\s*[)）]?", stripped):
        return True
    if re.fullmatch(r"※\d+\s+[△▲(（-]?\s*\d[\d,]*(?:\.\d+)?\s*[)）]?", stripped):
        return True
    return False


def detect_unit(text: str) -> str:
    head = text[:60000]
    if "単位:百万円" in head or "単位 百万円" in head or "百万円" in head:
        return "百万円"
    if "単位:千円" in head or "単位 千円" in head or "千円" in head:
        return "千円"
    if "単位:円" in head or "単位 円" in head:
        return "円"
    return "百万円"


def unit_to_million_yen(value: float | None, unit: str, metric_key: str) -> float | None:
    if value is None:
        return None
    if metric_key == "employees":
        return value
    if unit == "千円":
        return round(value / 1000, 2)
    if unit == "円":
        return round(value / 1_000_000, 2)
    return value


def clean_company_name(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" :：-[]【】")
    value = re.sub(r"\([A-Z0-9]+\)$", "", value).strip()
    return value[:60].strip()


def detect_company_name(text: str, filename: str) -> str:
    sample = text[:12000]
    patterns = [
        r"【会社名】\s*([^\n【]+)",
        r"【提出会社の名称】\s*([^\n【]+)",
        r"【商号】\s*([^\n【]+)",
        r"EDINET提出書類\s*\n\s*([^(\n]+)\([A-Z0-9]+\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sample)
        if match:
            candidate = clean_company_name(match.group(1))
            if candidate and candidate not in {"】", "【"}:
                return candidate

    stem = Path(filename).stem
    stem = re.sub(r"S\d+[A-Z0-9_]*|type\d+|pdf|有価証券報告書|20\d{2}", "", stem, flags=re.IGNORECASE)
    return clean_company_name(stem) or "未判定"


def detect_english_name(text: str) -> str:
    sample = text[:12000]
    match = re.search(r"【英訳名】\s*([^\n【]+)", sample)
    return clean_company_name(match.group(1)) if match else ""


def detect_edinet_code(text: str) -> str:
    sample = text[:20000]
    match = re.search(r"\(([EG]\d{5})\)", sample)
    return match.group(1) if match else ""


@lru_cache(maxsize=1)
def local_stock_code_name_index() -> list[tuple[str, str]]:
    candidates = [
        Path.home() / "OneDrive" / "大学院" / "论文" / "数据" / "paper_all_company_folders",
        Path.home() / "OneDrive" / "大学院" / "論文" / "データ" / "paper_all_company_folders",
    ]
    roots: list[Path] = []
    for candidate in candidates:
        if candidate.exists():
            roots.append(candidate)
    if not roots:
        for root in (Path.home() / "OneDrive").rglob("paper_all_company_folders"):
            if root.is_dir():
                roots.append(root)
                break

    index: list[tuple[str, str]] = []
    for root in roots:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            match = re.match(r"^(\d{4})[_\-\s](.+)$", child.name)
            if match:
                code, name = match.groups()
                normalized = normalize_identity(name)
                if normalized:
                    index.append((code, normalized))
    return index


def detect_security_code(text: str, filename: str, path: Path, company_name: str, english_name: str) -> str:
    joined = "\n".join([filename, str(path), text[:30000]])
    patterns = [
        r"証券コード[:：\s]*([0-9]{4})",
        r"コード番号[:：\s]*([0-9]{4})",
        r"(^|[\\/_\-\s])([0-9]{4})[_\-\s]",
    ]
    for pattern in patterns:
        match = re.search(pattern, joined, flags=re.MULTILINE | re.DOTALL)
        if match:
            return match.group(match.lastindex or 1)

    edinet_match = re.search(r"\(([EG]\d{5})\)", text[:20000])
    if edinet_match and edinet_match.group(1) == "E05617":
        return "2121"

    company_keys = {normalize_identity(company_name), normalize_identity(english_name)}
    company_keys = {key for key in company_keys if key}
    for code, indexed_name in local_stock_code_name_index():
        if any(key == indexed_name or key in indexed_name or indexed_name in key for key in company_keys):
            return code
    return ""


def detect_fiscal_period(text: str) -> str:
    sample = text[:20000]
    patterns = [
        r"【事業年度】\s*([^\n]+)",
        r"(第\s*\d+\s*期\s*[\(（]?\s*自\s*\d{4}年.*?至\s*\d{4}年.*?[）\)]?)",
        r"(自\s*\d{4}年\d{1,2}月\d{1,2}日\s*至\s*\d{4}年\d{1,2}月\d{1,2}日)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sample, flags=re.DOTALL)
        if match:
            period = re.sub(r"\s+", " ", match.group(1)).strip()
            return period[:120]
    return ""


def detect_fiscal_year(text: str, filename: str) -> int | None:
    sample = text[:30000]
    patterns = [
        r"【事業年度】[\s\S]{0,120}?至\s*(20\d{2})年",
        r"第\s*\d+\s*期[\s\S]{0,120}?至\s*(20\d{2})年",
        r"当連結会計年度[\s\S]{0,120}?至\s*(20\d{2})年",
        r"当事業年度[\s\S]{0,120}?至\s*(20\d{2})年",
        r"決算年月[\s\S]{0,120}?(20\d{2})年\d{1,2}月",
    ]
    for pattern in patterns:
        match = re.search(pattern, sample)
        if match:
            return int(match.group(1))

    filename_year = re.search(r"(20\d{2})", filename)
    if filename_year:
        return int(filename_year.group(1))
    return None


def find_section_pages(pages: list[PageText], start: str, end: str | None = None, window: int = 3) -> list[PageText]:
    start_index = None
    for index, page in enumerate(pages):
        if start in page.text:
            start_index = index
            break
    if start_index is None:
        return []

    end_index = min(len(pages), start_index + window)
    if end:
        for index in range(start_index + 1, min(len(pages), start_index + window + 3)):
            if end in pages[index].text:
                end_index = index
                break
    return pages[start_index:end_index]


def collect_values_after_label(lines: list[str], index: int, label_parts: list[str], max_scan: int = 14) -> list[float] | None:
    last_label_index = index
    if len(label_parts) > 1:
        for offset in range(0, min(4, len(lines) - index)):
            if any(part in lines[index + offset] for part in label_parts):
                last_label_index = index + offset

    values: list[float] = []
    saw_content = False
    for line in lines[last_label_index + 1 : last_label_index + 1 + max_scan]:
        if is_noise_line(line) or is_unit_line(line):
            continue
        if looks_numeric_line(line):
            saw_content = True
            values.extend(numeric_values(line))
            continue
        if values:
            break
        if saw_content:
            break
        return None
    return values if values else None


def extract_row_from_pages(
    pages: list[PageText],
    label_parts: list[str],
    label: str,
    source: str,
    exact_first_line: bool = False,
    prefer_last: bool = False,
) -> ExtractedValue | None:
    candidates: list[ExtractedValue] = []
    for page in pages:
        lines = page.lines
        for index, line in enumerate(lines):
            window = "".join(lines[index : min(index + 4, len(lines))])
            if exact_first_line:
                matched = line == label_parts[0]
            elif len(label_parts) == 1:
                matched = label_parts[0] in line
            else:
                matched = all(part in window for part in label_parts)
            if not matched:
                continue
            values = collect_values_after_label(lines, index, label_parts)
            if not values:
                continue
            candidates.append(ExtractedValue(value=values[-1], label=label, page=page.page, source=f"{source} p.{page.page}"))
    if not candidates:
        return None
    return candidates[-1] if prefer_last else candidates[0]


def extract_metrics_from_major_indicators(pages: list[PageText]) -> dict[str, ExtractedValue]:
    section_pages = find_section_pages(pages, "連結経営指標等", "(2) 提出会社", window=3)
    source = "主要な経営指標等の推移"
    specs = {
        "revenue": (["売上高"], "売上高"),
        "ordinary_income": (["経常利益"], "経常利益"),
        "net_income": (["親会社株主に帰属する", "当期純利益"], "親会社株主に帰属する当期純利益"),
        "net_assets": (["純資産額"], "純資産額"),
        "total_assets": (["総資産額"], "総資産額"),
        "operating_cash_flow": (["営業活動による", "キャッシュ・フロー"], "営業活動によるキャッシュ・フロー"),
        "investing_cash_flow": (["投資活動による", "キャッシュ・フロー"], "投資活動によるキャッシュ・フロー"),
        "financing_cash_flow": (["財務活動による", "キャッシュ・フロー"], "財務活動によるキャッシュ・フロー"),
        "employees": (["従業員数"], "従業員数"),
    }
    return {
        key: value
        for key, (parts, label) in specs.items()
        if (value := extract_row_from_pages(section_pages, parts, label, source)) is not None
    }


def extract_metrics_from_statements(pages: list[PageText]) -> dict[str, ExtractedValue]:
    bs_pages = find_section_pages(pages, "連結貸借対照表", "連結損益計算書", window=4)
    pl_pages = find_section_pages(pages, "連結損益計算書", "連結包括利益計算書", window=3)
    cf_pages = find_section_pages(pages, "連結キャッシュ・フロー計算書", "注記事項", window=4)
    specs: list[tuple[str, list[PageText], list[str], str, str, bool, bool]] = [
        ("current_assets", bs_pages, ["流動資産合計"], "流動資産合計", "連結貸借対照表", True, False),
        ("total_assets", bs_pages, ["資産合計"], "資産合計", "連結貸借対照表", True, False),
        ("current_liabilities", bs_pages, ["流動負債合計"], "流動負債合計", "連結貸借対照表", True, False),
        ("net_assets", bs_pages, ["純資産合計"], "純資産合計", "連結貸借対照表", True, False),
        ("revenue", pl_pages, ["売上高"], "売上高", "連結損益計算書", True, False),
        ("gross_profit", pl_pages, ["売上総利益"], "売上総利益", "連結損益計算書", True, False),
        ("operating_income", pl_pages, ["営業利益"], "営業利益", "連結損益計算書", True, False),
        ("ordinary_income", pl_pages, ["経常利益"], "経常利益", "連結損益計算書", True, False),
        ("net_income", pl_pages, ["親会社株主に帰属する当期純利益"], "親会社株主に帰属する当期純利益", "連結損益計算書", True, False),
        ("operating_cash_flow", cf_pages, ["営業活動によるキャッシュ・フロー"], "営業活動によるキャッシュ・フロー", "連結キャッシュ・フロー計算書", True, True),
        ("investing_cash_flow", cf_pages, ["投資活動によるキャッシュ・フロー"], "投資活動によるキャッシュ・フロー", "連結キャッシュ・フロー計算書", True, True),
        ("financing_cash_flow", cf_pages, ["財務活動によるキャッシュ・フロー"], "財務活動によるキャッシュ・フロー", "連結キャッシュ・フロー計算書", True, True),
    ]
    extracted: dict[str, ExtractedValue] = {}
    for key, section, parts, label, source, exact, prefer_last in specs:
        value = extract_row_from_pages(section, parts, label, source, exact_first_line=exact, prefer_last=prefer_last)
        if value is not None:
            extracted[key] = value
    return extracted


def extract_metrics(pages: list[PageText], default_unit: str) -> tuple[dict[str, float | None], list[str], float]:
    major = extract_metrics_from_major_indicators(pages)
    statements = extract_metrics_from_statements(pages)
    metrics: dict[str, float | None] = {key: None for key in DISPLAY_NAMES}
    notes: list[str] = []

    for key in DISPLAY_NAMES:
        picked = statements.get(key) or major.get(key)
        if key in {"operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "employees"}:
            picked = major.get(key) or statements.get(key)
        if picked is None:
            continue
        metrics[key] = unit_to_million_yen(picked.value, default_unit, key)
        notes.append(f"{DISPLAY_NAMES[key]}: {picked.value:,.0f} ({picked.source})")

    essentials = ["revenue", "net_income", "total_assets", "net_assets", "operating_cash_flow"]
    found = sum(1 for key in essentials if metrics.get(key) is not None)
    confidence = round(found / len(essentials), 2)
    if confidence < 0.8:
        notes.append("主要項目の抽出数が不足しています。抽出結果レビューでPDF本文と照合してください。")
    if metrics.get("gross_profit") is None:
        notes.append("売上総利益は企業の表示形式により未抽出の場合があります。")
    return metrics, notes, confidence


def parse_pdf(path: Path, doc_id: str, original_filename: str) -> FinancialDocument:
    pages, page_count = extract_pdf_pages(path)
    text = "\n".join(page.text for page in pages)
    unit = detect_unit(text)
    company_name = detect_company_name(text, original_filename)
    english_name = detect_english_name(text)
    edinet_code = detect_edinet_code(text)
    security_code = detect_security_code(text, original_filename, path, company_name, english_name)
    metrics, notes, confidence = extract_metrics(pages, unit)
    if security_code:
        notes.insert(0, f"証券コード: {security_code}")
    if edinet_code:
        notes.insert(0, f"EDINETコード: {edinet_code}")
    excerpt = re.sub(r"\s+", " ", text[:1000]).strip()
    return FinancialDocument(
        id=doc_id,
        filename=original_filename,
        stored_path=str(path),
        company_name=company_name,
        fiscal_year=detect_fiscal_year(text, original_filename),
        fiscal_period=detect_fiscal_period(text),
        unit=unit,
        page_count=page_count,
        char_count=len(text),
        text_excerpt=excerpt,
        security_code=security_code,
        edinet_code=edinet_code,
        metrics=metrics,
        extraction_notes=notes,
        confidence=confidence,
    )
