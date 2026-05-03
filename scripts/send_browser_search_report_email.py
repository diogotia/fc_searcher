#!/usr/bin/env python3
"""Email the Playwright browser-search HTML report (``report/search_<UTC>/index.html``).

This is **not** the daily DB report from ``POST /admin/report`` (CSV under ``REPORTS_DIR``).

Examples::

    cd /Users/andreidiogoti/Documents/fc_searcher
    .venv/bin/python scripts/send_browser_search_report_email.py --folder search_20260426T113551Z

    # Same, stamp only (resolves to ``report/search_<stamp>/`` under the repo):
    .venv/bin/python scripts/send_browser_search_report_email.py --stamp 20260426T113551Z

Requires ``SMTP_USER``, ``SMTP_PASSWORD``, and ``REPORT_EMAIL`` in ``.env`` (same as daily report).

To email the **newest** ``report/search_*`` without naming it, use ``scripts/last_send_browser_search_report.py --html-only``
or ``./scripts/admin_request.sh report-browser-html`` with a folder name.

For the **combined** daily CSV report JSON **plus** latest browser HTML (two emails), use
``./scripts/admin_request.sh report-browser-html-last`` or ``last_send_browser_search_report.py`` (default).
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
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--folder",
        metavar="NAME",
        help="Folder name under report/, e.g. search_20260426T113551Z",
    )
    g.add_argument(
        "--stamp",
        metavar="UTC_STAMP",
        help="UTC stamp only, e.g. 20260426T113551Z (becomes search_<stamp>)",
    )
    g.add_argument(
        "--dir",
        dest="report_dir",
        metavar="PATH",
        type=Path,
        help="Absolute path to the search_* directory containing index.html",
    )
    args = p.parse_args()

    from src.config import clear_settings_caches, get_settings  # noqa: E402
    from src.services.pipeline import send_browser_search_html_report_email  # noqa: E402

    clear_settings_caches()
    settings = get_settings()
    if args.report_dir is not None:
        out = send_browser_search_html_report_email(settings, report_dir=args.report_dir)
    elif args.folder:
        out = send_browser_search_html_report_email(settings, search_folder=args.folder)
    else:
        out = send_browser_search_html_report_email(settings, search_folder=args.stamp)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
