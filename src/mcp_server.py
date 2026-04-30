"""MCP stdio server exposing Facebook Monitor tools.

Run from repository root:

    python -m src.mcp_server
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.config import get_settings
from src.db.session import init_db, init_engine
from src.services.facebook_client import FacebookClient
from src.services.pipeline import run_browser_search_sync, run_daily_report, run_sync


def main() -> None:
    if os.environ.get("RUNNING_PYTEST") != "1":
        load_dotenv()
    _repo = Path(__file__).resolve().parent.parent
    os.environ.setdefault("FC_SEARCHER_REPO_ROOT", str(_repo))
    get_settings.cache_clear()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "The 'mcp' package is required for MCP mode. Install: python3 -m pip install -r requirements-mcp.txt"
        ) from exc

    mcp = FastMCP("facebook-monitor")

    @mcp.tool()
    def facebook_sync_posts() -> str:
        """Fetch latest posts from configured FACEBOOK_GROUP_IDS and upsert into the database."""
        return str(run_sync(get_settings()))

    @mcp.tool()
    def facebook_search_group_keyword(group_id: str, keyword: str) -> str:
        """Scan recent group feed posts and return those containing keyword (case-insensitive)."""
        settings = get_settings()
        if not settings.facebook_graph_ready():
            return "Error: FACEBOOK_ACCESS_TOKEN not set (or set FACEBOOK_MOCK_FEED_JSON for offline dev)"
        client = FacebookClient(settings)
        hits = client.search_group_feed_keyword(group_id, keyword)
        slim = [{"id": h["id"], "preview": (h.get("message") or "")[:240]} for h in hits]
        return str(slim)

    @mcp.tool()
    def facebook_browser_search_sync(
        query: str | None = None,
        in_group_query: str | None = None,
        in_group_queries: list[str] | None = None,
        group_limit: int | None = None,
        post_limit_per_group: int | None = None,
        seed_group_urls: str | None = None,
        global_message_contains: str | None = None,
    ) -> str:
        """Browser-driven Facebook group search; upserts rows into `posts` with source `playwright_browser`.

        Use this when **Graph** group `/feed` fails for your token (typical: HTTP **400**, code **100**,
        **error_subcode 33** — missing visibility or permissions) but you still want posts in the DB.

        **Login:** set `ENABLE_BROWSER_SEARCH_SYNC=true`, `BROWSER_HEADLESS=false`, and a large enough
        `BROWSER_SEARCH_TIMEOUT_SECONDS` (e.g. 120–300). Optional **`FACEBOOK_WEB_LOGIN`** +
        **`FACEBOOK_WEB_PASSWORD`** in `.env` trigger an automated sign-in attempt in the same browser
        session before the manual wait (2FA, checkpoints, or unusual UIs may still need you to act in
        the window). Otherwise complete Facebook login manually and wait until the tool returns.

        Optional `query` overrides `BROWSER_SEARCH_QUERY` for **global** group discovery
        (`/search/groups/?q=`). Optional **`in_group_query`** overrides `BROWSER_IN_GROUP_SEARCH_QUERY`
        (comma-separated tokens; each phase uses ``query + " " + token``). When omitted, env / `query` applies.

        Optional **`in_group_queries`**: ordered list of in-group search strings run in the **same**
        browser session after one login (one discovery pass, then each phrase per group). When set,
        it takes precedence over a single `in_group_query`.

        Optional **`global_message_contains`**: only upsert posts whose message contains this substring
        (case-insensitive). Use with multi-phase runs to keep e.g. ``ищу работу`` as a filter across all phases.

        Optional `group_limit` / `post_limit_per_group` override the usual caps (same as admin JSON body).
        **`group_limit`** caps only groups from **`/search/groups`**; every seed URL is still scanned.

        **`seed_group_urls`:** comma-separated `https://www.facebook.com/groups/NUMERIC_ID/...` URLs or numeric ids.
        Those groups are opened **first** and **all** are used; then up to `group_limit` groups from search results.
        You can also set `BROWSER_SEED_GROUP_URLS` in `.env` for the same effect across runs.
        """
        return str(
            run_browser_search_sync(
                get_settings(),
                query=query,
                in_group_query=in_group_query,
                in_group_queries=in_group_queries,
                group_limit=group_limit,
                post_limit_per_group=post_limit_per_group,
                seed_group_urls=seed_group_urls,
                global_message_contains=global_message_contains,
            )
        )

    @mcp.tool()
    def facebook_send_daily_report() -> str:
        """Build CSV/HTML report, run optional Claude analysis, and email via SMTP."""
        return str(run_daily_report(get_settings()))

    _settings = get_settings()
    init_engine(_settings.database_url)
    init_db()

    mcp.run()


if __name__ == "__main__":
    main()
