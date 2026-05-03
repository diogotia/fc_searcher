from __future__ import annotations

from pathlib import Path

from src.config import clear_settings_caches, get_settings
from src.db.session import init_db, init_engine
from src.services.agentic_facebook import sync as af


def _stub_fc_repo_root(path: Path) -> None:
    (path / "src").mkdir(parents=True, exist_ok=True)
    (path / "src" / "config.py").write_text("# test stub\n", encoding="utf-8")


def _reset_db(monkeypatch, tmp_path, name: str) -> None:
    db_path = tmp_path / name
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")
    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()


def test_run_agentic_facebook_sync_disabled_returns_error(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("ENABLE_AGENTIC_FACEBOOK_SYNC", raising=False)
    _reset_db(monkeypatch, tmp_path, "agentic-disabled.db")

    out = af.run_agentic_facebook_sync(query="job")

    assert out["ok"] is False
    assert out["flow"] == "agentic_facebook"
    assert "disabled" in (out.get("error") or "")
    assert out.get("html_report_dir")
    assert "agentic_search_" in out["html_report_dir"]


def test_run_agentic_facebook_sync_upserts_with_agentic_source(monkeypatch, tmp_path):
    from sqlalchemy import select

    from src.db.db_models import Post
    from src.db.session import get_session

    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_AGENTIC_FACEBOOK_SYNC", "true")
    monkeypatch.setenv("AGENTIC_FACEBOOK_OUTPUT_DIR", "output/custom_agentic")
    monkeypatch.setenv("AGENTIC_FACEBOOK_SOURCE", "test_agentic_source")
    _reset_db(monkeypatch, tmp_path, "agentic-upsert.db")
    seen: dict[str, object] = {}

    def _fake_browser_search(_settings, **kwargs):
        seen.update(kwargs)
        return {
            "ok": True,
            "query": kwargs.get("query") or "job",
            "in_group_query": "job Berlin",
            "in_group_queries": ["job Berlin"],
            "groups_scanned": 1,
            "found_posts": 1,
            "errors": [],
            "groups": [
                {
                    "group_name": "Group A",
                    "group_id": "111",
                    "group_url": "https://www.facebook.com/groups/111",
                    "posts": [
                        {
                            "id": "agentic_post_1",
                            "group_id": "111",
                            "message": "Agentic job opening in Berlin",
                            "author_id": None,
                            "author_name": "Recruiter",
                            "created_time": None,
                            "raw_json": {"source_type": "playwright_agentic"},
                        }
                    ],
                }
            ],
            "artifacts_dir": "output/custom_agentic/test",
        }

    monkeypatch.setattr(af, "run_browser_group_search", _fake_browser_search)

    out = af.run_agentic_facebook_sync(
        query="job",
        in_group_query="Berlin",
        seed_group_urls="https://www.facebook.com/groups/111/",
    )

    assert out["ok"] is True
    assert out["flow"] == "agentic_facebook"
    assert out["source"] == "test_agentic_source"
    assert out["upserted"] == 1
    assert out["groups_with_hits"] == 1
    assert out.get("html_report_dir")
    assert seen["output_base_dir"] == Path("output/custom_agentic")
    seed_groups = seen["seed_groups"]
    assert len(seed_groups) == 1
    assert seed_groups[0].group_url == "https://www.facebook.com/groups/111"

    with get_session() as session:
        post = session.scalar(select(Post).where(Post.id == "agentic_post_1"))
        assert post is not None
        assert post.source == "test_agentic_source"


def test_run_agentic_facebook_sync_forwards_expand_and_body_keyword_union(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_AGENTIC_FACEBOOK_SYNC", "true")
    monkeypatch.setenv("AGENTIC_FACEBOOK_OUTPUT_DIR", "output/custom_agentic")
    _reset_db(monkeypatch, tmp_path, "agentic-kwargs.db")
    seen: dict[str, object] = {}

    def _fake_browser_search(_settings, **kwargs):
        seen.update(kwargs)
        return {
            "ok": True,
            "query": "job",
            "in_group_query": "a",
            "in_group_queries": ["a"],
            "groups_scanned": 0,
            "found_posts": 0,
            "errors": [],
            "groups": [],
            "artifacts_dir": "out",
        }

    monkeypatch.setattr(af, "run_browser_group_search", _fake_browser_search)

    af.run_agentic_facebook_sync(
        query="job",
        expand_see_more_before_extract=True,
        body_keyword_union=True,
    )

    assert seen.get("expand_see_more_before_extract") is True
    assert seen.get("body_keyword_union") is True
