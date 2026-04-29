#!/usr/bin/env python3
"""
Step 4 — Exchange a short-lived *user* access token for a long-lived one (~60 days).

Reads from the project root `.env` (same KEY=value rules as `admin_request.py`):

  FACEBOOK_APP_ID
  FACEBOOK_APP_SECRET
  FACEBOOK_SHORT_TOKEN   # short token from Graph API Explorer

Or set those in the environment instead of using a file.

The script always loads the project root `.env` (same folder as `README.md`), even if your
shell cwd is elsewhere — use a line like `FACEBOOK_SHORT_TOKEN=...` (not `envFACEBOOK_...`).
If Graph API Explorer cannot produce a user token, use `scripts/oauth_facebook_user_token.py`
(Facebook Login) to print a short-lived user token, then paste it here.

Usage:
  cd fc_searcher
  python3 scripts/exchange_user_long_lived_token.py
  python3 scripts/exchange_user_long_lived_token.py --token-only

Then put the returned `access_token` into FACEBOOK_ACCESS_TOKEN in `.env`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from load_repo_env import load_dotenv_file, project_root


def _normalize_exchange_token(raw: str) -> str:
    """Strip BOM/outer whitespace; remove CR/LF and zero-width chars from copy-paste."""
    s = raw.strip().strip("\ufeff").replace("\r", "").replace("\n", "")
    for ch in ("\u200b", "\u200c", "\u200d"):
        s = s.replace(ch, "")
    s = s.strip()
    while True:
        low = s.lower()
        if low.startswith("bearer "):
            s = s[7:].strip()
            continue
        if low.startswith("access_token="):
            s = s.split("=", 1)[1].strip()
            continue
        break
    # Whole JSON object pasted from a tool response
    if s.startswith("{") and '"access_token"' in s.replace("'", '"'):
        try:
            blob = json.loads(s)
            if isinstance(blob, dict):
                inner = blob.get("access_token")
                if isinstance(inner, str) and inner.strip():
                    s = inner.strip()
        except json.JSONDecodeError:
            pass
    # Outer quotes left in value
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    # Meta tokens are a single segment — remove accidental spaces / line wraps
    s = "".join(s.split())
    return s


def _looks_like_app_access_token(s: str) -> bool:
    """Meta app tokens look like ``{numeric_app_id}|{secret}`` — not valid for fb_exchange_token."""
    if "|" not in s:
        return False
    left, _, right = s.partition("|")
    return left.isdigit() and len(right) >= 8


def main() -> int:
    loaded_path = load_dotenv_file()
    parser = argparse.ArgumentParser(description="Exchange short-lived user token for long-lived token.")
    parser.add_argument("--token-only", action="store_true", help="Print only access_token")
    parser.add_argument(
        "--graph-version",
        default=os.environ.get("GRAPH_API_VERSION", "v21.0"),
        help="Graph version prefix (default: GRAPH_API_VERSION or v21.0)",
    )
    args = parser.parse_args()

    app_id = os.environ.get("FACEBOOK_APP_ID", "").strip()
    secret = os.environ.get("FACEBOOK_APP_SECRET", "").strip()
    short_raw = os.environ.get("FACEBOOK_SHORT_TOKEN", "").strip() or os.environ.get(
        "FB_EXCHANGE_TOKEN", ""
    ).strip()
    short = _normalize_exchange_token(short_raw)

    if not app_id or not secret or not short:
        env_file = project_root() / ".env"
        if loaded_path:
            src = f"loaded {loaded_path}"
        else:
            src = f"no {env_file} (create it in the project root, next to README.md)"
        gaps: list[str] = []
        if not app_id:
            gaps.append("FACEBOOK_APP_ID")
        if not secret:
            gaps.append("FACEBOOK_APP_SECRET")
        if not short:
            gaps.append("FACEBOOK_SHORT_TOKEN (or FB_EXCHANGE_TOKEN)")
        print(
            "error: need non-empty "
            + ", ".join(["FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET", "FACEBOOK_SHORT_TOKEN"])
            + " — short *user* token from Graph API Explorer.",
            file=sys.stderr,
        )
        print(f"  ({src})", file=sys.stderr)
        print(f"  empty or unset: {', '.join(gaps)}", file=sys.stderr)
        print(
            "  add: FACEBOOK_SHORT_TOKEN=paste_token_here  "
            "(no spaces around `=`; remove or fill any second empty FACEBOOK_SHORT_TOKEN= line)",
            file=sys.stderr,
        )
        return 1

    if _looks_like_app_access_token(short):
        print(
            "error: FACEBOOK_SHORT_TOKEN is an *app* access token (shape: YOUR_APP_ID|...). "
            "That value cannot be exchanged for a long-lived *user* token.",
            file=sys.stderr,
        )
        print(
            "  Do this instead:\n"
            "  1) Open https://developers.facebook.com/tools/explorer\n"
            "  2) Select your Meta app (top right).\n"
            "  3) Under **User or Page**, pick **User Token** (not *Get App Token* / not Page).\n"
            "  4) Click **Generate Access Token**, log in with Facebook, approve scopes.\n"
            "  5) Copy the token string (usually starts with EAA… and does **not** contain `|`).\n"
            "  6) Put only that string in FACEBOOK_SHORT_TOKEN=… in .env (keep APP_ID|SECRET on separate lines).\n"
            "  Note: output from scripts/fetch_app_access_token.py is an app token — do not paste it here.",
            file=sys.stderr,
        )
        return 1

    ver = args.graph_version.strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"

    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": secret,
        "fb_exchange_token": short,
    }
    # quote (not quote_plus) so '+' inside a token is sent as %2B, not as a space
    q = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"https://graph.facebook.com/{ver}/oauth/access_token?{q}"

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(err_body, file=sys.stderr)
        try:
            parsed = json.loads(err_body)
            err = parsed.get("error") or {}
            msg = str(err.get("message", ""))
            code = err.get("code")
            if "No user access token" in msg or code == 1:
                print(
                    f"hint: Meta rejected fb_exchange_token (local length {len(short)}). "
                    "In Graph API Explorer choose **User** (not Page / not App), click **Generate access token**, "
                    "and paste that string into FACEBOOK_SHORT_TOKEN. "
                    "App tokens contain `|` — those cannot be exchanged here.",
                    file=sys.stderr,
                )
            if code == 190 or "Cannot parse access token" in msg:
                preview = short[:7] + "…" + short[-4:] if len(short) > 14 else "(short)"
                bad = [hex(ord(c)) for c in short[:40] if ord(c) > 127 or not c.isprintable()]
                print(
                    f"hint: code 190 — token looks malformed to Meta (length {len(short)}, preview {preview}). "
                    "Paste only the raw EAA… string on one line in .env (no JSON, no quotes). "
                    f"Non-ASCII / odd chars in first 40: {bad or 'none'}",
                    file=sys.stderr,
                )
        except json.JSONDecodeError:
            pass
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
        print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
