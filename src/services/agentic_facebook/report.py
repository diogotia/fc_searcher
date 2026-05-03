"""HTML reporting for the isolated agentic Facebook flow."""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db.session import _repo_base_dir

logger = logging.getLogger(__name__)


def _utc_folder_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _truncate(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def write_agentic_facebook_html_report(
    *,
    browse_result: dict[str, Any] | None,
    sync_summary: dict[str, Any],
) -> Path | None:
    """Create ``<repo>/report/agentic_search_<UTC>/index.html`` for this flow only."""
    repo = _repo_base_dir()
    stamp = _utc_folder_stamp()
    out_dir = (repo / "report" / f"agentic_search_{stamp}").resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create agentic Facebook report directory %s: %s", out_dir, exc)
        return None

    ok = bool(sync_summary.get("ok"))
    title = "Agentic Facebook flow - success" if ok else "Agentic Facebook flow - failed or incomplete"
    group_blocks: list[str] = []
    if browse_result and browse_result.get("groups"):
        for group in browse_result["groups"]:
            group_name = html.escape(str(group.get("group_name") or ""))
            group_url = html.escape(str(group.get("group_url") or ""), quote=True)
            posts = group.get("posts") or []
            group_blocks.append(f"<h3>{group_name}</h3>")
            if group_url:
                group_blocks.append(f'<p class="meta"><a href="{group_url}">{group_url}</a></p>')
            if not posts:
                group_blocks.append('<p class="muted">No posts in this group for this run.</p>')
                continue
            group_blocks.append(
                "<table><thead><tr><th>Id</th><th>Author</th><th>Message</th><th>Link</th></tr></thead><tbody>"
            )
            for post in posts:
                raw = post.get("raw_json") if isinstance(post.get("raw_json"), dict) else {}
                post_url = ""
                if isinstance(raw, dict):
                    post_url = str(raw.get("post_url") or "") or str(
                        (raw.get("payload") or {}).get("extracted", {}).get("post_url") or ""
                    )
                link_cell = (
                    f'<a href="{html.escape(post_url, quote=True)}">open</a>' if post_url else "-"
                )
                group_blocks.append(
                    "<tr>"
                    f'<td class="mono">{html.escape(str(post.get("id") or ""))}</td>'
                    f"<td>{html.escape(str(post.get('author_name') or ''))}</td>"
                    f'<td class="msg">{html.escape(_truncate(str(post.get("message") or "")))}</td>'
                    f"<td>{link_cell}</td>"
                    "</tr>"
                )
            group_blocks.append("</tbody></table>")

    summary_rows = [
        ("Flow", str(sync_summary.get("flow") or "agentic_facebook")),
        ("Status", "ok" if ok else "not ok"),
        ("Error", str(sync_summary.get("error") or "-")),
        ("Discover query", str(sync_summary.get("query") or "")),
        ("In-group query", str(sync_summary.get("in_group_query") or "")),
        ("Groups scanned", str(sync_summary.get("groups_scanned", ""))),
        ("Groups with hits", str(sync_summary.get("groups_with_hits", ""))),
        ("Posts found", str(sync_summary.get("found_posts", ""))),
        ("Posts upserted", str(sync_summary.get("upserted", ""))),
        ("Artifacts", str(sync_summary.get("artifacts_dir") or "-")),
        ("HTML report folder", str(out_dir)),
    ]
    if sync_summary.get("in_group_queries"):
        summary_rows.insert(
            5,
            ("In-group queries", " | ".join(str(v) for v in sync_summary["in_group_queries"])),
        )
    if sync_summary.get("global_message_contains"):
        summary_rows.insert(6, ("Message must contain", str(sync_summary["global_message_contains"])))

    summary_table = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in summary_rows
    )
    json_payload = html.escape(json.dumps(sync_summary, ensure_ascii=False, default=str, indent=2))
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 960px; color: #1a1a1a; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin: 0.5rem 0 1.25rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; vertical-align: top; }}
    th {{ background: #f4f4f4; text-align: left; width: 11rem; }}
    .mono {{ font-family: ui-monospace, monospace; font-size: 0.75rem; word-break: break-all; }}
    .msg {{ white-space: pre-wrap; }}
    .meta, .muted {{ color: #666; }}
    pre.raw {{ background: #f8f8f8; padding: 1rem; overflow: auto; font-size: 0.75rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Generated <span class="mono">{html.escape(stamp)}</span> UTC</p>
  <h2>Summary</h2>
  <table>{summary_table}</table>
  <h2>Posts by group</h2>
  {"".join(group_blocks) if group_blocks else '<p class="muted">No group/post payload for this run.</p>'}
  <h2>Machine-readable summary</h2>
  <pre class="raw">{json_payload}</pre>
</body>
</html>
"""
    path = out_dir / "index.html"
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write agentic Facebook report %s: %s", path, exc)
        return None
    logger.info("Wrote agentic Facebook HTML report %s", path)
    return out_dir
