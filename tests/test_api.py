"""Integration tests for the FastAPI app using TestClient."""
from __future__ import annotations

import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import db
from app.analysis import METRIC_ORDER
from app.main import app
from app.models import AnalysisRecord, FinancialDocument
from app.passwords import hash_password
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

    def test_disabled_user_cannot_login(self):
        _mk_user("login_disabled")
        db.set_status("login_disabled", "disabled")
        r = TestClient(app).post("/login", data={"username": "login_disabled", "password": "pw12345678"},
                                 follow_redirects=False)
        assert r.status_code == 401


# ── helpers for multi-user tests ──────────────────────────────────────────
def _mk_user(name: str, pw: str = "pw12345678", role: str = "user") -> str:
    try:
        db.create_user(name, hash_password(pw), role=role)
    except ValueError:
        db.set_password(name, hash_password(pw))
        db.set_status(name, "active")
        db.set_role(name, role)
    return name


def _client_as(name: str, pw: str = "pw12345678") -> TestClient:
    c = TestClient(app)
    r = c.post("/login", data={"username": name, "password": pw}, follow_redirects=False)
    assert r.status_code == 303, f"login failed for {name}: {r.status_code}"
    return c


def _csrf(client: TestClient, path: str = "/app") -> str:
    html = client.get(path).text
    m = re.search(r'name="csrf_token" value="([0-9a-f]+)"', html)
    assert m, f"no csrf token found on {path}"
    return m.group(1)


def _owned_record(owner: str, rid: str | None = None) -> str:
    rid = rid or (datetime.now().strftime("%Y%m%d%H%M%S%f")[:18] + "-" + owner[:4])
    save_record(AnalysisRecord(
        id=rid, created_at="2026-01-01 00:00", owner=owner,
        documents=[FinancialDocument(
            id="d1", filename="x.pdf", stored_path="/tmp/x.pdf", company_name="Owned Corp",
            fiscal_year=2024, fiscal_period="", unit="百万円", page_count=1, char_count=1,
            text_excerpt="",
            metrics={**dict.fromkeys(METRIC_ORDER), "revenue": 1000.0, "net_income": 100.0,
                     "total_assets": 5000.0, "net_assets": 2000.0, "operating_cash_flow": 200.0},
            confidence=1.0,
        )],
    ))
    return rid


class TestRegistration:
    def test_invite_required(self):
        r = TestClient(app).post(
            "/register",
            data={"code": "nope", "username": "reg_a", "password": "pw12345678", "confirm": "pw12345678"},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert db.get_user_by_name("reg_a") is None

    def test_register_then_single_use(self):
        code = db.create_invite(role="user", created_by="admin", max_uses=1)
        r = TestClient(app).post(
            "/register",
            data={"code": code, "username": "reg_b", "password": "pw12345678", "confirm": "pw12345678"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get_user_by_name("reg_b") is not None
        r2 = TestClient(app).post(
            "/register",
            data={"code": code, "username": "reg_c", "password": "pw12345678", "confirm": "pw12345678"},
            follow_redirects=False,
        )
        assert r2.status_code == 400
        assert db.get_user_by_name("reg_c") is None

    def test_password_rules(self):
        code = db.create_invite(created_by="admin", max_uses=5)
        c = TestClient(app)
        assert c.post("/register", data={"code": code, "username": "reg_d",
                      "password": "pw12345678", "confirm": "mismatch99"}, follow_redirects=False).status_code == 400
        assert c.post("/register", data={"code": code, "username": "reg_e",
                      "password": "short", "confirm": "short"}, follow_redirects=False).status_code == 400


class TestIsolation:
    def test_user_cannot_access_others(self):
        _mk_user("iso_alice")
        _mk_user("iso_bob")
        rid = _owned_record("iso_alice")
        cb = _client_as("iso_bob")
        assert cb.get(f"/analysis/{rid}", follow_redirects=False).status_code == 404
        assert rid not in cb.get("/app").text
        ca = _client_as("iso_alice")
        assert ca.get(f"/analysis/{rid}").status_code == 200
        assert rid in ca.get("/app").text

    def test_admin_sees_all(self):
        _mk_user("iso_carol")
        rid = _owned_record("iso_carol")
        assert _client_as("admin", "guest001").get(f"/analysis/{rid}").status_code == 200

    def test_other_user_cannot_mutate(self):
        _mk_user("iso_dan")
        _mk_user("iso_erin")
        rid = _owned_record("iso_dan")
        ce = _client_as("iso_erin")
        r = ce.post(f"/analysis/{rid}/rename", data={"title": "hax", "csrf_token": _csrf(ce)},
                    follow_redirects=False)
        assert r.status_code == 404


class TestCSRF:
    def test_missing_token_rejected(self):
        _mk_user("csrf_u")
        rid = _owned_record("csrf_u")
        c = _client_as("csrf_u")
        assert c.post(f"/analysis/{rid}/rename", data={"title": "x"}, follow_redirects=False).status_code == 403
        assert c.post(f"/analysis/{rid}/rename", data={"title": "x", "csrf_token": _csrf(c)},
                      follow_redirects=False).status_code == 303


class TestAdminMgmt:
    def test_non_admin_forbidden(self):
        _mk_user("adm_user")
        assert _client_as("adm_user").get("/admin/users").status_code == 403

    def test_admin_disable_user(self):
        _mk_user("adm_target")
        c = _client_as("admin", "guest001")
        assert c.get("/admin/users").status_code == 200
        r = c.post("/admin/users/adm_target/status",
                   data={"status": "disabled", "csrf_token": _csrf(c, "/admin/users")},
                   follow_redirects=False)
        assert r.status_code == 303
        assert db.get_user_by_name("adm_target")["status"] == "disabled"

    def test_cannot_delete_last_admin(self):
        c = _client_as("admin", "guest001")
        r = c.post("/admin/users/admin/delete",
                   data={"csrf_token": _csrf(c, "/admin/users")}, follow_redirects=False)
        assert r.status_code == 400


class TestAccount:
    def test_change_password(self):
        _mk_user("acc_u", pw="oldpassword1")
        c = _client_as("acc_u", "oldpassword1")
        r = c.post("/account/password",
                   data={"current_password": "oldpassword1", "new_password": "newpassword2",
                         "confirm": "newpassword2", "csrf_token": _csrf(c, "/account")},
                   follow_redirects=False)
        assert r.status_code == 303
        assert db.authenticate("acc_u", "newpassword2")
        assert not db.authenticate("acc_u", "oldpassword1")

    def test_self_delete(self):
        _mk_user("acc_del")
        _owned_record("acc_del")
        c = _client_as("acc_del")
        r = c.post("/account/delete",
                   data={"confirm_username": "acc_del", "csrf_token": _csrf(c, "/account")},
                   follow_redirects=False)
        assert r.status_code == 303
        assert db.get_user_by_name("acc_del") is None
