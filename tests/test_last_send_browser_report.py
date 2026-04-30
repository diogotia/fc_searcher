from __future__ import annotations

import os
import time
from pathlib import Path


def test_find_latest_browser_search_report_dir_by_folder_name_not_mtime(tmp_path: Path, monkeypatch) -> None:
    """Newer UTC stamp in the folder name wins even if an older folder's index.html has newer mtime."""
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "config.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))

    old = tmp_path / "report" / "search_20260429T125554Z"
    new = tmp_path / "report" / "search_20260429T130952Z"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "index.html").write_text("<html>old run</html>", encoding="utf-8")
    (new / "index.html").write_text("<html>new run</html>", encoding="utf-8")

    # Bump mtime on the *older* stamp's file so mtime-based logic would wrongly pick it.
    time.sleep(0.05)
    os.utime(old / "index.html", None)

    from src.services.pipeline import find_latest_browser_search_report_dir

    assert find_latest_browser_search_report_dir().name == "search_20260429T130952Z"
