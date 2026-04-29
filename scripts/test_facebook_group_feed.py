#!/usr/bin/env python3
"""
Step 5 — Test `GET /{group-id}/feed` with your user access token (from .env).

Uses:
  FACEBOOK_ACCESS_TOKEN
  FACEBOOK_GROUP_IDS   (first id only if comma-separated; numeric id or full
                        `https://www.facebook.com/groups/NUMERIC_ID/...` URL)
  GRAPH_API_VERSION    (default v21.0)

Optional: ``--diagnose`` — calls ``debug_token`` (needs FACEBOOK_APP_ID + FACEBOOK_APP_SECRET)
and ``/me/permissions`` with your user token to list what Graph actually granted.

Prints HTTP status and a short body preview. Interpretation (typical):
  200 + data array     → token can read feed
  400 (#3) Missing Permission → token missing scope or app/mode restrictions
  400 (#200)            → permissions / app review
  400 (#100)            → invalid group id or parameter

Scopes and product rules change — verify current Meta docs for your API version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from load_repo_env import load_dotenv_file

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _scope_list_from_debug(data: dict[str, object]) -> list[str]:
    """Normalize `scopes` or `granular_scopes` from debug_token into string permission names."""
    raw = data.get("scopes")
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw]
    gs = data.get("granular_scopes")
    if not isinstance(gs, list) or not gs:
        return []
    out: list[str] = []
    for item in gs:
        if isinstance(item, dict) and item.get("scope"):
            out.append(str(item["scope"]))
        else:
            out.append(str(item))
    return out


def _print_me_permissions(user_token: str, ver: str) -> None:
    """List permissions granted to this user token (often clearer than debug_token.scopes)."""
    q = urllib.parse.urlencode({"access_token": user_token}, quote_via=urllib.parse.quote)
    url = f"https://graph.facebook.com/{ver}/me/permissions?{q}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(
            f"--- me/permissions (failed) ---\n{exc.read().decode('utf-8', errors='replace')[:800]}",
            file=sys.stderr,
        )
        return
    except urllib.error.URLError as exc:
        print(f"--- me/permissions (failed): {exc}", file=sys.stderr)
        return
    try:
        rows = json.loads(body).get("data") or []
    except json.JSONDecodeError:
        print(f"--- me/permissions (bad JSON) ---\n{body[:800]}", file=sys.stderr)
        return
    granted = [
        r.get("permission")
        for r in rows
        if isinstance(r, dict) and r.get("status") == "granted" and r.get("permission")
    ]
    print("--- me/permissions (granted for this FACEBOOK_ACCESS_TOKEN) ---", file=sys.stderr)
    print(f"  count: {len(granted)}", file=sys.stderr)
    print(f"  granted: {granted}", file=sys.stderr)
    if not granted:
        print(
            "  WARNING: Graph reports **zero** granted permissions for this token. "
            "Re-authorize in Explorer or oauth script and **accept** each permission in the Facebook dialog.",
            file=sys.stderr,
        )
    print("", file=sys.stderr)


def _print_debug_token(user_token: str, ver: str) -> int:
    """Print granted scopes from Graph debug_token (needs app id + secret, not printed)."""
    app_id = os.environ.get("FACEBOOK_APP_ID", "").strip()
    secret = os.environ.get("FACEBOOK_APP_SECRET", "").strip()
    if not app_id or not secret:
        print(
            "error: --diagnose needs FACEBOOK_APP_ID and FACEBOOK_APP_SECRET in .env",
            file=sys.stderr,
        )
        return 1
    app_token = f"{app_id}|{secret}"
    q = urllib.parse.urlencode(
        {"input_token": user_token, "access_token": app_token},
        quote_via=urllib.parse.quote,
    )
    url = f"https://graph.facebook.com/{ver}/debug_token?{q}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        data = json.loads(body).get("data") or {}
    except json.JSONDecodeError:
        print(body[:2000], file=sys.stderr)
        return 1
    print("--- debug_token (scopes on your FACEBOOK_ACCESS_TOKEN) ---", file=sys.stderr)
    print(f"  is_valid: {data.get('is_valid')}", file=sys.stderr)
    print(f"  type: {data.get('type')}", file=sys.stderr)
    print(f"  app_id: {data.get('app_id')}", file=sys.stderr)
    print(f"  user_id: {data.get('user_id')}", file=sys.stderr)
    scopes = _scope_list_from_debug(data)
    print(f"  scopes ({len(scopes)}): {scopes}", file=sys.stderr)
    if not scopes:
        print(
            "  WARNING: token has no Graph permissions — /{group}/feed will return (#3). "
            "In Graph API Explorer generate a **new** user token and **enable the permission "
            "checkboxes** Meta lists for your app (group-related names change by API version). "
            "Or: python3 scripts/oauth_facebook_user_token.py --open-browser --scopes public_profile,… "
            "then put that value in FACEBOOK_SHORT_TOKEN and run exchange_user_long_lived_token again.",
            file=sys.stderr,
        )
        print(f"  debug_token keys: {sorted(data.keys())}", file=sys.stderr)
        dump = json.dumps(data, indent=2, ensure_ascii=False)[:2500]
        print(f"  raw data (truncated):\n{dump}", file=sys.stderr)
    print("", file=sys.stderr)
    _print_me_permissions(user_token, ver)
    return 0


def _first_numeric_group_id(raw_ids: str) -> str | None:
    """Accept `123` or a full `https://www.facebook.com/groups/123/...` when the path id is numeric."""
    from src.services.browser_search import extract_group_id

    first = raw_ids.split(",")[0].strip()
    if not first:
        return None
    if first.isdigit():
        return first
    extracted = extract_group_id(first)
    if extracted and extracted.isdigit():
        return extracted
    return None


def main() -> int:
    load_dotenv_file()
    parser = argparse.ArgumentParser(description="Test Graph group /feed with FACEBOOK_ACCESS_TOKEN.")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Call debug_token first (needs FACEBOOK_APP_ID + FACEBOOK_APP_SECRET) to list granted scopes",
    )
    parser.add_argument(
        "--group-url",
        metavar="URL_OR_ID",
        help=(
            "Override FACEBOOK_GROUP_IDS for this run only (numeric id or full "
            "https://www.facebook.com/groups/NUMERIC_ID/... URL). Use this when `.env` "
            "would otherwise win over a temporary shell export."
        ),
    )
    args = parser.parse_args()

    token = os.environ.get("FACEBOOK_ACCESS_TOKEN", "").strip()
    raw_ids = (args.group_url or os.environ.get("FACEBOOK_GROUP_IDS", "")).strip()
    ver = os.environ.get("GRAPH_API_VERSION", "v21.0").strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"

    if not token:
        print("error: FACEBOOK_ACCESS_TOKEN not set", file=sys.stderr)
        return 1
    if not raw_ids:
        print("error: FACEBOOK_GROUP_IDS not set", file=sys.stderr)
        return 1

    group_id = _first_numeric_group_id(raw_ids)
    if not group_id:
        first = raw_ids.split(",")[0].strip()
        print(
            f"error: first FACEBOOK_GROUP_IDS must be a **numeric** group id (or a facebook.com/groups/NUMERIC_URL), got {first!r}.",
            file=sys.stderr,
        )
        print(
            "  Examples: FACEBOOK_GROUP_IDS=934750153812574",
            file=sys.stderr,
        )
        print(
            "            FACEBOOK_GROUP_IDS=https://www.facebook.com/groups/934750153812574",
            file=sys.stderr,
        )
        print(
            "  Slugs in the URL (non-numeric) are not accepted here — resolve the numeric id in Meta tools or Page Source.",
            file=sys.stderr,
        )
        return 1

    if args.diagnose:
        rc = _print_debug_token(token, ver)
        if rc != 0:
            return rc

    params = urllib.parse.urlencode(
        {
            "fields": "id,message,created_time",
            "limit": "3",
            "access_token": token,
        }
    )
    url = f"https://graph.facebook.com/{ver}/{group_id}/feed?{params}"

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"HTTP {status}")
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2, ensure_ascii=False)[:4000])
        err_obj = parsed.get("error") or {}
        err = err_obj.get("message", "")
        code = err_obj.get("code")
        sub = err_obj.get("error_subcode")
        if status != 200 and "(#3) Missing Permission" in str(err):
            print(
                "\nHint: (#3) = Graph will not return this group's feed for this token. "
                "Common causes: missing/obsolete group scopes on the token, app in Development without the right roles, "
                "or Meta no longer offering group feed for your app type — see current Groups docs. "
                "Run with --diagnose to print granted scopes (needs FACEBOOK_APP_ID + FACEBOOK_APP_SECRET).",
                file=sys.stderr,
            )
        elif status != 200 and code == 100:
            print(
                "\nHint: code 100 often means this token cannot **see** the group or `/feed` is not allowed. "
                "If `--diagnose` shows only `public_profile`, re-authorize with **group-related** permissions "
                "Meta lists for your app (Explorer checkboxes or oauth `--scopes`), then exchange again. "
                "Also confirm FACEBOOK_GROUP_IDS is the numeric id, the Facebook **user** for this token is a **member** "
                "of that group, and the app (see debug_token app_id) is the one configured for Groups access.",
                file=sys.stderr,
            )
            if sub == 33:
                print(
                    "  (error_subcode 33: object missing or not visible — wrong id, privacy, or insufficient scopes.)",
                    file=sys.stderr,
                )
    except json.JSONDecodeError:
        print(body[:4000])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
