"""Shared fixtures: isolated temporary storage so tests don't touch real data."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_storage(tmp_path_factory):
    """Point FINANCIAL_ANALYZER_STORAGE at a temp dir BEFORE app modules import settings."""
    store = tmp_path_factory.mktemp("fa-storage")
    os.environ["FINANCIAL_ANALYZER_STORAGE"] = str(store)
    os.environ["FINANCIAL_ANALYZER_RETENTION_DAYS"] = "0"  # disable cleanup
    os.environ.setdefault("FINANCIAL_ANALYZER_USERS",
                          "admin:admin:pbkdf2_sha256$260000$Bq6yIdC4_juvg3WXxQ28kQ$n5bwTefDHY6xtGrr5k9po5ILPdvM_kSRoMlq9nynIcA")
    os.environ.setdefault("FINANCIAL_ANALYZER_SESSION_SECRET", "test-secret-for-pytest")
    yield store


@pytest.fixture
def storage_dir() -> Path:
    return Path(os.environ["FINANCIAL_ANALYZER_STORAGE"])
