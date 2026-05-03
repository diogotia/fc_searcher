"""Phase 2 — Code Verification (IMPLEMENTATION_VERIFICATION / CODE_VERIFICATION).

Automates the manual grep/run checklist: CLI flags, token parsing, see-more labels,
body-keyword OR union, and sync JSON metadata fields. No live Facebook session required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXACT_POSTS_SCRIPT = _REPO_ROOT / "scripts" / "run_agentic_facebook_exact_posts.py"


def test_phase2_exact_posts_script_cli_has_in_group_exact_keywords() -> None:
    src = _EXACT_POSTS_SCRIPT.read_text(encoding="utf-8")
    assert "--in-group-exact-keywords" in src
    assert 'dest="in_group_query"' in src or "dest='in_group_query'" in src
    assert "in_group_exact_keywords=bool(args.in_group_exact_keywords)" in src
    assert "expand_see_more_before_extract=True" in src
    assert "body_keyword_union=True" in src


def test_phase2_split_in_group_query_tokens_commas() -> None:
    from src.services.browser_search import _split_in_group_query_tokens

    assert _split_in_group_query_tokens("Плотник,Столяр") == ["Плотник", "Столяр"]
    assert _split_in_group_query_tokens(" a , b ") == ["a", "b"]
    assert _split_in_group_query_tokens("x\ny,z") == ["x", "y", "z"]


def test_phase2_see_more_embedded_js_targets_meta_labels() -> None:
    from src.services import browser_search as bs

    js = bs._EXPAND_GROUP_SEARCH_SEE_MORE_JS
    assert "Ещё" in js
    assert "See more" in js
    assert "getByText" in js


def test_phase2_body_keyword_needles_union_and_or_match() -> None:
    from src.services.browser_search import (
        build_body_keyword_needles,
        post_matches_body_keyword_union,
    )

    needles = build_body_keyword_needles("ищу работу в Германии", ["Плотник", "Столяр"])
    assert "Плотник" in needles
    assert "Столяр" in needles
    assert any(n.casefold() == "ищу работу в германии" for n in needles)

    assert post_matches_body_keyword_union("Ищу Столяр работу", needles) is True
    assert post_matches_body_keyword_union("No keywords here", needles) is False
    assert post_matches_body_keyword_union("", []) is True


def test_phase2_agentic_sync_surfaces_verification_metadata(monkeypatch, tmp_path):
    """Sync JSON must expose flags documented for CODE_VERIFICATION (via stub browser result)."""
    from src.config import clear_settings_caches, get_settings
    from src.db.session import init_db, init_engine
    from src.services.agentic_facebook import sync as af

    _repo = tmp_path / "fc_searcher"
    (_repo / "src").mkdir(parents=True)
    (_repo / "src" / "config.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(_repo))
    monkeypatch.setenv("ENABLE_AGENTIC_FACEBOOK_SYNC", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{tmp_path / 'cv_meta.db'}")
    clear_settings_caches()
    init_engine(get_settings().database_url)
    init_db()

    def _fake_browser_search(_settings, **kwargs):
        return {
            "ok": True,
            "query": "job",
            "in_group_query": "2 phases: Плотник | Столяр",
            "in_group_queries": ["Плотник", "Столяр"],
            "groups_scanned": 0,
            "found_posts": 0,
            "errors": [],
            "groups": [],
            "artifacts_dir": None,
            "in_group_exact_keywords": True,
            "expand_see_more": True,
            "body_keyword_union": True,
            "body_keyword_needles_count": 3,
        }

    monkeypatch.setattr(af, "run_browser_group_search", _fake_browser_search)

    out = af.run_agentic_facebook_sync(
        get_settings(),
        query="job",
        in_group_query="Плотник,Столяр",
        in_group_exact_keywords=True,
        expand_see_more_before_extract=True,
        body_keyword_union=True,
    )

    assert out["ok"] is True
    assert out.get("in_group_exact_keywords") is True
    assert out.get("expand_see_more") is True
    assert out.get("body_keyword_union") is True
    assert out.get("body_keyword_needles_count") == 3


@pytest.mark.parametrize(
    "script_name",
    [
        "run_agentic_facebook_once.py",
        "run_agentic_facebook_exact_posts.py",
        "run_agentic_facebook_once_exact_year.py",
    ],
)
def test_phase2_entry_scripts_exist(script_name: str) -> None:
    p = _REPO_ROOT / "scripts" / script_name
    assert p.is_file(), f"missing {p}"
