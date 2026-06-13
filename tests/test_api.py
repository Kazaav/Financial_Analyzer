"""Integration tests for the FastAPI app using TestClient."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import AnalysisRecord, FinancialDocument
from app.storage import save_record


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def demo_record():
    """Insert a tiny demo record into the test storage."""
    record = AnalysisRecord(
        id="demo-test-fixture",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        documents=[
            FinancialDocument(
                id="abc", filename="sample.pdf", stored_path="/tmp/sample.pdf",
                company_name="Test Corp", fiscal_year=2024,
                fiscal_period="", unit="百万円", page_count=10, char_count=100,
                text_excerpt="", security_code="0001", edinet_code="E12345",
                metrics={"revenue": 100_000, "net_income": 10_000,
                         "total_assets": 200_000, "net_assets": 100_000,
                         "operating_cash_flow": 15_000},
                metric_sources={"revenue": {"label": "売上高", "section": "主要な経営指標等の推移",
                                            "page": 2, "raw_value": 100_000, "source_text": "p.2",
                                            "is_ifrs": False}},
                confidence=1.0,
            ),
        ],
    )
    save_record(record)
    return record


class TestPublicRoutes:
    def test_landing(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Financial Analyzer" in resp.text

    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True

    def test_metrics_endpoint(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # When prometheus_client is installed, body is OpenMetrics text format.
        # When not, a comment line. Either way we accept a 200 response with some bytes.
        assert resp.content

    def test_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_app_requires_login(self, client):
        # Should redirect to /login (not follow to compare)
        resp = client.get("/app", follow_redirects=False)
        assert resp.status_code == 303
        assert "/login" in resp.headers["location"]


class TestI18n:
    def test_lang_switch_sets_cookie(self, client):
        resp = client.get("/set-lang/en", follow_redirects=False)
        assert resp.status_code == 303
        assert "fa_lang=en" in resp.headers.get("set-cookie", "")

    def test_lang_switch_invalid_does_not_set(self, client):
        resp = client.get("/set-lang/xx", follow_redirects=False)
        assert "fa_lang" not in resp.headers.get("set-cookie", "")

    def test_landing_in_english(self, client):
        resp = client.get("/", cookies={"fa_lang": "en"})
        assert "Read financial data" in resp.text or "Capabilities" in resp.text

    def test_landing_in_chinese(self, client):
        resp = client.get("/", cookies={"fa_lang": "zh"})
        assert "示例分析" in resp.text or "查看示例" in resp.text


class TestDemo:
    def test_demo_route_404_on_unknown(self, client):
        resp = client.get("/demo/nonexistent")
        assert resp.status_code == 404


class TestLoginFlow:
    def test_wrong_password(self, client):
        resp = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_correct_password(self, client):
        resp = client.post("/login", data={"username": "admin", "password": "guest001"},
                           follow_redirects=False)
        assert resp.status_code == 303
        assert "financial_analyzer_session=" in resp.headers.get("set-cookie", "")
