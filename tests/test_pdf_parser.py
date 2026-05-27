"""Unit tests for low-level PDF parser helpers."""
from __future__ import annotations

import pytest

from app.pdf_parser import (
    clean_line,
    collect_values_after_label,
    detect_unit,
    is_parenthesized_annotation,
    is_per_unit_line,
    looks_numeric_line,
    normalize_identity,
    normalize_text,
    numeric_values,
    parse_number,
)


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
