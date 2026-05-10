#!/usr/bin/env python3
"""Send the **daily database report** plus the **latest** Playwright HTML (same idea as ``report-browser-html-last``).

By default runs :func:`run_daily_report_with_latest_browser_html_email` — same JSON shape as
``POST /admin/report`` (``csv``, ``rows``, ``run_stamp``, ``publication_*``, …) and sends **one**
email whose attachments include the daily CSV (and contact CSVs when present), a
``daily_posts_<run_stamp>.html`` file (same rows as the CSV), plus the newest
``report/search_*/index.html`` as ``browser_search_<search_stamp>_daily_<run_stamp>.html``.

Use ``--html-only`` to only email the latest browser HTML (no daily CSV / Claude / DB report email).

Examples::

    .venv/bin/python scripts/last_send_browser_search_report.py
    .venv/bin/python scripts/last_send_browser_search_report.py --html-only
    .venv/bin/python scripts/last_send_browser_search_report.py --print-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent
os.environ.setdefault("FC_SEARCHER_REPO_ROOT", str(_REPO))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from load_repo_env import load_dotenv_file  # noqa: E402


def main() -> int:
    env_path = _REPO / ".env"
    if not load_dotenv_file(env_path):
        print(f"error: missing {env_path}", file=sys.stderr)
        return 1

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--print-only",
        action="store_true",
        help="print latest report/search_* path and exit (no email, no daily run)",
    )
    p.add_argument(
        "--html-only",
        action="store_true",
        help="only email latest browser HTML (skip daily DB report)",
    )
    p.add_argument(
        "--browser-html-dir",
        default=None,
        metavar="PATH",
        help="with default mode: attach this report folder's index.html (basename under report/ or absolute), "
        "instead of newest report/search_*",
    )
    args = p.parse_args()

    from src.config import clear_settings_caches, get_settings  # noqa: E402
    from src.db.session import init_db, init_engine  # noqa: E402
    from src.services.pipeline import (  # noqa: E402
        find_latest_browser_search_report_dir,
        run_daily_report_with_latest_browser_html_email,
        send_browser_search_html_report_email,
    )

    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()

    if args.print_only:
        try:
            print(str(find_latest_browser_search_report_dir()))
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.html_only:
        try:
            folder = find_latest_browser_search_report_dir()
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        out = send_browser_search_html_report_email(settings, report_dir=folder)
    else:
        opt = str(args.browser_html_dir).strip() if args.browser_html_dir else None
        out = run_daily_report_with_latest_browser_html_email(
            settings,
            browser_html_report_dir=opt or None,
        )

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
