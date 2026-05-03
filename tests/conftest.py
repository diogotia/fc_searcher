from __future__ import annotations

import os

import pytest

# Do not load the repo `.env` during tests (avoids real Graph calls and leaked tokens).
os.environ.setdefault("RUNNING_PYTEST", "1")


def _create_test_app(tmp_path, monkeypatch, *, public_search: bool) -> object:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("WEBHOOK_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "super-secret-app")
    monkeypatch.delenv("FACEBOOK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FACEBOOK_GROUP_IDS", raising=False)
    monkeypatch.delenv("FACEBOOK_MOCK_FEED_JSON", raising=False)
    monkeypatch.delenv("FACEBOOK_SYNC_MODE", raising=False)
    monkeypatch.delenv("ENABLE_BROWSER_SEARCH_SYNC", raising=False)
    monkeypatch.delenv("ENABLE_AGENTIC_FACEBOOK_SYNC", raising=False)
    monkeypatch.delenv("BROWSER_SEED_GROUP_URLS", raising=False)
    if public_search:
        monkeypatch.setenv("ENABLE_PUBLIC_POST_SEARCH", "true")
    else:
        monkeypatch.delenv("ENABLE_PUBLIC_POST_SEARCH", raising=False)
    from src.main import create_app

    return create_app()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    return _create_test_app(tmp_path, monkeypatch, public_search=False)


@pytest.fixture()
def app_public_search(tmp_path, monkeypatch):
    return _create_test_app(tmp_path, monkeypatch, public_search=True)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def client_public_search(app_public_search):
    return app_public_search.test_client()
