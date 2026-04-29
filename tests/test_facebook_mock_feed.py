from __future__ import annotations

from pathlib import Path

from src.config import get_settings
from src.services.facebook_client import FacebookClient


def test_mock_feed_loads_and_prefixes_ids(monkeypatch, tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample_group_feed.json"
    monkeypatch.setenv("FACEBOOK_MOCK_FEED_JSON", str(fixture))
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    settings = get_settings()
    client = FacebookClient(settings)
    out = client.fetch_group_feed_with_diagnostics("999", limit=10)
    assert out["http_status"] == 200
    assert out["error"] is None
    assert len(out["posts"]) == 2
    assert out["posts"][0]["id"] == "999_dev_post_1"
    assert out["posts"][0]["group_id"] == "999"
    assert "Berlin" in (out["posts"][0].get("message") or "")


def test_mock_feed_keyword_search(monkeypatch):
    fixture = Path(__file__).resolve().parent / "fixtures" / "sample_group_feed.json"
    monkeypatch.setenv("FACEBOOK_MOCK_FEED_JSON", str(fixture))
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    settings = get_settings()
    client = FacebookClient(settings)
    hits = client.search_group_feed_keyword("999", "Berlin", max_posts_scan=50)
    assert len(hits) == 1
    assert hits[0]["matched_keyword"] == "Berlin"
