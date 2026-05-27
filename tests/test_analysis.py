"""Tests for analysis aggregation and derived metric calculations."""
from __future__ import annotations

from app.analysis import _sparkline_path, _yoy, summary_kpis
from app.formatting import fmt_money_compact, fmt_percent, fmt_ratio
from app.models import FinancialDocument


def _doc(year, **metrics):
    return {
        "doc": FinancialDocument(
            id="d1", filename="a.pdf", stored_path="/tmp/a.pdf",
            company_name="Test", fiscal_year=year, fiscal_period="",
            unit="百万円", page_count=10, char_count=100, text_excerpt="",
            confidence=1.0,
        ),
        "id": "d1",
        "filename": "a.pdf",
        "company_name": "Test",
        "company_key": "TEST",
        "display_code": "0000",
        "security_code": "0000",
        "edinet_code": "E12345",
        "fiscal_year": year,
        "unit": "百万円",
        "metrics": metrics,
        "derived": {},
    }


class TestYoY:
    def test_growth(self):
        assert _yoy([100, 110]) == 0.1
        assert _yoy([100, 200]) == 1.0

    def test_decline(self):
        assert _yoy([200, 100]) == -0.5

    def test_zero_base(self):
        assert _yoy([0, 100]) is None

    def test_insufficient_data(self):
        assert _yoy([100]) is None
        assert _yoy([]) is None


class TestSparklinePath:
    def test_returns_none_for_short(self):
        assert _sparkline_path([42]) is None
        assert _sparkline_path([]) is None

    def test_generates_polyline_string(self):
        path = _sparkline_path([1, 2, 3])
        # Three points, each "x,y" pair separated by space
        assert path is not None
        parts = path.split(" ")
        assert len(parts) == 3
        for part in parts:
            x, y = part.split(",")
            assert float(x) >= 0
            assert float(y) >= 0


class TestSummaryKPIs:
    def test_year_range_single(self):
        rows = [_doc(2024, revenue=100_000, net_income=10_000)]
        kpis = summary_kpis(rows)
        assert kpis["year_range"] == "2024"
        assert kpis["company_count"] == 1
        assert kpis["document_count"] == 1

    def test_year_range_multi(self):
        rows = [
            _doc(2020, revenue=100_000, net_income=10_000),
            _doc(2024, revenue=200_000, net_income=20_000),
        ]
        kpis = summary_kpis(rows)
        assert kpis["year_range"] == "2020-2024"
        assert kpis["total_revenue"] == 300_000
        assert kpis["total_net_income"] == 30_000

    def test_trend_series_and_yoy(self):
        rows = [
            _doc(2022, revenue=100, net_income=10),
            _doc(2023, revenue=110, net_income=12),
            _doc(2024, revenue=121, net_income=14),
        ]
        kpis = summary_kpis(rows)
        assert kpis["revenue_series"] == [100, 110, 121]
        assert kpis["revenue_yoy"] == (121 - 110) / 110
        assert kpis["revenue_spark"] is not None
        assert kpis["trend_years"] == [2022, 2023, 2024]


class TestFormatters:
    def test_money_compact_million(self):
        assert fmt_money_compact(80) == "80百万円"
        assert fmt_money_compact(None) == "-"

    def test_money_compact_oku(self):
        # 50,000 百万 = 500億
        assert "億" in fmt_money_compact(50_000)

    def test_money_compact_chou(self):
        # 1,500,000 百万 = 1.5兆
        assert "兆" in fmt_money_compact(1_500_000)

    def test_percent(self):
        assert fmt_percent(0.123) == "12.3%"
        assert fmt_percent(None) == "-"

    def test_ratio(self):
        assert fmt_ratio(1.234) == "1.23x"
