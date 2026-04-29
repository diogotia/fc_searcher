#!/usr/bin/env python3
"""
Get a *short-lived user* access token via Facebook Login (OAuth), without Graph API Explorer.

Use when Explorer does not let you generate a user token, or you prefer a standard OAuth flow.

Prerequisites (Meta Developer Console → your app):
  1) Add product **Facebook Login** (Вход через Facebook).
  2) In Facebook Login → **Settings** → **Valid OAuth Redirect URIs**, add the redirect URL
     this script prints (must match **exactly**, including http, host, port, and path).
  3) **App mode** / roles: you must be able to log in as a user allowed for your app.

Then run from the repo (loads project `.env`):
  FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, GRAPH_API_VERSION

Example:
  ./scripts/oauth_facebook_user_token_groups.sh
  python3 scripts/oauth_facebook_user_token.py --open-browser --scopes public_profile,groups_access_member_info

Copy the printed access_token into FACEBOOK_SHORT_TOKEN and run:
  python3 scripts/exchange_user_long_lived_token.py --token-only

Scope names and group access rules change — confirm allowed scopes for your GRAPH_API_VERSION in Meta docs.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from load_repo_env import load_dotenv_file


def _graph_ver() -> str:
    ver = os.environ.get("GRAPH_API_VERSION", "v21.0").strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"
    return ver


def main() -> int:
    load_dotenv_file()

    parser = argparse.ArgumentParser(description="Facebook Login: open browser, receive short-lived user token.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Local port (default 8765)")
    parser.add_argument(
        "--scopes",
        default=os.environ.get("FACEBOOK_OAUTH_SCOPES", "public_profile"),
        help="Comma-separated scopes (default public_profile or FACEBOOK_OAUTH_SCOPES from .env)",
    )
    parser.add_argument("--open-browser", action="store_true", help="Try to open the system web browser")
    args = parser.parse_args()

    app_id = os.environ.get("FACEBOOK_APP_ID", "").strip()
    secret = os.environ.get("FACEBOOK_APP_SECRET", "").strip()
    if not app_id or not secret:
        print(
            "error: set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET in the project `.env`.",
            file=sys.stderr,
        )
        return 1

    callback_path = "/oauth/facebook-callback"
    redirect_uri = f"http://{args.host}:{args.port}{callback_path}"
    state = secrets.token_urlsafe(24)
    holder: dict[str, str | None] = {"code": None, "error": None, "error_description": None, "got_state": None}

    ver = _graph_ver()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_error(404, "Not found")
                return
            q = parse_qs(parsed.query)
            holder["got_state"] = (q.get("state") or [None])[0]
            if q.get("error"):
                holder["error"] = (q.get("error") or [""])[0]
                holder["error_description"] = (q.get("error_description") or [""])[0]
            if q.get("code"):
                holder["code"] = (q.get("code") or [""])[0]
            body = (
                b"<html><body><p>Facebook Login complete. You can close this tab "
                b"and return to the terminal.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    scope_str = ",".join(s.strip() for s in args.scopes.split(",") if s.strip())
    auth_params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": scope_str,
    }
    auth_q = urllib.parse.urlencode(auth_params, quote_via=urllib.parse.quote)
    dialog_url = f"https://www.facebook.com/{ver}/dialog/oauth?{auth_q}"

    print("--- Facebook Login (user token) ---", file=sys.stderr)
    print(f"Using Graph version: {ver}", file=sys.stderr)
    print(
        "Add this **exact** URL under Meta app → Facebook Login → Settings → "
        "Valid OAuth Redirect URIs:",
        file=sys.stderr,
    )
    print(f"  {redirect_uri}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Waiting for one request on this machine…", file=sys.stderr)
    print("Open this URL in your browser (log in with Facebook when prompted):", file=sys.stderr)
    print(dialog_url, file=sys.stderr)
    print("", file=sys.stderr)

    if args.open_browser:
        import webbrowser

        try:
            webbrowser.open(dialog_url)
        except Exception as exc:  # noqa: BLE001 — optional UX
            print(f"note: could not open browser automatically ({exc}). Open the URL above manually.", file=sys.stderr)

    try:
        httpd = HTTPServer((args.host, args.port), _Handler)
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, 48, 98):  # 48 macOS, 98 Linux
            print(
                f"error: port {args.port} is already in use. Stop the other process (e.g. old oauth run) "
                f"or retry with --port 8767 and add **exactly** "
                f"http://{args.host}:8767/oauth/facebook-callback to Meta → Facebook Login → Redirect URIs.",
                file=sys.stderr,
            )
            return 1
        raise
    httpd.timeout = 1.0
    deadline = time.monotonic() + 600.0
    while time.monotonic() < deadline:
        httpd.handle_request()
        if holder["code"] or holder["error"]:
            break
    else:
        print("error: timed out waiting for browser callback (10 min).", file=sys.stderr)
        return 1

    if holder["error"]:
        print(
            f"error: Facebook returned error={holder['error']} {holder.get('error_description') or ''}".strip(),
            file=sys.stderr,
        )
        return 1
    if holder["got_state"] != state:
        print(
            "error: state mismatch (possible CSRF). Try again.",
            file=sys.stderr,
        )
        return 1
    code = holder["code"]
    if not code:
        print("error: no authorization code in callback.", file=sys.stderr)
        return 1

    ex_params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "client_secret": secret,
        "code": code,
    }
    ex_q = urllib.parse.urlencode(ex_params, quote_via=urllib.parse.quote)
    token_url = f"https://graph.facebook.com/{ver}/oauth/access_token?{ex_q}"
    try:
        with urllib.request.urlopen(token_url, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
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

    print(token)
    print(
        "\nNext: put this string in FACEBOOK_SHORT_TOKEN in .env, then run:\n"
        "  python3 scripts/exchange_user_long_lived_token.py --token-only\n"
        "and copy the result into FACEBOOK_ACCESS_TOKEN.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
