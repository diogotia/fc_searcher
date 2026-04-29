from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from src.db.session import normalize_database_url


def test_normalize_relative_sqlite_uses_base_dir(tmp_path: Path) -> None:
    out = normalize_database_url("sqlite:///./data/facebook_monitor.db", base_dir=tmp_path)
    assert make_url(out).database == str((tmp_path / "data" / "facebook_monitor.db").resolve())


@pytest.mark.skipif(Path("/app").exists(), reason="host has /app; Docker remap rule not applied")
def test_normalize_docker_app_path_rewrites_to_repo_data(tmp_path: Path) -> None:
    out = normalize_database_url("sqlite:////app/data/facebook_monitor.db", base_dir=tmp_path)
    assert make_url(out).database == str((tmp_path / "data" / "facebook_monitor.db").resolve())


def test_normalize_absolute_sqlite_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "custom.db"
    url = f"sqlite:///{db}"
    assert normalize_database_url(url, base_dir=tmp_path) == url


def test_normalize_three_slash_unix_absolute_not_joined_to_base(tmp_path: Path) -> None:
    """``sqlite:///Users/...`` (three slashes) must not become ``<cwd>/Users/...``."""
    out = normalize_database_url(
        "sqlite:///Users/andreidiogoti/Documents/fc_searcher/data/facebook_monitor.db",
        base_dir=tmp_path,
    )
    assert make_url(out).database == "/Users/andreidiogoti/Documents/fc_searcher/data/facebook_monitor.db"


def test_normalize_ignores_invalid_fc_searcher_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Wrong ``FC_SEARCHER_REPO_ROOT`` must not break ``sqlite:///./data/...`` when cwd is the real repo."""
    good = tmp_path / "fc_searcher"
    (good / "src").mkdir(parents=True)
    (good / "src" / "config.py").write_text("#", encoding="utf-8")
    (good / "data").mkdir()
    bad = tmp_path / "not_a_repo"
    bad.mkdir()
    monkeypatch.chdir(good)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(bad))
    caplog.set_level(logging.WARNING)
    out = normalize_database_url("sqlite:///./data/facebook_monitor.db")
    assert make_url(out).database == str((good / "data" / "facebook_monitor.db").resolve())
    assert "FC_SEARCHER_REPO_ROOT" in caplog.text


def test_normalize_dot_slash_users_path_not_joined_to_base(tmp_path: Path) -> None:
    """``sqlite:///./Users/...`` must not become ``<base>/Users/...`` (double path)."""
    out = normalize_database_url(
        "sqlite:///./Users/andreidiogoti/Documents/fc_searcher/data/facebook_monitor.db",
        base_dir=tmp_path,
    )
    assert make_url(out).database == "/Users/andreidiogoti/Documents/fc_searcher/data/facebook_monitor.db"
