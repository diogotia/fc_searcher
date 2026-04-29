from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


def test_browser_config_defaults(monkeypatch):
    monkeypatch.delenv("ENABLE_BROWSER_SEARCH_SYNC", raising=False)
    monkeypatch.delenv("BROWSER_SEARCH_QUERY", raising=False)
    monkeypatch.delenv("BROWSER_GROUP_SCAN_LIMIT", raising=False)
    monkeypatch.delenv("BROWSER_POST_LIMIT_PER_GROUP", raising=False)
    monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
    monkeypatch.delenv("BROWSER_SEARCH_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.enable_browser_search_sync is False
    assert settings.browser_search_query == "job"
    assert settings.browser_group_scan_limit == 20
    assert settings.browser_post_limit_per_group == 25
    assert settings.browser_headless is False
    assert settings.browser_search_timeout_seconds == 45
    assert settings.browser_post_publication_year is None


def test_browser_post_publication_year_filter(monkeypatch):
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    get_settings.cache_clear()
    assert get_settings().browser_post_publication_year == 2026
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "auto")
    get_settings.cache_clear()
    y = get_settings().browser_post_publication_year
    assert isinstance(y, int) and 2020 <= y <= 2035
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    get_settings.cache_clear()
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
    get_settings.cache_clear()
    s = get_settings()
    assert s.browser_post_publication_month == 4
    assert s.browser_post_publication_day == 27
    from datetime import date

    from src.services.browser_search import browser_publication_cutoff_date

    assert browser_publication_cutoff_date(s) == date(2026, 4, 27)


def test_browser_config_clamps_limits(monkeypatch):
    monkeypatch.setenv("BROWSER_GROUP_SCAN_LIMIT", "999")
    monkeypatch.setenv("BROWSER_POST_LIMIT_PER_GROUP", "0")
    monkeypatch.setenv("BROWSER_SEARCH_TIMEOUT_SECONDS", "2")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.browser_group_scan_limit == 100
    assert settings.browser_post_limit_per_group == 1
    assert settings.browser_search_timeout_seconds == 10
