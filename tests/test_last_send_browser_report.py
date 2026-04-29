from __future__ import annotations

import sys
import time
from pathlib import Path


def test_find_latest_browser_search_report_dir_by_mtime(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "config.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))

    (tmp_path / "report" / "search_aaa").mkdir(parents=True)
    (tmp_path / "report" / "search_aaa" / "index.html").write_text("old", encoding="utf-8")
    time.sleep(0.03)
    (tmp_path / "report" / "search_bbb").mkdir(parents=True)
    (tmp_path / "report" / "search_bbb" / "index.html").write_text("new", encoding="utf-8")

    from src.services.pipeline import find_latest_browser_search_report_dir

    assert find_latest_browser_search_report_dir().name == "search_bbb"
