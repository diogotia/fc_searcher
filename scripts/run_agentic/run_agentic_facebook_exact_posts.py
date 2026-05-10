#!/usr/bin/env python3
"""Run agentic Facebook sync with expanded post bodies and stricter DB filters.

Same CLI as ``scripts/run_agentic/run_agentic_facebook_once.py``, plus:

- **Ещё / See more:** After each in-group search navigation, scrolls and clicks truncated-post
  controls before scraping so ``message`` includes fuller text when Meta hides it behind “Ещё”.

- **Two-stage body filter (AND/OR):**

  1. Mandatory AND — when ``--global-message-contains`` (or ``BROWSER_GLOBAL_MESSAGE_CONTAINS``)
     is set, the post body must contain that exact phrase (case-insensitive substring), e.g.
     ``ищу работу``.
  2. Optional OR — when ``--in-post-keywords`` (CLI) or ``BROWSER_IN_GROUP_SEARCH_IN_POST``
     (.env) is set, the post body must additionally contain at least one of the listed
     trade-role keywords (e.g. ``Каменщик,Бетонщик,Арматурщик,...``). The matched needle is
     stamped onto the post as ``matched_in_post_keyword`` for the HTML report.

  When ``BROWSER_IN_GROUP_SEARCH_IN_POST`` is empty AND ``--in-post-keywords`` is not passed,
  the OR stage is a no-op (only the AND --global-message-contains stage applies).

- **Facebook UI creation-year on in-group URLs:** When ``BROWSER_POST_PUBLICATION_YEAR`` is set
  in ``.env`` (e.g. ``2026`` or ``auto``), the same ``filters=`` token as
  ``run_agentic_facebook_once_exact_year.py`` is appended to every group search URL. If the year
  env var is unset, no URL year filter is applied.

Usage::

    .venv/bin/python scripts/run_agentic/run_agentic_facebook_exact_posts.py

Requires ``ENABLE_AGENTIC_FACEBOOK_SYNC=true``. Anthropic env vars are stripped like
``scripts/run_agentic/run_agentic_facebook_once.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_RUN_AGENTIC_DIR = Path(__file__).resolve().parent
_SCRIPTS_ROOT = _RUN_AGENTIC_DIR.parent
_REPO = _SCRIPTS_ROOT.parent
os.environ.setdefault("FC_SEARCHER_REPO_ROOT", str(_REPO))
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from load_repo_env import load_dotenv_file  # noqa: E402


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
        if rc == here or not _interpreter_ok(rc):
            continue
        os.environ["FC_SEARCHER_VENV_REEXEC"] = "1"
        os.execv(str(rc), [str(rc), str(script), *sys.argv[1:]])


def _die_py310_hint() -> None:
    print(
        "error: this project needs Python 3.10 or newer (your interpreter is older).\n"
        "  Fix:\n"
        "    brew install python@3.12\n"
        "    ./scripts/recreate_venv_for_mcp.sh\n"
        "    .venv/bin/python scripts/run_agentic/run_agentic_facebook_exact_posts.py\n",
        file=sys.stderr,
    )


def main() -> int:
    if sys.version_info < (3, 10):
        _die_py310_hint()
        return 2

    parser = argparse.ArgumentParser(
        description="Agentic Facebook sync with see-more expansion and body keyword union filter."
    )
    parser.add_argument("--query", default=None, help="Override BROWSER_SEARCH_QUERY")
    parser.add_argument("--in-group-query", default=None, dest="in_group_query")
    parser.add_argument("--group-limit", type=int, default=None, metavar="N")
    parser.add_argument("--post-limit", type=int, default=None, metavar="N")
    parser.add_argument("--seed-group-urls", default=None, help="Comma-separated group URLs/ids")
    parser.add_argument(
        "--global-message-contains",
        default=None,
        metavar="SUBSTRING",
        help="Override BROWSER_GLOBAL_MESSAGE_CONTAINS (mandatory AND substring on post body; empty disables).",
    )
    parser.add_argument(
        "--in-group-exact-keywords",
        dest="in_group_exact_keywords",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Each comma-separated --in-group-query segment is used verbatim as in-group /groups/.../search/?q= "
        "(no prefix from BROWSER_SEARCH_QUERY). Default on so phrases like "
        "'ищу работу Каменщик, ищу работу Бетонщик' match chat input. "
        "Use --no-in-group-exact-keywords to prefix short tokens with the discovery query.",
    )
    parser.add_argument(
        "--in-post-keywords",
        dest="in_post_keywords",
        default=None,
        metavar="CSV",
        help="Comma-separated trade-role keywords; OR-filter applied to scraped post body "
        "(case-insensitive substring). Overrides BROWSER_IN_GROUP_SEARCH_IN_POST from .env. "
        "Empty CLI value + empty env = no OR-filter. Pair with BROWSER_GLOBAL_MESSAGE_CONTAINS "
        "(or --global-message-contains) for the mandatory AND phrase (e.g. \"ищу работу\").",
    )
    args = parser.parse_args()

    load_dotenv_file()
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("CLAUDE_MODEL", None)
    try:
        from src.config import clear_settings_caches, get_settings  # noqa: E402
        from src.db.session import init_db, init_engine  # noqa: E402
        from src.services.agentic_facebook import run_agentic_facebook_sync  # noqa: E402
    except ModuleNotFoundError as exc:
        name = getattr(exc, "name", "") or ""
        if name in {"pydantic", "pydantic_settings"}:
            print(
                "error: dependencies missing. Install with the same Python you use to run this script:\n"
                f"    {Path(sys.executable)} -m pip install -r requirements-mcp.txt\n",
                file=sys.stderr,
            )
            raise SystemExit(2) from exc
        raise

    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()
    if args.global_message_contains is not None:
        gmc = str(args.global_message_contains).strip() or None
    else:
        gmc = (settings.browser_global_message_contains or "").strip() or None
    facebook_ui_year_filter = settings.browser_post_publication_year is not None
    from src.services.browser_search import parse_in_post_keywords  # noqa: E402

    in_post_keywords: list[str] | None = None
    if args.in_post_keywords is not None:
        in_post_keywords = parse_in_post_keywords(args.in_post_keywords)
    out = run_agentic_facebook_sync(
        settings,
        query=args.query,
        in_group_query=args.in_group_query,
        group_limit=args.group_limit,
        post_limit_per_group=args.post_limit,
        seed_group_urls=args.seed_group_urls,
        global_message_contains=gmc,
        in_group_exact_keywords=args.in_group_exact_keywords,
        facebook_ui_year_filter=facebook_ui_year_filter,
        expand_see_more_before_extract=True,
        body_keyword_union=True,
        in_post_keywords=in_post_keywords,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
