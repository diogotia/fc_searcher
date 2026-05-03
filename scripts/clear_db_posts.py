#!/usr/bin/env python3
"""Report or delete stored posts (safe on-demand cleanup).

Default: **dry-run** — prints row counts per ``Post.source`` and exits.

Deletion removes rows from ``posts``; related ``analyses``, ``extracted_phones``, and
``extracted_emails`` rows are removed via FK cascade.

Examples::

    # Inspect only (safe)
    .venv/bin/python scripts/clear_db_posts.py

    # Delete Playwright/browser scrape rows only (same DB targets as search flows)
    .venv/bin/python scripts/clear_db_posts.py --execute --yes

    # Delete only agentic rows
    .venv/bin/python scripts/clear_db_posts.py --execute --yes --source playwright_agentic

    # Delete everything in ``posts`` (destructive)
    .venv/bin/python scripts/clear_db_posts.py --execute --yes --all-posts

Uses ``DATABASE_URL`` from project ``.env`` (via ``load_repo_env``).
"""

from __future__ import annotations

import argparse
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


DEFAULT_SCRAPE_SOURCES = ("playwright_browser", "playwright_agentic")


def _interpreter_ok(py: Path) -> bool:
    if not py.is_file() or not os.access(py, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [str(py), "-c", "import sys; assert sys.version_info >= (3, 10); import sqlalchemy"],
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
    for cand in (
        _REPO / ".venv-py312/bin/python",
        _REPO / ".venv/bin/python",
        Path("/opt/homebrew/bin/python3.12"),
        Path("/usr/local/bin/python3.12"),
    ):
        if cand.is_file() and cand.resolve() != here and _interpreter_ok(cand):
            os.environ["FC_SEARCHER_VENV_REEXEC"] = "1"
            os.execv(str(cand), [str(cand), str(script), *sys.argv[1:]])


def _print_counts(rows: list[tuple[str, int]], *, database_url_hint: str) -> None:
    print(f"Database: {database_url_hint}")
    print("Posts by source:")
    total = 0
    for src, n in sorted(rows, key=lambda x: x[0]):
        print(f"  {src!r}: {n}")
        total += n
    print(f"  TOTAL: {total}")


def main() -> int:
    if sys.version_info < (3, 10):
        print("error: Python 3.10+ required.", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(
        description="List or delete posts in the fc_searcher database (safe dry-run by default)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows (without this flag, only counts are printed).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation (required for non-interactive deletes).",
    )
    parser.add_argument(
        "--all-posts",
        action="store_true",
        help="Delete every row in posts (not only Playwright sources). Very destructive.",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE",
        help=(
            "Restrict deletion to this Post.source value (repeatable). "
            "If omitted with --execute, defaults to playwright_browser and playwright_agentic."
        ),
    )
    args = parser.parse_args()

    load_dotenv_file()

    from sqlalchemy import delete, func, select

    from src.config import clear_settings_caches, get_settings
    from src.db.db_models import Post
    from src.db.session import get_session, init_db, init_engine

    clear_settings_caches()
    settings = get_settings()
    url_hint = settings.database_url
    if "@" in url_hint:
        url_hint = "<redacted credentials>"
    init_engine(settings.database_url)
    init_db()

    with get_session() as session:
        rows = list(
            session.execute(
                select(Post.source, func.count()).group_by(Post.source).order_by(Post.source)
            ).all()
        )
        counts = [(str(r[0]), int(r[1])) for r in rows]

    _print_counts(counts, database_url_hint=url_hint)

    if not args.execute:
        print()
        print("Dry-run only. To delete Playwright/search scrape posts:")
        print(f"  {Path(sys.argv[0]).name} --execute --yes")
        print("To delete all posts:")
        print(f"  {Path(sys.argv[0]).name} --execute --yes --all-posts")
        return 0

    if args.all_posts and args.sources:
        print("error: use either --all-posts or --source, not both.", file=sys.stderr)
        return 2

    if args.all_posts:
        targets: list[str] | None = None
        label = "ALL posts"
    elif args.sources:
        targets = []
        for raw in args.sources:
            for part in raw.split(","):
                p = part.strip()
                if p:
                    targets.append(p)
        if not targets:
            print("error: --source produced no values.", file=sys.stderr)
            return 2
        label = ", ".join(repr(t) for t in targets)
    else:
        targets = list(DEFAULT_SCRAPE_SOURCES)
        label = "default scrape sources (" + ", ".join(DEFAULT_SCRAPE_SOURCES) + ")"

    if args.all_posts:
        print()
        print("WARNING: This will delete EVERY row in `posts` (cascade analyses, phones, emails).")

    if not args.yes:
        print()
        print(f"About to delete: {label}")
        try:
            line = input("Type DELETE and press Enter to confirm (or empty to abort): ")
        except EOFError:
            print("Aborted (no tty). Use --yes for non-interactive runs.", file=sys.stderr)
            return 2
        if line.strip() != "DELETE":
            print("Aborted.")
            return 3

    deleted = 0
    with get_session() as session:
        if targets is None:
            res = session.execute(delete(Post))
            deleted = res.rowcount or 0
        else:
            res = session.execute(delete(Post).where(Post.source.in_(targets)))
            deleted = res.rowcount or 0

    print()
    print(f"Deleted {deleted} post row(s) ({label}).")
    return 0


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
