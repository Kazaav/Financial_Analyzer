"""Shared fixtures: isolated temporary storage + SQLite DB so tests never touch
real data. Env vars are set at MODULE import time (conftest is imported before
test collection) so settings/db/bootstrap pick them up when app.main is imported.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("FINANCIAL_ANALYZER_STORAGE", tempfile.mkdtemp(prefix="fa-test-"))
os.environ.setdefault("FINANCIAL_ANALYZER_RETENTION_DAYS", "0")  # disable cleanup
# Seed admin (password: "guest001") into the test DB via bootstrap_users().
os.environ.setdefault(
    "FINANCIAL_ANALYZER_USERS",
    "admin:admin:pbkdf2_sha256$260000$Bq6yIdC4_juvg3WXxQ28kQ$n5bwTefDHY6xtGrr5k9po5ILPdvM_kSRoMlq9nynIcA",
)
os.environ.setdefault("FINANCIAL_ANALYZER_SESSION_SECRET", "test-secret-for-pytest")


@pytest.fixture
def storage_dir() -> Path:
    return Path(os.environ["FINANCIAL_ANALYZER_STORAGE"])


@pytest.fixture(autouse=True)
def _clear_ratelimit():
    """Keep auth-endpoint rate limits from bleeding across tests."""
    from app import ratelimit

    ratelimit.clear()
    yield
