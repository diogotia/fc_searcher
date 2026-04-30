from __future__ import annotations

from pathlib import Path

from src.services.daily_report_rows_html import write_daily_report_rows_html


def test_write_daily_report_rows_html_empty(tmp_path: Path) -> None:
    p = tmp_path / "daily.html"
    write_daily_report_rows_html(
        p,
        report={"date": "2026-04-29", "publication_year_filter": 2026},
        rows=[],
        run_stamp="20260429T120000Z",
    )
    text = p.read_text(encoding="utf-8")
    assert "No rows" in text
    assert "20260429T120000Z" in text


def test_write_daily_report_rows_html_one_row(tmp_path: Path) -> None:
    p = tmp_path / "daily.html"
    rows = [
        {
            "id": "p1",
            "group_id": "999",
            "author_name": "A",
            "created_time": "2026-04-29T10:00:00+00:00",
            "post_url": "https://example.com/x",
            "phones": "",
            "emails": "",
            "message": "hello",
            "source": "playwright_browser",
        }
    ]
    write_daily_report_rows_html(
        p,
        report={"date": "2026-04-29"},
        rows=rows,
        run_stamp="20260429T120000Z",
    )
    text = p.read_text(encoding="utf-8")
    assert "playwright_browser" in text
    assert "https://example.com/x" in text
    assert "hello" in text
