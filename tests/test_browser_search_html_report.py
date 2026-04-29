from __future__ import annotations

from pathlib import Path

import pytest

from src.services import browser_search_html_report as rep


def test_write_browser_search_html_report_creates_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rep, "_repo_base_dir", lambda: tmp_path)
    browse = {
        "groups": [
            {
                "group_name": "G1",
                "group_url": "https://www.facebook.com/groups/1",
                "posts": [
                    {
                        "id": "p1",
                        "author_name": "A & B",
                        "message": "Hello <world>",
                        "raw_json": {"post_url": "https://www.facebook.com/groups/1/posts/p1"},
                    }
                ],
            }
        ]
    }
    sync = {
        "ok": True,
        "query": "q1",
        "in_group_query": "q2",
        "groups_scanned": 1,
        "groups_with_hits": 1,
        "found_posts": 1,
        "upserted": 1,
        "errors": [],
        "artifacts_dir": "/tmp/art",
    }
    out_dir = rep.write_browser_search_html_report(browse_result=browse, sync_summary=sync)
    assert out_dir is not None
    assert out_dir.parent.name == "report"
    assert out_dir.name.startswith("search_")
    html_path = out_dir / "index.html"
    assert html_path.is_file()
    text = html_path.read_text(encoding="utf-8")
    assert "Hello &lt;world&gt;" in text
    assert "A &amp; B" in text
    assert "q1" in text
