from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

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
# Footnote reference markers (※1, ＊2 …) that statement tables attach to values.
# PyMuPDF sometimes drops the space, fusing marker and number ("※4151,639"),
# which then fails to parse. We strip 「※/＊」 plus an optional single digit; the
# remaining "151,639" parses cleanly. Two-digit markers fused without a space are
# vanishingly rare in the primary statements and degrade gracefully.
NOTE_MARKER_RE = re.compile(r"[※＊*]\d?")


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


def strip_note_markers(line: str) -> str:
    """Remove ※N / ＊N footnote markers fused onto numeric values (see NOTE_MARKER_RE)."""
    return NOTE_MARKER_RE.sub("", line)


def numeric_values(line: str) -> list[float]:
    line = strip_note_markers(line)
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


# Lines starting with these are per-share or per-unit derivatives, not the
# primary aggregate metric. Used to skip e.g. "1株当たり純資産額" when we
# want "純資産" / "純資産額".
PER_UNIT_PREFIXES = (
    "1株当たり", "１株当たり",
    "基本的1株当たり", "基本的１株当たり",
    "希薄化後", "希薄化",
    "潜在株式", "潜在株式調整後",
    "従業員1人当たり", "1人当たり",
)


def is_per_unit_line(line: str) -> bool:
    s = line.strip()
    return any(s.startswith(prefix) for prefix in PER_UNIT_PREFIXES)


# A "parenthesized annotation" is a line whose ONLY content is (N) — typically
# 「外、X名」style sub-totals next to 従業員数. Distinguished from △N
# (proper financial negative numbers), which we must keep collecting (e.g. CF).
PAREN_ANNOTATION_RE = re.compile(r"^[（(]\s*\d[\d,]*(?:\.\d+)?\s*[)）]$")


def is_parenthesized_annotation(line: str) -> bool:
    return bool(PAREN_ANNOTATION_RE.match(line.strip()))


def looks_numeric_line(line: str) -> bool:
    stripped = strip_note_markers(line).strip()
    if stripped in {"-", "－"}:
        return True
    if re.fullmatch(r"[△▲(（-]?\s*\d[\d,]*(?:\.\d+)?\s*[)）]?", stripped):
        return True
    return bool(re.fullmatch(r"※\d+\s+[△▲(（-]?\s*\d[\d,]*(?:\.\d+)?\s*[)）]?", stripped))


def detect_unit(text: str) -> str:
    """Detect the dominant amount unit for the 主要な経営指標等の推移 table.

    Strategy: the table is at the very beginning of every 有報. We find the
    FIRST occurrence of "(百万円)" or "(千円)" after the 主要な経営指標 heading.
    Small companies (e.g. Avant Group) use 千円 throughout; large companies
    use 百万円. The first marker in the indicators table is authoritative.
    """
    head = text[:30000]

    # Locate the indicators section start
    anchor = re.search(r"主要な経営指標等の推移", head)
    start = anchor.end() if anchor else 0
    region = head[start : start + 8000]

    million = re.search(r"[（(]\s*百万円\s*[)）]", region)
    thousand = re.search(r"[（(]\s*千円\s*[)）]", region)

    if million and thousand:
        return "百万円" if million.start() < thousand.start() else "千円"
    if thousand:
        return "千円"
    if million:
        return "百万円"

    # Fallback to legacy whole-document scan
    if "単位:千円" in head or "単位 千円" in head:
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
    """Collect numeric values from the lines following a matched label.

    Tolerates label continuation lines (e.g. when "親会社株主に帰属する当期純利益"
    is split as "親会社株主に帰属する当期" + "純利益") by allowing up to 2 short
    non-numeric lines before the first value appears.
    """
    last_label_index = index
    if len(label_parts) > 1:
        for offset in range(0, min(4, len(lines) - index)):
            if any(part in lines[index + offset] for part in label_parts):
                last_label_index = index + offset

    values: list[float] = []
    saw_content = False
    continuation_text = 0
    for line in lines[last_label_index + 1 : last_label_index + 1 + max_scan]:
        if is_noise_line(line) or is_unit_line(line):
            continue
        if looks_numeric_line(line):
            # Annotation sub-row detection: once we've collected primary values,
            # any *parenthesized* (N)-style line (not △N) is a sub-annotation
            # row (typical 「外、平均臨時従業員数」 below 従業員数). Stop here.
            # △N is a proper financial negative and must keep being collected
            # (e.g. 財務CF △21,948).
            if values and is_parenthesized_annotation(line):
                break
            saw_content = True
            continuation_text = 0
            values.extend(numeric_values(line))
            continue
        if values:
            break
        if saw_content:
            break
        # Non-numeric, non-unit text BEFORE the first value. Likely a label
        # continuation. Allow up to 2 such lines then give up.
        if len(line) <= 24:
            continuation_text += 1
            if continuation_text > 2:
                return None
            continue
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
            # Skip per-share / per-unit derived rows; they're not the
            # aggregate metric we're after.
            if is_per_unit_line(line):
                continue
            window = "".join(lines[index : min(index + 4, len(lines))])
            if exact_first_line:
                # Strip leading/trailing symbols that PDF extraction may prepend/append
                # (e.g. 「売上総利益」→ 売上総利益, （売上総利益）→ 売上総利益)
                _stripped = re.sub(r'^[\s　「」（）()【】「」・./※＊*]+', '', line)
                _stripped = re.sub(r'[\s　「」（）()【】「」・./※＊*]+$', '', _stripped)
                matched = _stripped == label_parts[0]
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


# IFRS / JGAAP synonyms for major indicators (連結経営指標等の推移)
# Order matters: try IFRS labels FIRST (preferred for companies that adopted IFRS),
# then JGAAP. Stop at first match. This ensures IFRS-primary companies (e.g. 野村総合研究所
# 2022年以降) get values from 売上収益 column, not historical 売上高 column.
MAJOR_SPECS: dict[str, list[tuple[list[str], str]]] = {
    "revenue": [
        (["売上収益"], "売上収益（IFRS）"),
        (["営業収益"], "営業収益"),
        (["売上高"], "売上高"),
    ],
    "operating_income": [
        (["営業利益"], "営業利益"),
    ],
    "ordinary_income": [
        (["税引前利益"], "税引前利益（IFRS）"),
        (["税引前当期利益"], "税引前当期利益（IFRS）"),
        (["経常利益"], "経常利益"),
    ],
    "net_income": [
        (["親会社の所有者に帰属する", "当期利益"], "親会社の所有者に帰属する当期利益（IFRS）"),
        (["親会社株主に帰属する", "当期純利益"], "親会社株主に帰属する当期純利益"),
        (["当期純利益"], "当期純利益"),
    ],
    "net_assets": [
        (["親会社の所有者に帰属する持分合計"], "親会社の所有者に帰属する持分合計（IFRS）"),
        (["親会社の所有者に帰属する", "持分"], "親会社の所有者に帰属する持分（IFRS）"),
        (["資本合計"], "資本合計（IFRS）"),
        (["純資産額"], "純資産額"),
        (["純資産"], "純資産"),
    ],
    "total_assets": [
        (["資産合計"], "資産合計"),
        (["総資産額"], "総資産額"),
        (["総資産"], "総資産"),
    ],
    "operating_cash_flow": [
        (["営業活動による", "キャッシュ・フロー"], "営業活動によるキャッシュ・フロー"),
    ],
    "investing_cash_flow": [
        (["投資活動による", "キャッシュ・フロー"], "投資活動によるキャッシュ・フロー"),
    ],
    "financing_cash_flow": [
        (["財務活動による", "キャッシュ・フロー"], "財務活動によるキャッシュ・フロー"),
    ],
    "employees": [
        (["従業員数"], "従業員数"),
    ],
}


def find_first_section(pages: list[PageText], starts: list[str], ends: list[str] | None, window: int = 4) -> list[PageText]:
    """Try multiple section start/end heading combinations; return first non-empty match."""
    for start in starts:
        end_candidates = ends if ends else [None]
        for end in end_candidates:
            sec = find_section_pages(pages, start, end, window=window)
            if sec:
                return sec
    return []


def find_statement_section(
    pages: list[PageText],
    starts: list[str],
    confirm_anchors: list[str],
    ends: list[str] | None = None,
    window: int = 4,
    min_confirms: int = 2,
) -> list[PageText]:
    """Locate an actual financial-statement section, robust to stray heading mentions.

    ``find_first_section`` takes the first page that merely *mentions* a heading,
    which is easily fooled: a 有価証券報告書 name-drops 「連結貸借対照表」 in its
    table of contents and in narrative sections (事業等のリスク, MD&A) dozens of
    pages before the real statement. We instead require the candidate window to
    actually contain the statement's characteristic total rows (``confirm_anchors``,
    e.g. 流動資産合計 / 資産合計 for the B/S).

    We score *every* heading occurrence by how many anchors its window contains
    and return the best one (earliest wins ties), rather than the first that
    merely clears ``min_confirms``. This matters in JGAAP→IFRS transition years
    (e.g. 野村総合研究所 2021), where a condensed prior-year 連結貸借対照表 carries
    資産合計 + 負債合計 (2 anchors) but lacks the 流動資産合計 subtotal — the real
    IFRS 連結財政状態計算書 later in the document scores all 4 anchors and must win.
    Falls back to ``find_first_section`` when no window clears ``min_confirms``.
    """
    best: list[PageText] | None = None
    best_score = min_confirms - 1
    for start in starts:
        for index, page in enumerate(pages):
            if start not in page.text:
                continue
            end_index = min(len(pages), index + window)
            if ends:
                for j in range(index + 1, min(len(pages), index + window + 3)):
                    if any(e in pages[j].text for e in ends):
                        end_index = j
                        break
            section = pages[index:end_index]
            blob = "".join(p.text for p in section)
            confirms = sum(1 for a in confirm_anchors if a in blob)
            if confirms > best_score:
                best_score = confirms
                best = section
                if confirms == len(confirm_anchors):
                    return section  # perfect match — can't do better
    if best is not None:
        return best
    return find_first_section(pages, starts, ends, window=window)


def extract_metrics_from_major_indicators(pages: list[PageText]) -> dict[str, ExtractedValue]:
    # The 連結 indicators section. Search includes both the IFRS table and the JGAAP
    # historical table (both are 連結, not 提出会社). The synonym list controls which
    # accounting standard's value is preferred when both are present.
    section_pages = find_section_pages(pages, "連結経営指標等", "(2) 提出会社", window=3)
    source = "主要な経営指標等の推移"
    extracted: dict[str, ExtractedValue] = {}
    for key, alternatives in MAJOR_SPECS.items():
        for parts, label in alternatives:
            value = extract_row_from_pages(section_pages, parts, label, source)
            if value is not None:
                extracted[key] = value
                break
    return extracted


def extract_metrics_from_statements(pages: list[PageText]) -> dict[str, ExtractedValue]:
    # Balance sheet: 連結貸借対照表 (JGAAP) or 連結財政状態計算書 (IFRS).
    # Confirm anchors are the section's total rows, so a stray 「連結貸借対照表」
    # mention in the TOC / narrative (which precedes the real statement by dozens
    # of pages, e.g. 野村総合研究所) cannot hijack the locator.
    bs_pages = find_statement_section(
        pages,
        ["連結財政状態計算書", "連結貸借対照表"],
        ["流動資産合計", "資産合計", "負債合計", "流動負債合計"],
        ["連結損益計算書", "連結損益及び包括利益計算書", "連結包括利益計算書"],
        window=4,
    )
    # P/L: 連結損益計算書 (JGAAP) or 連結損益及び包括利益計算書 (IFRS combined)
    pl_pages = find_statement_section(
        pages,
        ["連結損益及び包括利益計算書", "連結損益計算書"],
        ["営業利益", "営業損失", "税引前", "経常利益", "売上原価"],
        ["連結包括利益計算書", "連結キャッシュ・フロー計算書", "連結株主資本等変動計算書"],
        window=4,
    )
    cf_pages = find_statement_section(
        pages,
        ["連結キャッシュ・フロー計算書", "連結キャッシュ・フロー"],
        ["営業活動による", "投資活動による", "財務活動による"],
        ["注記事項", "連結附属明細表"],
        window=4,
    )

    # Each metric: list of (parts, label) alternatives. First match wins.
    bs_specs: dict[str, list[tuple[list[str], str]]] = {
        "current_assets": [(["流動資産合計"], "流動資産合計")],
        "total_assets": [(["資産合計"], "資産合計")],
        "current_liabilities": [(["流動負債合計"], "流動負債合計")],
        "net_assets": [
            (["資本合計"], "資本合計（IFRS）"),
            (["純資産合計"], "純資産合計"),
        ],
    }
    pl_specs: dict[str, list[tuple[list[str], str]]] = {
        "revenue": [
            (["売上収益"], "売上収益（IFRS）"),
            (["営業収益"], "営業収益"),
            (["売上高"], "売上高"),
        ],
        "gross_profit": [(["売上総利益"], "売上総利益")],
        "operating_income": [(["営業利益"], "営業利益")],
        "ordinary_income": [
            (["税引前利益"], "税引前利益（IFRS）"),
            (["税引前当期利益"], "税引前当期利益（IFRS）"),
            (["経常利益"], "経常利益"),
        ],
        "net_income": [
            (["親会社の所有者に帰属する当期利益"], "親会社の所有者に帰属する当期利益（IFRS）"),
            (["親会社株主に帰属する当期純利益"], "親会社株主に帰属する当期純利益"),
        ],
    }
    cf_specs: dict[str, list[tuple[list[str], str]]] = {
        "operating_cash_flow": [(["営業活動によるキャッシュ・フロー"], "営業活動によるキャッシュ・フロー")],
        "investing_cash_flow": [(["投資活動によるキャッシュ・フロー"], "投資活動によるキャッシュ・フロー")],
        "financing_cash_flow": [(["財務活動によるキャッシュ・フロー"], "財務活動によるキャッシュ・フロー")],
    }

    extracted: dict[str, ExtractedValue] = {}

    def _apply(specs: dict[str, list[tuple[list[str], str]]], section: list[PageText], source: str, prefer_last: bool = False) -> None:
        for key, alternatives in specs.items():
            for parts, label in alternatives:
                value = extract_row_from_pages(section, parts, label, source, exact_first_line=True, prefer_last=prefer_last)
                if value is not None:
                    extracted[key] = value
                    break

    _apply(bs_specs, bs_pages, "連結貸借対照表/連結財政状態計算書")
    _apply(pl_specs, pl_pages, "連結損益計算書")
    _apply(cf_specs, cf_pages, "連結キャッシュ・フロー計算書", prefer_last=True)
    return extracted


def detect_accounting_standard(text: str) -> str:
    """Classify the report as 'IFRS' or 'JGAAP' from document-level structure.

    Replaces the old per-metric label guess (which mistook JGAAP 資本合計 sub-totals
    for IFRS). The decisive signal is the balance-sheet name: IFRS filings use
    連結財政状態計算書, JGAAP filings use 連結貸借対照表 — the two are mutually
    exclusive in practice. When the structural marker is ambiguous we corroborate
    with IFRS-only P/L wording (売上収益, 親会社の所有者に帰属する) and explicit
    国際会計基準 / IFRS declarations.
    """
    has_ifrs_bs = "連結財政状態計算書" in text
    has_jgaap_bs = "連結貸借対照表" in text
    if has_ifrs_bs and not has_jgaap_bs:
        return "IFRS"
    if has_jgaap_bs and not has_ifrs_bs:
        return "JGAAP"
    score = 2 if has_ifrs_bs else 0
    if "売上収益" in text:
        score += 1
    if "親会社の所有者に帰属する" in text:
        score += 1
    if re.search(r"国際会計基準|IFRS(?:第|に基づ|を適用|に準拠)", text):
        score += 2
    return "IFRS" if score >= 2 else "JGAAP"


# Accounting identities used to cross-check extraction. Each returns one of
# True (holds), False (violated → suspect extraction), or None (insufficient data).
def cross_validate(metrics: dict[str, float | None]) -> tuple[list[str], int, int]:
    """Validate extracted metrics against accounting identities.

    Returns (warnings, n_applicable_checks, n_passed). A violation almost always
    means a value was mis-extracted (wrong row / wrong column), so we surface it
    to the user and let it lower confidence — silent-but-wrong is the worst
    outcome for research use.
    """
    m = metrics
    tol = 1.005  # 0.5% slack for rounding across 千円/百万円 conversions
    checks: list[tuple[str, bool | None]] = []

    def chk(name: str, ok: bool | None) -> None:
        checks.append((name, ok))

    rev = m.get("revenue")
    rev_abs = abs(rev) if rev is not None else None
    chk("営業利益 ≤ 売上高",
        None if rev_abs is None or m.get("operating_income") is None
        else abs(m["operating_income"]) <= rev_abs * tol)
    chk("売上総利益 ≤ 売上高",
        None if rev_abs is None or m.get("gross_profit") is None
        else m["gross_profit"] <= rev_abs * tol)
    chk("純資産 ≤ 総資産",
        None if m.get("total_assets") is None or m.get("net_assets") is None
        else m["net_assets"] <= m["total_assets"] * tol)
    chk("流動資産 ≤ 総資産",
        None if m.get("total_assets") is None or m.get("current_assets") is None
        else m["current_assets"] <= m["total_assets"] * tol)
    chk("流動負債 ≤ 総資産",
        None if m.get("total_assets") is None or m.get("current_liabilities") is None
        else m["current_liabilities"] <= m["total_assets"] * tol)

    warnings = [f"会計整合性チェック要確認: {name}" for name, ok in checks if ok is False]
    n_checks = sum(1 for _, ok in checks if ok is not None)
    n_passed = sum(1 for _, ok in checks if ok is True)
    return warnings, n_checks, n_passed


def extract_metrics(pages: list[PageText], default_unit: str, standard: str = "JGAAP") -> tuple[dict[str, float | None], dict[str, dict[str, Any]], list[str], float]:
    major = extract_metrics_from_major_indicators(pages)
    statements = extract_metrics_from_statements(pages)
    metrics: dict[str, float | None] = dict.fromkeys(DISPLAY_NAMES)
    sources: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    # 主要な経営指標等の推移 (MAJOR) is more robust for trend-table metrics:
    # values are always rightmost = current year, and the format is uniform across
    # JGAAP/IFRS PDFs. STATEMENTS detail is preferred only for sub-items not in MAJOR.
    PREFER_MAJOR = {
        "revenue", "ordinary_income", "net_income", "total_assets", "net_assets",
        "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "employees",
    }
    for key in DISPLAY_NAMES:
        if key in PREFER_MAJOR:
            picked = major.get(key) or statements.get(key)
            origin = "major" if major.get(key) else ("statements" if statements.get(key) else None)
        else:
            picked = statements.get(key) or major.get(key)
            origin = "statements" if statements.get(key) else ("major" if major.get(key) else None)
        if picked is None:
            continue
        metrics[key] = unit_to_million_yen(picked.value, default_unit, key)
        sources[key] = {
            "label": picked.label,
            "section": "主要な経営指標等の推移" if origin == "major" else "連結財務諸表",
            "page": picked.page,
            "raw_value": picked.value,
            "source_text": picked.source,
            # IFRS flag is now document-level (driven by detect_accounting_standard),
            # not a per-label guess — far more reliable across statement variants.
            "is_ifrs": standard == "IFRS",
        }
        notes.append(f"{DISPLAY_NAMES[key]}: {picked.value:,.0f} ({picked.source})")

    # ── Coverage of the five essential metrics ──────────────────────────────
    essentials = ["revenue", "net_income", "total_assets", "net_assets", "operating_cash_flow"]
    found = sum(1 for key in essentials if metrics.get(key) is not None)
    coverage = found / len(essentials)

    # ── Cross-validation against accounting identities ──────────────────────
    val_warnings, n_checks, n_passed = cross_validate(metrics)
    val_rate = (n_passed / n_checks) if n_checks else 1.0
    notes.extend(val_warnings)

    # Confidence blends coverage (how much we found) with validation (how much
    # of what we found is internally consistent). Pure coverage was too coarse:
    # a doc could score 1.0 while silently carrying a mis-extracted value.
    confidence = round(0.75 * coverage + 0.25 * val_rate, 2)

    if coverage < 0.8:
        notes.append("主要項目の抽出数が不足しています。抽出結果レビューでPDF本文と照合してください。")
    # gross_profit absence is expected under IFRS (expense-by-nature P/L has no
    # 売上総利益 line) — report it as N/A, not as a failed extraction.
    if metrics.get("gross_profit") is None:
        if standard == "IFRS":
            notes.append("売上総利益: IFRS（費用性質法）の損益計算書では区分表示されないため非開示。")
        else:
            notes.append("売上総利益は企業の表示形式により未抽出の場合があります。")
    return metrics, sources, notes, confidence


def parse_pdf(path: Path, doc_id: str, original_filename: str) -> FinancialDocument:
    pages, page_count = extract_pdf_pages(path)
    text = "\n".join(page.text for page in pages)
    unit = detect_unit(text)
    company_name = detect_company_name(text, original_filename)
    english_name = detect_english_name(text)
    edinet_code = detect_edinet_code(text)
    security_code = detect_security_code(text, original_filename, path, company_name, english_name)
    standard = detect_accounting_standard(text)
    metrics, metric_sources, notes, confidence = extract_metrics(pages, unit, standard)
    notes.insert(0, f"会計基準: {standard}")
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
        metric_sources=metric_sources,
        extraction_notes=notes,
        confidence=confidence,
        accounting_standard=standard,
    )
