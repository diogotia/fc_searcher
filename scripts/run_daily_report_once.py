#!/usr/bin/env python3
"""Run the daily report pipeline once (CSV + optional phone/email CSVs + SMTP), same as MCP ``facebook_send_daily_report``.

Loads project ``.env``, initializes the DB, calls ``run_daily_report``, prints a short **status** block to stderr
and the full result as JSON on stdout.

Requires Python 3.10+. Email sends only when ``SMTP_USER``, ``SMTP_PASSWORD``, and ``REPORT_EMAIL`` are set.

Usage::

    cd /Users/andreidiogoti/Documents/fc_searcher
    .venv/bin/python scripts/run_daily_report_once.py

    .venv/bin/python scripts/run_daily_report_once.py --json-only
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
            [str(py), "-c", "import sys; assert sys.version_info >= (3, 10); import pydantic"],
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
        Path("/opt/homebrew/bin/python3.11"),
        Path("/usr/local/bin/python3.11"),
    ):
        if not cand.is_file():
            continue
        rc = cand.resolve()
        if rc == here or not _interpreter_ok(rc):
            continue
        os.environ["FC_SEARCHER_VENV_REEXEC"] = "1"
        os.execv(str(rc), [str(rc), str(script), *sys.argv[1:]])


def _die_py310_hint() -> None:
    print(
        "error: Python 3.10+ required. Try: brew install python@3.12 && ./scripts/recreate_venv_for_mcp.sh\n",
        file=sys.stderr,
    )


def _print_status(out: dict, settings) -> None:
    smtp_ok = bool(settings.smtp_user and settings.smtp_password and settings.report_email)
    lines = [
        "=== Daily report job ===",
        f"  ok:                 {out.get('ok')}",
        f"  email_sent:         {out.get('email_sent')}  (smtp_configured={smtp_ok})",
        f"  report_date:        {out.get('date', '—')}",
        f"  rows (main CSV):    {out.get('rows')}",
        f"  phones_exported:    {out.get('phones_exported')}",
        f"  emails_exported:    {out.get('emails_exported')}",
        f"  csv:                {out.get('csv')}",
    ]
    if out.get("phones_csv"):
        lines.append(f"  phones_csv:         {out['phones_csv']}")
    if out.get("emails_csv"):
        lines.append(f"  emails_csv:         {out['emails_csv']}")
    if not smtp_ok:
        lines.append(
            "  hint: Set SMTP_USER, SMTP_PASSWORD, REPORT_EMAIL in .env to send email."
        )
    print("\n".join(lines), file=sys.stderr)


def main() -> int:
    if sys.version_info < (3, 10):
        _die_py310_hint()
        return 2

    parser = argparse.ArgumentParser(description="Run daily report + email once (reads .env).")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only print JSON to stdout (no status lines on stderr).",
    )
    args = parser.parse_args()

    load_dotenv_file()
    try:
        from src.config import clear_settings_caches, get_settings  # noqa: E402
        from src.db.session import init_db, init_engine  # noqa: E402
        from src.services.pipeline import run_daily_report  # noqa: E402
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", "") in {"pydantic", "pydantic_settings"}:
            print(
                f"error: install deps: {sys.executable} -m pip install -r requirements.txt\n",
                file=sys.stderr,
            )
            return 2
        raise

    clear_settings_caches()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()

    try:
        out = run_daily_report(settings)
    except Exception as exc:
        err = {"ok": False, "error": str(exc)}
        if not args.json_only:
            print("=== Daily report job ===", file=sys.stderr)
            print(f"  FAILED: {exc}", file=sys.stderr)
        print(json.dumps(err, indent=2, default=str))
        return 1

    if not args.json_only:
        _print_status(out, settings)

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out.get("ok") is not False else 1


if __name__ == "__main__":
    _try_reexec_with_suitable_python()
    raise SystemExit(main())
