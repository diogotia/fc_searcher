"""Write a self-contained HTML summary after a browser group search (under ``report/search_<UTC>/``)."""

from __future__ import annotations

import html
import json
from src.logging_config import get_logger
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db.session import _repo_base_dir

logger = get_logger(__name__)

_MAX_MSG_LEN = 4000


def _utc_folder_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def write_browser_search_html_report(
    *,
    browse_result: dict[str, Any] | None,
    sync_summary: dict[str, Any],
) -> Path | None:
    """Create ``<repo>/report/search_<UTC>/index.html``. Returns the ``search_*`` directory, or None on failure."""
    repo = _repo_base_dir()
    stamp = _utc_folder_stamp()
    out_dir = (repo / "report" / f"search_{stamp}").resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create HTML report directory %s: %s", out_dir, exc)
        return None

    ok = bool(sync_summary.get("ok"))
    title = "Browser search — success" if ok else "Browser search — failed or incomplete"
    rows_html: list[str] = []
    if browse_result and browse_result.get("groups"):
        for grp in browse_result["groups"]:
            gname = html.escape(str(grp.get("group_name") or ""))
            gurl = html.escape(str(grp.get("group_url") or ""))
            posts = grp.get("posts") or []
            rows_html.append(f"<h3>{gname}</h3>")
            if gurl:
                rows_html.append(f'<p class="meta"><a href="{gurl}">{gurl}</a></p>')
            if not posts:
                rows_html.append('<p class="muted">No posts in this group for this run.</p>')
                continue
            rows_html.append("<table><thead><tr><th>Id</th><th>Author</th><th>Message</th><th>Link</th></tr></thead><tbody>")
            for p in posts:
                pid = html.escape(str(p.get("id") or ""))
                author = html.escape(str(p.get("author_name") or ""))
                msg = html.escape(_truncate(str(p.get("message") or ""), _MAX_MSG_LEN))
                raw = p.get("raw_json") if isinstance(p.get("raw_json"), dict) else {}
                post_url = ""
                if isinstance(raw, dict):
                    post_url = str(raw.get("post_url") or "") or str(
                        (raw.get("payload") or {}).get("extracted", {}).get("post_url") or ""
                    )
                link_cell = (
                    f'<a href="{html.escape(post_url, quote=True)}">open</a>' if post_url else "—"
                )
                rows_html.append(f"<tr><td class=\"mono\">{pid}</td><td>{author}</td><td class=\"msg\">{msg}</td><td>{link_cell}</td></tr>")
            rows_html.append("</tbody></table>")

    err_block = ""
    errs = sync_summary.get("errors") or []
    if errs:
        items = []
        for e in errs:
            if isinstance(e, dict):
                phrase = e.get("phrase")
                prefix = html.escape(str(e.get("group_name") or e.get("group_url") or ""))
                if phrase:
                    prefix += " [" + html.escape(str(phrase)) + "]"
                items.append(
                    "<li>"
                    + prefix
                    + ": "
                    + html.escape(str(e.get("error") or ""))
                    + "</li>"
                )
            else:
                items.append(f"<li>{html.escape(str(e))}</li>")
        err_block = "<h2>Errors</h2><ul>" + "".join(items) + "</ul>"

    phases = sync_summary.get("in_group_queries")
    if isinstance(phases, list) and phases:
        ig_cell = " · ".join(str(p) for p in phases)
        ig_label = (
            "In-group queries (phases, one browser session)"
            if len(phases) > 1
            else "In-group query"
        )
    else:
        ig_label = "In-group query"
        ig_cell = str(sync_summary.get("in_group_query") or "")
    if len(ig_cell) > 1800:
        ig_cell = ig_cell[:1799] + "…"

    gmc_row: tuple[str, str] | None = None
    gmc_val = sync_summary.get("global_message_contains")
    if gmc_val:
        gmc_row = ("Message must contain", str(gmc_val))

    summary_rows: list[tuple[str, str]] = [
        ("Status", "ok" if ok else "not ok"),
        ("Error", str(sync_summary.get("error") or "—")),
        ("Discover query", str(sync_summary.get("query") or "")),
        (ig_label, ig_cell),
    ]
    if gmc_row:
        summary_rows.append(gmc_row)
    pyf = sync_summary.get("publication_year_filter")
    if pyf is not None:
        summary_rows.append(("Publication year filter", str(pyf)))
    pfrom = sync_summary.get("publication_from_date")
    if pfrom:
        summary_rows.append(("Publication from date (inclusive)", str(pfrom)))
    summary_rows.extend(
        [
            ("Groups scanned", str(sync_summary.get("groups_scanned", ""))),
            ("Groups with hits", str(sync_summary.get("groups_with_hits", ""))),
            ("Posts found (browser)", str(sync_summary.get("found_posts", ""))),
            ("Posts upserted (DB)", str(sync_summary.get("upserted", ""))),
            ("Playwright artifacts", str(sync_summary.get("artifacts_dir") or "—")),
            ("HTML report folder", str(out_dir)),
        ]
    )
    summary_table = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in summary_rows
    )

    json_ld = html.escape(json.dumps(sync_summary, ensure_ascii=False, default=str, indent=2))

    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 960px; color: #1a1a1a; }}
    h1 {{ font-size: 1.25rem; }}
    h2 {{ font-size: 1.05rem; margin-top: 1.5rem; }}
    h3 {{ font-size: 1rem; margin-top: 1.25rem; color: #333; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin: 0.5rem 0 1.25rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; vertical-align: top; }}
    th {{ background: #f4f4f4; text-align: left; width: 11rem; }}
    .mono {{ font-family: ui-monospace, monospace; font-size: 0.75rem; word-break: break-all; }}
    .msg {{ white-space: pre-wrap; }}
    .meta {{ font-size: 0.85rem; margin: 0.25rem 0 0.75rem; }}
    .muted {{ color: #666; }}
    pre.raw {{ background: #f8f8f8; padding: 1rem; overflow: auto; font-size: 0.75rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Generated <span class="mono">{html.escape(stamp)}</span> (UTC)</p>
  <h2>Summary</h2>
  <table>{summary_table}</table>
  {err_block}
  <h2>Posts by group</h2>
  {"".join(rows_html) if rows_html else '<p class="muted">No group/post payload (run failed before browser extraction or no groups).</p>'}
  <h2>Machine-readable summary (JSON)</h2>
  <pre class="raw">{json_ld}</pre>
</body>
</html>
"""

    path = out_dir / "index.html"
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write HTML report %s: %s", path, exc)
        return None
    logger.info("Wrote browser search HTML report %s", path)
    return out_dir
