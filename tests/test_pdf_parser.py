"""Unit tests for low-level PDF parser helpers."""
from __future__ import annotations

import pytest

from app.pdf_parser import (
    PageText,
    clean_line,
    collect_values_after_label,
    cross_validate,
    detect_accounting_standard,
    detect_unit,
    find_statement_section,
    is_parenthesized_annotation,
    is_per_unit_line,
    looks_numeric_line,
    normalize_identity,
    normalize_text,
    numeric_values,
    parse_number,
)


def _page(page_no: int, text: str) -> PageText:
    """Build a PageText the way extract_pdf_pages would (cleaned lines)."""
    lines = [clean_line(ln) for ln in text.splitlines() if clean_line(ln)]
    return PageText(page=page_no, text=text, lines=lines)


class TestNormalize:
    def test_normalize_text_fullwidth(self):
        assert normalize_text("ＡＢＣ１２３") == "ABC123"

    def test_normalize_text_triangle_negative(self):
        assert normalize_text("▲100") == "△100"
        assert normalize_text("−5") == "-5"

    def test_normalize_identity_strips_suffix(self):
        assert normalize_identity("株式会社野村総合研究所") == "野村総合研究所"
        assert normalize_identity("Toyota Inc.") == "TOYOTA"

    def test_clean_line(self):
        assert clean_line("  hello   world  ") == "hello world"


class TestParseNumber:
    @pytest.mark.parametrize("token,expected", [
        ("1,234", 1234.0),
        ("△1,234", -1234.0),
        ("▲500", -500.0),
        ("-12.5", -12.5),
        ("0", 0.0),
        ("-", None),
        ("", None),
    ])
    def test_parse_number(self, token, expected):
        assert parse_number(token) == expected


class TestNumericLine:
    def test_pure_number(self):
        assert looks_numeric_line("1,234")
        assert looks_numeric_line("△500")
        assert looks_numeric_line("(750)")  # parenthesized

    def test_dash(self):
        assert looks_numeric_line("-")
        assert looks_numeric_line("－")

    def test_non_numeric(self):
        assert not looks_numeric_line("売上高")
        assert not looks_numeric_line("(百万円)")

    def test_numeric_values_extract(self):
        assert numeric_values("1,234 5,678") == [1234.0, 5678.0]
        assert numeric_values("△100") == [-100.0]

    def test_numeric_values_strips_fused_note_marker(self):
        # PyMuPDF fuses a ※N footnote marker onto the value: ※4151,639 -> 151,639
        assert numeric_values("※4151,639") == [151639.0]
        assert numeric_values("※4 151,639") == [151639.0]
        assert looks_numeric_line("※4151,639")


class TestParenthesizedAnnotation:
    """The (27)(34) sub-row vs △N negative distinction (critical for CF / employees)."""

    def test_paren_annotation(self):
        assert is_parenthesized_annotation("(27)")
        assert is_parenthesized_annotation("(2,785)")
        assert is_parenthesized_annotation("（48）")  # fullwidth

    def test_triangle_negative_is_not_annotation(self):
        assert not is_parenthesized_annotation("△21,948")
        assert not is_parenthesized_annotation("△500")

    def test_regular_number_is_not_annotation(self):
        assert not is_parenthesized_annotation("12,484")

    def test_per_unit_line(self):
        assert is_per_unit_line("1株当たり当期純利益")
        assert is_per_unit_line("基本的1株当たり純資産")
        assert not is_per_unit_line("当期純利益")


class TestDetectUnit:
    def test_million_yen_dominant(self):
        text = "主要な経営指標等の推移\n売上高 (百万円) 100,000\n営業利益 (百万円) 10,000"
        assert detect_unit(text) == "百万円"

    def test_thousand_yen_dominant(self):
        text = "主要な経営指標等の推移\n売上高 (千円) 100,000\n営業利益 (千円) 10,000"
        assert detect_unit(text) == "千円"

    def test_first_occurrence_wins(self):
        # Even if 百万円 appears later in notes, 千円 in the indicator table wins
        text = "主要な経営指標等の推移\n売上高 (千円) 50,000\n... 法人税 (百万円) 100"
        assert detect_unit(text) == "千円"


class TestCollectValuesAfterLabel:
    """Test the heuristics that distinguish primary values from annotation sub-rows."""

    def _make_lines(self, text: str) -> list[str]:
        return [clean_line(line) for line in text.strip().split("\n") if clean_line(line)]

    def test_basic_collection(self):
        lines = self._make_lines("""
        売上高
        (百万円)
        100
        200
        300
        営業利益
        """)
        # index 0 = 売上高 label
        values = collect_values_after_label(lines, 0, ["売上高"])
        assert values == [100.0, 200.0, 300.0]

    def test_stops_at_paren_annotation_row(self):
        """Employee count followed by (X) annotation values — must stop at annotation."""
        lines = self._make_lines("""
        従業員数
        (人)
        603
        1055
        (27)
        (16)
        """)
        values = collect_values_after_label(lines, 0, ["従業員数"])
        # Must stop at the first parenthesized annotation — only the regular values survive
        assert values == [603.0, 1055.0]

    def test_keeps_triangle_negatives(self):
        """Financial CF row: positive then △N — must keep all values."""
        lines = self._make_lines("""
        財務活動によるキャッシュ・フロー
        (百万円)
        12,484
        △21,948
        △27,791
        """)
        values = collect_values_after_label(lines, 0, ["財務活動による", "キャッシュ・フロー"])
        assert values == [12484.0, -21948.0, -27791.0]

    def test_multipart_label_spanning_lines(self):
        """Label split across lines: '親会社株主に帰属する当期' + '純利益'."""
        lines = self._make_lines("""
        親会社株主に帰属する当期
        純利益
        (百万円)
        12,678
        29,411
        """)
        values = collect_values_after_label(lines, 0, ["親会社株主に帰属する", "当期純利益"])
        assert values == [12678.0, 29411.0]


class TestDetectAccountingStandard:
    """Document-level JGAAP vs IFRS classification (replaces per-label guessing)."""

    def test_jgaap_balance_sheet(self):
        text = "連結貸借対照表\n資産合計\n負債合計\n純資産合計\n売上高\n経常利益"
        assert detect_accounting_standard(text) == "JGAAP"

    def test_ifrs_statement_of_financial_position(self):
        text = "連結財政状態計算書\n非流動資産\n資本合計\n売上収益\n親会社の所有者に帰属する"
        assert detect_accounting_standard(text) == "IFRS"

    def test_transition_year_prefers_ifrs_when_both_bs_present(self):
        # JGAAP→IFRS transition reports carry BOTH balance-sheet names; the IFRS
        # financial-position statement plus 売上収益 wording should win.
        text = (
            "連結貸借対照表\n（参考）前年度\n"
            "連結財政状態計算書\n売上収益\n親会社の所有者に帰属する\n国際会計基準に基づき作成"
        )
        assert detect_accounting_standard(text) == "IFRS"

    def test_plain_jgaap_without_explicit_markers(self):
        text = "連結貸借対照表\n売上高\n売上原価\n売上総利益\n営業利益\n経常利益"
        assert detect_accounting_standard(text) == "JGAAP"


class TestCrossValidate:
    """Accounting-identity checks that surface silently mis-extracted values."""

    def test_consistent_metrics_no_warnings(self):
        m = {
            "revenue": 1000.0, "operating_income": 100.0, "gross_profit": 300.0,
            "total_assets": 2000.0, "net_assets": 800.0,
            "current_assets": 900.0, "current_liabilities": 500.0,
        }
        warnings, n_checks, n_passed = cross_validate(m)
        assert warnings == []
        assert n_checks == 5
        assert n_passed == 5

    def test_operating_income_exceeding_revenue_is_flagged(self):
        m = {"revenue": 1000.0, "operating_income": 5000.0}
        warnings, n_checks, n_passed = cross_validate(m)
        assert any("営業利益" in w for w in warnings)
        assert n_passed < n_checks

    def test_net_assets_exceeding_total_assets_is_flagged(self):
        m = {"total_assets": 1000.0, "net_assets": 1500.0}
        warnings, _, _ = cross_validate(m)
        assert any("純資産" in w for w in warnings)

    def test_missing_data_yields_no_applicable_checks(self):
        warnings, n_checks, n_passed = cross_validate({"revenue": 1000.0})
        assert warnings == []
        assert n_checks == 0

    def test_negative_operating_loss_within_revenue_ok(self):
        # An operating loss (negative) must not trip the |op| ≤ revenue check
        # unless its magnitude truly exceeds revenue.
        m = {"revenue": 1000.0, "operating_income": -200.0}
        warnings, _, n_passed = cross_validate(m)
        assert warnings == []
        assert n_passed == 1


class TestFindStatementSection:
    """Anchor-confirmed section location, robust to stray heading mentions."""

    def _bs_pages(self):
        # p1: a narrative page that merely *mentions* 連結貸借対照表 (TOC/MD&A),
        # dozens of pages before the real statement — as in real 有報 (野村:
        # p24 mention vs p78 statement). Filler pages keep them beyond `window`.
        return [
            _page(1, "事業等のリスク\n連結貸借対照表 における主要な変動について述べる"),
            *[_page(n, "本文") for n in range(2, 40)],
            _page(40, "連結貸借対照表\n流動資産合計 100\n資産合計 300\n"
                      "流動負債合計 50\n負債合計 120\n純資産合計 180"),
            _page(41, "連結損益計算書\n売上高 900"),
        ]

    def test_skips_stray_mention_picks_real_statement(self):
        pages = self._bs_pages()
        sec = find_statement_section(
            pages,
            ["連結財政状態計算書", "連結貸借対照表"],
            ["流動資産合計", "資産合計", "負債合計", "流動負債合計"],
            ["連結損益計算書"],
            window=4,
        )
        assert 40 in [p.page for p in sec]
        assert 1 not in [p.page for p in sec]

    def test_prefers_window_with_more_anchors(self):
        # A condensed prior-year table (2 anchors) must lose to the full
        # statement (4 anchors) appearing later — the transition-year case.
        pages = [
            _page(1, "連結貸借対照表\n資産合計 250\n負債合計 100"),
            _page(2, "中略"),
            _page(8, "連結財政状態計算書\n流動資産合計 120\n資産合計 300\n"
                     "流動負債合計 60\n負債合計 130"),
        ]
        sec = find_statement_section(
            pages,
            ["連結財政状態計算書", "連結貸借対照表"],
            ["流動資産合計", "資産合計", "負債合計", "流動負債合計"],
            window=4,
        )
        assert 8 in [p.page for p in sec]

    def test_falls_back_when_no_anchors_present(self):
        pages = [_page(1, "連結貸借対照表\n何らかの本文")]
        sec = find_statement_section(
            pages, ["連結貸借対照表"], ["流動資産合計", "資産合計"], window=4,
        )
        # No window clears min_confirms → fall back to first heading mention.
        assert sec and sec[0].page == 1
