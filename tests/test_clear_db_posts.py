from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

_REPO = Path(__file__).resolve().parent.parent


def _load_clear_script():
    path = _REPO / "scripts" / "clear_db_posts.py"
    spec = importlib.util.spec_from_file_location("_clear_db_posts_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_clear_db_posts_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def clear_mod(monkeypatch, tmp_path):
    db_path = tmp_path / "clear_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(_REPO))
    return _load_clear_script()


def test_clear_db_posts_counts_only(monkeypatch, clear_mod, capsys):
    from src.config import clear_settings_caches, get_settings
    from src.db.db_models import Post
    from src.db.session import get_session, init_db, init_engine

    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()
    with get_session() as s:
        s.add(Post(id="a1", group_id="g", message="m", source="playwright_browser"))
        s.add(Post(id="a2", group_id="g", message="m2", source="graph"))

    monkeypatch.setattr(sys, "argv", ["clear_db_posts.py"])
    rc = clear_mod.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "playwright_browser" in out
    assert "graph" in out
    assert "TOTAL: 2" in out


def test_clear_db_posts_execute_default_sources(monkeypatch, clear_mod, capsys):
    from src.config import clear_settings_caches, get_settings
    from src.db.db_models import Post
    from src.db.session import get_session, init_db, init_engine

    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()
    with get_session() as s:
        s.add(Post(id="p1", group_id="g", message="x", source="playwright_browser"))
        s.add(Post(id="p2", group_id="g", message="x", source="playwright_agentic"))
        s.add(Post(id="p3", group_id="g", message="x", source="graph"))

    monkeypatch.setattr(sys, "argv", ["clear_db_posts.py", "--execute", "--yes"])
    rc = clear_mod.main()
    assert rc == 0

    clear_settings_caches()
    init_engine(settings.database_url)
    with get_session() as s:
        ids = list(s.scalars(select(Post.id)))
    assert sorted(ids) == ["p3"]
