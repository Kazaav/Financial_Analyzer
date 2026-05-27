"""Tests for the i18n translator."""
from __future__ import annotations

from app.i18n import DEFAULT, SUPPORTED, TRANSLATIONS, translator


def test_supported_languages_have_same_keys():
    keys = set(TRANSLATIONS[DEFAULT])
    for lang in SUPPORTED:
        missing = keys - set(TRANSLATIONS[lang])
        assert not missing, f"{lang} missing keys: {missing}"


def test_translator_returns_language_specific():
    t_ja = translator("ja")
    t_en = translator("en")
    t_zh = translator("zh")
    assert t_ja("tab.overview") == "概要"
    assert t_en("tab.overview") == "Overview"
    assert t_zh("tab.overview") == "概要"  # zh also happens to use 概要


def test_translator_falls_back_to_japanese_for_unknown_lang():
    t = translator("xx")
    assert t("tab.overview") == "概要"  # falls back to ja


def test_translator_returns_key_for_unknown_string():
    t = translator("ja")
    assert t("nonexistent.key") == "nonexistent.key"


def test_translator_uses_default_when_provided():
    t = translator("ja")
    assert t("nonexistent.key", default="fallback") == "fallback"
