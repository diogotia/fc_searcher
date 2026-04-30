#!/usr/bin/env python3
"""Run one browser search sync using project `.env` (same pipeline as MCP `facebook_browser_search_sync`).

For **parent search + construction hashtag passes**, use
``scripts/run_browser_search_parent_then_construction_tags.py``.

Requires Python 3.10+ (fc_searcher uses `str | None` etc.). Requires `ENABLE_BROWSER_SEARCH_SYNC=true`
and other browser vars in `.env`. Optional `BROWSER_SEED_GROUP_URLS` is read after `.env` is loaded.

Usage (from repo root):

    .venv/bin/python scripts/run_browser_search_once.py

Use a venv created with **Homebrew `python3.12`** (not Apple `python3` / not a 3.9 venv). See README → MCP.
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
    """True if this executable is Python 3.10+ and can import pydantic (project baseline)."""
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
    """Re-run with Python 3.10+ when the current interpreter is too old (e.g. Apple or 3.9 `.venv`)."""
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
        "error: this project needs Python 3.10 or newer (your interpreter is older).\n"
        "  Your `.venv` may have been created with Apple/Xcode Python 3.9.\n"
        "  Fix:\n"
        "    brew install python@3.12\n"
        "    ./scripts/recreate_venv_for_mcp.sh\n"
        "    .venv/bin/python scripts/run_browser_search_once.py\n",
        file=sys.stderr,
    )


def main() -> int:
    if sys.version_info < (3, 10):
        _die_py310_hint()
        return 2

    parser = argparse.ArgumentParser(description="Run browser search sync once (reads .env).")
    parser.add_argument("--query", default=None, help="Override BROWSER_SEARCH_QUERY (global group discovery)")
    parser.add_argument(
        "--in-group-query",
        default=None,
        dest="in_group_query",
        help="Override BROWSER_IN_GROUP_SEARCH_QUERY: comma-separated tokens; each phase uses '<query> <token>'.",
    )
    parser.add_argument("--group-limit", type=int, default=None, metavar="N")
    parser.add_argument("--post-limit", type=int, default=None, metavar="N")
    parser.add_argument(
        "--seed-group-urls",
        default=None,
        help="Comma-separated URLs/ids; merged with BROWSER_SEED_GROUP_URLS from .env",
    )
    parser.add_argument(
        "--global-message-contains",
        default=None,
        metavar="SUBSTRING",
        help="Only keep posts whose message contains this text (case-insensitive). Optional.",
    )
    args = parser.parse_args()

    load_dotenv_file()
    try:
        from src.config import get_settings  # noqa: E402
        from src.services.pipeline import run_browser_search_sync  # noqa: E402
    except ModuleNotFoundError as exc:
        name = getattr(exc, "name", "") or ""
        if name in {"pydantic", "pydantic_settings"}:
            print(
                "error: dependencies missing. Install with the **same** Python you use to run this script:\n"
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

    get_settings.cache_clear()
    settings = get_settings()
    from src.db.session import init_db, init_engine  # noqa: E402

    init_engine(settings.database_url)
    init_db()
    gmc = args.global_message_contains
    if gmc is not None:
        gmc = str(gmc).strip() or None
    out = run_browser_search_sync(
        settings,
        query=args.query,
        in_group_query=args.in_group_query,
        group_limit=args.group_limit,
        post_limit_per_group=args.post_limit,
        seed_group_urls=args.seed_group_urls,
        global_message_contains=gmc,
    )
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
