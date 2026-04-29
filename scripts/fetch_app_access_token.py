#!/usr/bin/env python3
"""
Fetch a Facebook *App* access token using client_credentials.

Usage (from repo root, secrets only in your environment — never commit them):

  export FACEBOOK_APP_ID="your_app_id"
  export FACEBOOK_APP_SECRET="your_app_secret"
  python3 scripts/fetch_app_access_token.py

Or print only the token for scripting:

  python3 scripts/fetch_app_access_token.py --token-only

This token is an *application* access token. It does **not** replace a User or
Page access token for most Graph calls (e.g. reading group feeds). For group
monitoring you still need a token issued to a user/page with the right scopes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _load_dotenv_from_cwd() -> None:
    """Load `.env` from current working directory if present (does not override existing exports)."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def _validate_app_id(app_id: str) -> str | None:
    """Return error message if App ID looks wrong, else None."""
    stripped = app_id.strip()
    if stripped != app_id:
        return "FACEBOOK_APP_ID has leading/trailing spaces; remove them."
    if not stripped.isdigit():
        return (
            "FACEBOOK_APP_ID must be the numeric App ID from Meta for Developers → "
            "Your app → Settings → Basic (digits only). "
            "Do not use README placeholder text like 'your app id' or '…'."
        )
    if len(stripped) < 8:
        return "FACEBOOK_APP_ID looks too short; double-check you copied the full App ID."
    return None


def main() -> int:
    _load_dotenv_from_cwd()

    parser = argparse.ArgumentParser(description="Fetch Facebook app access token (client_credentials).")
    parser.add_argument(
        "--graph-version",
        default=os.environ.get("GRAPH_API_VERSION", "v21.0"),
        help="Graph API version prefix (default: v21.0 or GRAPH_API_VERSION).",
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Print only the access_token string (no JSON).",
    )
    args = parser.parse_args()

    app_id = os.environ.get("FACEBOOK_APP_ID")
    secret = os.environ.get("FACEBOOK_APP_SECRET")
    if not app_id or not secret:
        print(
            "Error: set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET (e.g. in `.env` or via export). "
            "If you use `.env`, run this script from the project directory so it can be loaded.",
            file=sys.stderr,
        )
        return 1

    err = _validate_app_id(app_id)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if re.search(r"(?i)(your[_\s]?app|placeholder|…\s*your)", secret):
        print(
            "Error: FACEBOOK_APP_SECRET looks like placeholder text. Use the real secret from Meta.",
            file=sys.stderr,
        )
        return 1

    ver = args.graph_version.strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"

    q = urllib.parse.urlencode(
        {
            "client_id": app_id,
            "client_secret": secret,
            "grant_type": "client_credentials",
        }
    )
    url = f"https://graph.facebook.com/{ver}/oauth/access_token?{q}"

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(raw, file=sys.stderr)
        return 1

    token = data.get("access_token")
    if not token:
        print(json.dumps(data, indent=2), file=sys.stderr)
        return 1

    if args.token_only:
        print(token)
    else:
        # Do not pretty-print the secret again inside token; full JSON is standard.
        print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
