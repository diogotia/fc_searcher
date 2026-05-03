from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings, clear_settings_caches, get_settings
from src.config_anthropic import get_anthropic_settings


def test_browser_config_defaults(monkeypatch):
    monkeypatch.delenv("ENABLE_BROWSER_SEARCH_SYNC", raising=False)
    monkeypatch.delenv("BROWSER_SEARCH_QUERY", raising=False)
    monkeypatch.delenv("BROWSER_GROUP_SCAN_LIMIT", raising=False)
    monkeypatch.delenv("BROWSER_POST_LIMIT_PER_GROUP", raising=False)
    monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
    monkeypatch.delenv("BROWSER_SEARCH_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ENABLE_AGENTIC_FACEBOOK_SYNC", raising=False)
    monkeypatch.delenv("AGENTIC_FACEBOOK_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("AGENTIC_FACEBOOK_SOURCE", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    clear_settings_caches()

    settings = get_settings()
    assert settings.enable_browser_search_sync is False
    assert settings.browser_search_query == "job"
    assert settings.browser_group_scan_limit == 20
    assert settings.browser_post_limit_per_group == 25
    assert settings.browser_headless is False
    assert settings.browser_search_timeout_seconds == 45
    assert settings.enable_agentic_facebook_sync is False
    assert settings.agentic_facebook_output_dir == "output/agentic_facebook"
    assert settings.agentic_facebook_source == "playwright_agentic"
    assert settings.browser_post_publication_year is None


def test_agentic_facebook_config_env(monkeypatch):
    monkeypatch.delenv("ENABLE_AGENTIC_FACEBOOK_SYNC", raising=False)
    monkeypatch.delenv("AGENTIC_FACEBOOK_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("AGENTIC_FACEBOOK_SOURCE", raising=False)
    monkeypatch.setenv("ENABLE_AGENTIC_FACEBOOK_SYNC", "true")
    monkeypatch.setenv("AGENTIC_FACEBOOK_OUTPUT_DIR", "  output/custom_agentic  ")
    monkeypatch.setenv("AGENTIC_FACEBOOK_SOURCE", "  custom_agentic_source  ")
    clear_settings_caches()

    settings = get_settings()
    assert settings.enable_agentic_facebook_sync is True
    assert settings.agentic_facebook_output_dir == "output/custom_agentic"
    assert settings.agentic_facebook_source == "custom_agentic_source"


def test_browser_post_publication_year_filter(monkeypatch):
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    clear_settings_caches()
    assert get_settings().browser_post_publication_year == 2026
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "auto")
    clear_settings_caches()
    y = get_settings().browser_post_publication_year
    assert isinstance(y, int) and 2020 <= y <= 2035
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    clear_settings_caches()
    assert get_settings().browser_post_publication_year is None


def test_browser_post_publication_month_requires_year(monkeypatch):
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    with pytest.raises(ValidationError):
        Settings(browser_post_publication_month=4)


def test_browser_post_publication_from_date_env(monkeypatch):
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_MONTH", "4")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_DAY", "27")
    clear_settings_caches()
    s = get_settings()
    assert s.browser_post_publication_month == 4
    assert s.browser_post_publication_day == 27
    from datetime import date

    from src.services.browser_search import browser_publication_cutoff_date

    assert browser_publication_cutoff_date(s) == date(2026, 4, 27)


def test_facebook_ui_creation_year_filter_base64_matches_web_sample():
    from src.services.browser_search import encode_facebook_group_search_creation_year_filter

    expected = (
        "eyJycF9jcmVhdGlvbl90aW1lOjAiOiJ7XCJuYW1lXCI6XCJjcmVhdGlvbl90aW1lXCIsXCJhcmdzXCI6XCJ7XFxcInN0YXJ0X3llYXJcXFwiOlxcXCIyMDI2XFxcIixcXFwic3RhcnRfbW9udGhcXFwiOlxcXCIyMDI2LTFcXFwiLFxcXCJlbmRfeWVhclxcXCI6XFxcIjIwMjZcXFwiLFxcXCJlbmRfbW9udGhcXFwiOlxcXCIyMDI2LTEyXFxcIixcXFwic3RhcnRfZGF5XFxcIjpcXFwiMjAyNi0xLTFcXFwiLFxcXCJlbmRfZGF5XFxcIjpcXFwiMjAyNi0xMi0zMVxcXCJ9XCJ9In0="
    ).rstrip("=")
    assert encode_facebook_group_search_creation_year_filter(2026).rstrip("=") == expected


def test_build_in_group_phrases_exact_keywords():
    from src.services.browser_search import build_in_group_phrases_for_settings

    exact = build_in_group_phrases_for_settings(
        "ищу работу в Германии",
        in_group_query="Бетонщик, Арматурщик",
        settings_in_group="",
        exact_keywords=True,
    )
    assert exact == ["Бетонщик", "Арматурщик"]
    prefixed = build_in_group_phrases_for_settings(
        "ищу работу в Германии",
        in_group_query="Бетонщик, Арматурщик",
        settings_in_group="",
        exact_keywords=False,
    )
    assert prefixed == [
        "ищу работу в Германии Бетонщик",
        "ищу работу в Германии Арматурщик",
    ]


def test_anthropic_settings_separate_from_main_settings(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    clear_settings_caches()
    s = get_settings()
    assert not hasattr(s, "anthropic_api_key")
    get_anthropic_settings.cache_clear()
    ai = get_anthropic_settings()
    assert ai.anthropic_api_key is None
    assert "sonnet" in ai.claude_model.lower() or "claude" in ai.claude_model.lower()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-3-opus-20240229")
    get_anthropic_settings.cache_clear()
    ai2 = get_anthropic_settings()
    assert ai2.anthropic_api_key == "test-key-anthropic"
    assert ai2.claude_model == "claude-3-opus-20240229"


def test_browser_config_clamps_limits(monkeypatch):
    monkeypatch.setenv("BROWSER_GROUP_SCAN_LIMIT", "999")
    monkeypatch.setenv("BROWSER_POST_LIMIT_PER_GROUP", "0")
    monkeypatch.setenv("BROWSER_SEARCH_TIMEOUT_SECONDS", "2")
    clear_settings_caches()

    settings = get_settings()
    assert settings.browser_group_scan_limit == 100
    assert settings.browser_post_limit_per_group == 1
    assert settings.browser_search_timeout_seconds == 10
