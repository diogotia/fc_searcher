#!/usr/bin/env python3
"""Admin API helper: sync, daily report (POST), browser HTML report email (POST), or stored-post search (GET).

Uses ADMIN_TOKEN and API_HOST from ``.env``. Daily DB+CSV email is ``report``; browser Playwright HTML is
``report-browser-html <search_folder>`` or ``report-browser-html-last [html_report_dir]`` (optional folder:
basename under ``report/``, ``report/…``, or absolute path; default newest ``report/search_*`` on disk).
In Docker, mount the repo ``report/`` directory so ``index.html`` exists inside the container.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from load_repo_env import load_dotenv_file, project_root


def _urlopen_with_retries(req: urllib.request.Request, *, timeout: int) -> str:
    last_net_err: BaseException | None = None
    for attempt in range(12):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                print(
                    "hint: 404 usually means this route is missing in the running image "
                    "(`docker compose up --force-recreate` does not rebuild). Run "
                    "`docker compose build facebook-monitor && docker compose up -d --force-recreate facebook-monitor`, "
                    "then `curl -s http://localhost:5000/health` and check "
                    "`post_admin_report_browser_html_last` is true.",
                    file=sys.stderr,
                )
            try:
                print(json.dumps(json.loads(raw), indent=2))
            except json.JSONDecodeError:
                print(raw)
            raise SystemExit(1) from exc
        except urllib.error.URLError as exc:
            last_net_err = exc
        except (TimeoutError, ConnectionResetError, BrokenPipeError) as exc:
            last_net_err = exc
        except OSError as exc:
            errn = getattr(exc, "errno", None)
            if errn not in {errno.ECONNREFUSED, errno.ECONNRESET, 54}:
                raise
            last_net_err = exc
        if attempt < 11:
            time.sleep(1.5)
            continue
        print(
            f"error: could not reach {req.full_url!r} after several tries: {last_net_err!r}",
            file=sys.stderr,
        )
        print(
            "hint: wait a few seconds after `docker compose up`, then "
            "`curl -sf http://localhost:5000/health` and run this script again.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def main() -> int:
    env_path = project_root() / ".env"
    if not load_dotenv_file(env_path):
        print(f"error: missing {env_path}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Call fc_searcher admin endpoints.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="POST /admin/sync")
    sub.add_parser("report", help="POST /admin/report (daily DB CSV, not browser HTML)")
    p_rbh = sub.add_parser(
        "report-browser-html",
        help="POST /admin/report-browser-html (email report/search_*/index.html)",
    )
    p_rbh.add_argument(
        "search_folder",
        help="e.g. search_20260426T113551Z or 20260426T113551Z (under repo report/)",
    )
    p_rbhl = sub.add_parser(
        "report-browser-html-last",
        help="POST /admin/report-browser-html-last (daily CSVs + daily_posts HTML + browser HTML email)",
    )
    p_rbhl.add_argument(
        "html_report_dir",
        nargs="?",
        default=None,
        help="Optional folder: absolute path, or basename under report/ (e.g. agentic_search_20260509T065719Z). "
        "Default: newest report/search_*.",
    )

    p_search = sub.add_parser("search", help="GET /admin/posts/search (stored posts)")
    p_search.add_argument("query", help="substring to match in post body (case-insensitive)")
    p_search.add_argument("--limit", type=int, default=50, metavar="N", help="max rows (default 50, max 200)")
    p_search.add_argument("--group-id", default=None, metavar="ID", help="optional posts.group_id filter")

    args = parser.parse_args()

    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        print("error: ADMIN_TOKEN not set in .env (or empty)", file=sys.stderr)
        return 1

    host = os.environ.get("API_HOST", "http://localhost:5000").rstrip("/")

    if args.cmd in {"sync", "report"}:
        url = f"{host}/admin/{args.cmd}"
        req = urllib.request.Request(url, method="POST", headers={"X-Admin-Token": token})
        body = _urlopen_with_retries(req, timeout=300)
    elif args.cmd == "report-browser-html-last":
        url = f"{host}/admin/report-browser-html-last"
        payload: dict[str, str] = {}
        if getattr(args, "html_report_dir", None):
            payload["html_report_dir"] = str(args.html_report_dir).strip()
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"X-Admin-Token": token, "Content-Type": "application/json"},
        )
        body = _urlopen_with_retries(req, timeout=300)
    elif args.cmd == "report-browser-html":
        url = f"{host}/admin/report-browser-html"
        payload = json.dumps({"search_folder": args.search_folder}).encode("utf-8")
        req = urllib.request.Request(
            url,
            method="POST",
            data=payload,
            headers={"X-Admin-Token": token, "Content-Type": "application/json"},
        )
        body = _urlopen_with_retries(req, timeout=120)
    else:
        assert args.cmd == "search"
        qparams: dict[str, str] = {"q": args.query, "limit": str(args.limit)}
        if args.group_id:
            qparams["group_id"] = args.group_id
        qs = urllib.parse.urlencode(qparams)
        url = f"{host}/admin/posts/search?{qs}"
        req = urllib.request.Request(url, method="GET", headers={"X-Admin-Token": token})
        body = _urlopen_with_retries(req, timeout=60)

    try:
        print(json.dumps(json.loads(body), indent=2))
    except json.JSONDecodeError:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
