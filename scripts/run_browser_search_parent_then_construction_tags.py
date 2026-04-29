#!/usr/bin/env python3
"""Parent in-group search plus construction niche phrases in **one** Playwright session.

Runs ``run_browser_search_sync`` once with multiple **in-group** phases (same browser login,
same group discovery ``--query``). Construction entries use word phrases derived from tags
(``#рабочий_строительства`` → ``рабочий строительства``) for Facebook search.

Example::

    .venv/bin/python scripts/run_browser_search_parent_then_construction_tags.py \\
      --query "Работа в Германии" \\
      --in-group-query "ищу работу" \\
      --seed-group-urls "https://www.facebook.com/groups/934750153812574/" \\
      --group-limit 5 \\
      --post-limit 25 \\
      --additional-search "" \\
      --no-global-message-filter

    # **Timestamped CSVs** (``report_<date>_<UTCstamp>.csv`` and ``*_phones.csv`` / ``*_emails.csv`` under
    # ``REPORTS_DIR``, e.g. ``/app/reports``) are written by ``POST /admin/report``. Run that **before**
    # Playwright, then browser (JSON includes ``daily_report_first`` and paths in stdout)::
    .venv/bin/python scripts/run_browser_search_parent_then_construction_tags.py \\
      --query "Работа в Германии" \\
      --in-group-query "ищу работу" \\
      --seed-group-urls "https://www.facebook.com/groups/934750153812574/" \\
      --group-limit 5 \\
      --post-limit 25 \\
      --additional-search "" \\
      --no-global-message-filter \\
      --daily-report-first

    # Optional second report **after** a successful browser run (includes new upserts in CSV)::
    .venv/bin/python scripts/run_browser_search_parent_then_construction_tags.py \\
      --query "Работа в Германии" \\
      --in-group-query "ищу работу" \\
      --seed-group-urls "https://www.facebook.com/groups/934750153812574/" \\
      --group-limit 5 \\
      --post-limit 25 \\
      --additional-search "" \\
      --no-global-message-filter \\
      --daily-report-first \\
      --admin-report

    # Append more in-group phrases after the built-in construction list (comma-separated;
    # values with # or _ are normalized like built-in tags):
    .venv/bin/python scripts/run_browser_search_parent_then_construction_tags.py \\
      --query "Работа в Германии" --skip-parent \\
      --additional-search "#рабочий_строительства, демонтаж, штукатурка"

JSON stdout always includes ``additional_search`` (comma-separated string), ``additional_search_list``,
and ``additional_search_tags`` (original ``#...`` tags for the built-in set).

To email the HTML export for a given run, use ``html_report_dir`` from the JSON, e.g.::

    .venv/bin/python scripts/send_browser_search_report_email.py --folder search_20260426T113551Z

When ``--in-group-query`` is used (not ``--skip-parent``), each construction / ``--additional-search``
phase is sent to Facebook as **``<parent> <niche>``** (e.g. ``ищу работу рабочий строительства``); phase 1
stays the parent alone. Posts are also **globally** filtered: the message must contain the parent phrase
(case-insensitive) unless you pass ``--no-global-message-filter``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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


def _run_admin_daily_report(repo: Path) -> tuple[int, str, str]:
    """Run ``scripts/admin_request.sh report``. Returns (exit_code, stdout, stderr)."""
    script = repo / "scripts" / "admin_request.sh"
    proc = subprocess.run(
        [str(script), "report"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _dedupe_preserve(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        k = x.casefold().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _interpreter_ok(py: Path) -> bool:
    if not py.is_file() or not os.access(py, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [
                str(py),
                "-c",
                "import sys; assert sys.version_info >= (3, 10), 'need 3.10+'; import pydantic",
            ],
            check=False,
            capture_output=True,
            timeout=45,
        )
    except OSError:
        return False
    return proc.returncode == 0


def _try_reexec_with_suitable_python() -> None:
    if os.environ.get("FC_SEARCHER_VENV_REEXEC") == "1":
        return
    if sys.version_info >= (3, 10):
        return
    here = Path(sys.executable).resolve()
    script = Path(__file__).resolve()
    candidates = [
        _REPO / ".venv-py312/bin/python",
        _REPO / ".venv/bin/python",
        Path("/opt/homebrew/bin/python3.12"),
        Path("/usr/local/bin/python3.12"),
        Path("/opt/homebrew/bin/python3.11"),
        Path("/usr/local/bin/python3.11"),
    ]
    for cand in candidates:
        if not cand.is_file():
            continue
        rc = cand.resolve()
        if rc == here:
            continue
        if not _interpreter_ok(rc):
            continue
        os.environ["FC_SEARCHER_VENV_REEXEC"] = "1"
        os.execv(str(rc), [str(rc), str(script), *sys.argv[1:]])


def _die_py310_hint() -> None:
    print(
        "error: this project needs Python 3.10 or newer.\n"
        "  Fix: brew install python@3.12 && ./scripts/recreate_venv_for_mcp.sh\n",
        file=sys.stderr,
    )


def main() -> int:
    if sys.version_info < (3, 10):
        _die_py310_hint()
        return 2

    parser = argparse.ArgumentParser(
        description="One browser session: parent in-group phrase + construction search phases."
    )
    parser.add_argument("--query", default=None, help="Global group discovery (all phases)")
    parser.add_argument(
        "--in-group-query",
        default=None,
        dest="in_group_query",
        help="First in-group phase only (e.g. ищу работу). Skipped with --skip-parent.",
    )
    parser.add_argument("--group-limit", type=int, default=None, metavar="N")
    parser.add_argument("--post-limit", type=int, default=None, metavar="N")
    parser.add_argument(
        "--seed-group-urls",
        default=None,
        help="Comma-separated URLs/ids; merged with BROWSER_SEED_GROUP_URLS from .env",
    )
    parser.add_argument(
        "--skip-parent",
        action="store_true",
        help="Omit the first phase (--in-group-query); only construction-derived phrases",
    )
    parser.add_argument(
        "--additional-search",
        default=None,
        metavar="PHRASES",
        help=(
            "Optional comma-separated extra in-group phrases **after** the built-in construction set. "
            "Entries with # or _ are normalized like tags (e.g. #рабочий_строительства → рабочий строительства)."
        ),
    )
    parser.add_argument(
        "--no-global-message-filter",
        action="store_true",
        help="By default, when --in-group-query is used, only posts whose message contains that phrase "
        "are kept (all phases). Pass this to disable.",
    )
    parser.add_argument(
        "--daily-report-first",
        action="store_true",
        help="Before Playwright, run ./scripts/admin_request.sh report (timestamped CSVs under REPORTS_DIR, "
        "then email). Needs ADMIN_TOKEN and API_HOST; app must be listening.",
    )
    parser.add_argument(
        "--admin-report",
        action="store_true",
        help="After a successful browser run, run ./scripts/admin_request.sh report again (CSV includes new upserts). "
        "Needs ADMIN_TOKEN and API_HOST in .env; app must be listening.",
    )
    args = parser.parse_args()

    load_dotenv_file()
    try:
        from src.config import get_settings  # noqa: E402
        from src.data.specialized_construction_hashtags import (  # noqa: E402
            SPECIALIZED_CONSTRUCTION_TAGS,
            merge_parent_in_group_with_additional,
            tag_strings,
            tag_to_in_group_search,
        )
        from src.services.pipeline import run_browser_search_sync  # noqa: E402
    except ModuleNotFoundError as exc:
        name = getattr(exc, "name", "") or ""
        if name in {"pydantic", "pydantic_settings"}:
            print(
                "error: install deps with the same Python:\n"
                f"    {Path(sys.executable)} -m pip install -r requirements-mcp.txt\n",
                file=sys.stderr,
            )
            raise SystemExit(2) from exc
        raise
    except TypeError as exc:
        if "str | None" in str(exc) or "Unable to evaluate type annotation" in str(exc):
            _die_py310_hint()
            raise SystemExit(2) from exc
        raise

    builtin_phrases = [tag_to_in_group_search(e["tag"]) for e in SPECIALIZED_CONSTRUCTION_TAGS]
    builtin_tags = tag_strings()
    extra_phrases: list[str] = []
    if args.additional_search:
        for part in args.additional_search.replace("\n", ",").split(","):
            raw = part.strip()
            if not raw:
                continue
            if "#" in raw or "_" in raw:
                extra_phrases.append(tag_to_in_group_search(raw))
            else:
                extra_phrases.append(raw)

    main_q = (args.in_group_query or "").strip() if not args.skip_parent else ""

    phrases: list[str] = []
    if not args.skip_parent:
        if not main_q:
            print("error: need --in-group-query or pass --skip-parent\n", file=sys.stderr)
            return 2
        phrases.append(main_q)
        for p in builtin_phrases:
            phrases.append(merge_parent_in_group_with_additional(main_q, p))
        for p in extra_phrases:
            phrases.append(merge_parent_in_group_with_additional(main_q, p))
    else:
        phrases.extend(builtin_phrases)
        phrases.extend(extra_phrases)
    phrases = _dedupe_preserve(phrases)

    if main_q:
        additional_search_list = [
            merge_parent_in_group_with_additional(main_q, p) for p in builtin_phrases
        ]
        seen_add = {x.casefold() for x in additional_search_list}
        for ep in extra_phrases:
            merged = merge_parent_in_group_with_additional(main_q, ep)
            k = merged.casefold().strip()
            if not k or k in seen_add:
                continue
            seen_add.add(k)
            additional_search_list.append(merged)
    else:
        additional_search_list = list(builtin_phrases)
        seen_add = {x.casefold() for x in builtin_phrases}
        for ep in extra_phrases:
            k = ep.casefold().strip()
            if not k or k in seen_add:
                continue
            seen_add.add(k)
            additional_search_list.append(ep)
    additional_search = ", ".join(additional_search_list)

    print(
        f"--- single Playwright session, {len(phrases)} in-group phase(s) ---",
        file=sys.stderr,
    )
    for i, ph in enumerate(phrases, 1):
        print(f"  {i}. {ph}", file=sys.stderr)

    get_settings.cache_clear()
    settings = get_settings()
    from src.db.session import init_db, init_engine  # noqa: E402

    init_engine(settings.database_url)
    init_db()

    global_filter = None if args.no_global_message_filter else (main_q or None)

    exit_code = 0
    pre_report: dict | None = None
    if args.daily_report_first:
        print(
            "--- ./scripts/admin_request.sh report (before browser; timestamped CSVs in REPORTS_DIR) ---",
            file=sys.stderr,
        )
        rc_pre, out_pre, err_pre = _run_admin_daily_report(_REPO)
        pre_report = {
            "ok": rc_pre == 0,
            "exit_code": rc_pre,
            "stdout": out_pre.strip(),
            "stderr": err_pre.strip(),
        }
        if err_pre.strip():
            print(err_pre, file=sys.stderr)
        if rc_pre != 0:
            exit_code = 1

    out = run_browser_search_sync(
        settings,
        query=args.query,
        in_group_queries=phrases,
        group_limit=args.group_limit,
        post_limit_per_group=args.post_limit,
        seed_group_urls=args.seed_group_urls,
        global_message_contains=global_filter,
    )
    summary: dict = {
        "ok": out.get("ok"),
        "skip_parent": bool(args.skip_parent),
        "in_group_queries": phrases,
        "global_message_contains": out.get("global_message_contains"),
        "additional_search": additional_search,
        "additional_search_list": additional_search_list,
        "additional_search_tags": builtin_tags,
        "query": out.get("query"),
        "upserted": out.get("upserted"),
        "found_posts": out.get("found_posts"),
        "groups_scanned": out.get("groups_scanned"),
        "groups_with_hits": out.get("groups_with_hits"),
        "html_report_dir": out.get("html_report_dir"),
        "errors": out.get("errors"),
        "error": out.get("error"),
    }

    if pre_report is not None:
        summary["daily_report_first_requested"] = True
        summary["daily_report_first"] = pre_report

    if not out.get("ok"):
        exit_code = 1

    if args.admin_report:
        summary["admin_report_requested"] = True
        if not out.get("ok"):
            summary["admin_report"] = {
                "ok": False,
                "skipped": True,
                "reason": "browser run did not succeed",
            }
        else:
            print("--- ./scripts/admin_request.sh report (after browser; daily CSV + email) ---", file=sys.stderr)
            rc, out_adm, err_adm = _run_admin_daily_report(_REPO)
            summary["admin_report"] = {
                "ok": rc == 0,
                "exit_code": rc,
                "stdout": out_adm.strip(),
                "stderr": err_adm.strip(),
            }
            if err_adm.strip():
                print(err_adm, file=sys.stderr)
            if rc != 0:
                exit_code = 1

    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return exit_code


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
