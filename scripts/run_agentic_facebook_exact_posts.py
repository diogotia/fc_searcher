#!/usr/bin/env python3
"""Run agentic Facebook sync with expanded post bodies and stricter DB filters.

Same CLI as ``run_agentic_facebook_once.py``, plus:

- **Ещё / See more:** After each in-group search navigation, scrolls and clicks truncated-post
  controls before scraping so ``message`` includes fuller text when Meta hides it behind “Ещё”.
- **Body keyword union:** Keeps a post only if its body contains at least one of: each
  comma-separated ``--in-group-query`` phrase (after normal parsing), **or** the discovery
  ``--query`` phrase (same as group discovery). Reduces unrelated hits in the database.

Usage::

    .venv/bin/python scripts/run_agentic_facebook_exact_posts.py

Requires ``ENABLE_AGENTIC_FACEBOOK_SYNC=true``. Anthropic env vars are stripped like
``run_agentic_facebook_once.py``.
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
        "    .venv/bin/python scripts/run_agentic_facebook_exact_posts.py\n",
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
    parser.add_argument("--global-message-contains", default=None, metavar="SUBSTRING")
    parser.add_argument(
        "--in-group-exact-keywords",
        action="store_true",
        help="In-group /groups/.../search/?q= uses only --in-group-query (or BROWSER_IN_GROUP_SEARCH_QUERY) "
        "tokens, no prefix from BROWSER_SEARCH_QUERY (e.g. Бетонщик not 'ищу... Бетонщик').",
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
    gmc = args.global_message_contains
    if gmc is not None:
        gmc = str(gmc).strip() or None
    out = run_agentic_facebook_sync(
        settings,
        query=args.query,
        in_group_query=args.in_group_query,
        group_limit=args.group_limit,
        post_limit_per_group=args.post_limit,
        seed_group_urls=args.seed_group_urls,
        global_message_contains=gmc,
        in_group_exact_keywords=bool(args.in_group_exact_keywords),
        expand_see_more_before_extract=True,
        body_keyword_union=True,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
