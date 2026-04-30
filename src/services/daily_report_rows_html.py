"""Standalone HTML export for daily report CSV rows (same data as ``EmailReporter.write_csv``)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def write_daily_report_rows_html(
    path: Path,
    *,
    report: dict[str, Any],
    rows: list[dict[str, Any]],
    run_stamp: str,
) -> None:
    """Write a self-contained HTML document whose table rows match the daily ``report_*.csv``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    title = f"Daily posts — {report.get('date', '')} ({run_stamp})"
    meta_rows: list[tuple[str, str]] = [
        ("Run stamp", html.escape(run_stamp)),
        ("Rows", str(len(rows))),
        ("Report date", html.escape(str(report.get("date") or ""))),
    ]
    if report.get("publication_year_filter") is not None:
        meta_rows.append(("Publication year filter", html.escape(str(report["publication_year_filter"]))))
    if report.get("publication_from_date"):
        meta_rows.append(("Publication from date", html.escape(str(report["publication_from_date"]))))

    meta_html = "<table class='meta'>" + "".join(
        f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in meta_rows
    ) + "</table>"

    if not rows:
        body = "<p><em>No rows in this report window.</em></p>"
    else:
        headers = list(rows[0].keys())
        thead = "<tr>" + "".join(f"<th>{html.escape(str(h))}</th>" for h in headers) + "</tr>"
        tbody_parts: list[str] = []
        for row in rows:
            cells: list[str] = []
            for h in headers:
                val = row.get(h, "")
                s = "" if val is None else str(val)
                if h == "post_url" and s.startswith("http"):
                    disp = html.escape(s[:120]) + ("…" if len(s) > 120 else "")
                    cells.append(f'<td><a href="{html.escape(s, quote=True)}">{disp}</a></td>')
                elif h == "message" and len(s) > 4000:
                    cells.append(f"<td>{html.escape(s[:3999])}…</td>")
                else:
                    cells.append(f"<td>{html.escape(s)}</td>")
            tbody_parts.append("<tr>" + "".join(cells) + "</tr>")
        tbody = "".join(tbody_parts)
        body = f"<table class='posts'><thead>{thead}</thead><tbody>{tbody}</tbody></table>"

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
<style>
body {{ font-family: sans-serif; margin: 1rem; }}
table.meta {{ margin-bottom: 1rem; border-collapse: collapse; }}
table.meta th {{ text-align: left; padding-right: 1rem; }}
table.posts {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
table.posts th, table.posts td {{ border: 1px solid #ccc; padding: 0.35rem; vertical-align: top; }}
table.posts td {{ max-width: 28rem; word-wrap: break-word; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>Same rows as the attached daily <code>report_*.csv</code> (stored posts snapshot at generation time).</p>
{meta_html}
{body}
</body>
</html>"""
    path.write_text(doc, encoding="utf-8")
