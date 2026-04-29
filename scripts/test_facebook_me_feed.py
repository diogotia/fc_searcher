#!/usr/bin/env python3
"""Test ``GET /me/feed`` with ``FACEBOOK_ACCESS_TOKEN`` (when not using groups).

Set in .env:
  FACEBOOK_ACCESS_TOKEN
  GRAPH_API_VERSION

Meta often requires ``user_posts`` (or current equivalent) — not only ``public_profile``.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from load_repo_env import load_dotenv_file


def main() -> int:
    load_dotenv_file()
    token = os.environ.get("FACEBOOK_ACCESS_TOKEN", "").strip()
    ver = os.environ.get("GRAPH_API_VERSION", "v21.0").strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"
    if not token:
        print("error: FACEBOOK_ACCESS_TOKEN not set", file=sys.stderr)
        return 1

    params = urllib.parse.urlencode(
        {
            "fields": "id,message,created_time",
            "limit": "5",
            "access_token": token,
        }
    )
    url = f"https://graph.facebook.com/{ver}/me/feed?{params}"
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
        print(json.dumps(json.loads(body), indent=2, ensure_ascii=False)[:6000])
    except json.JSONDecodeError:
        print(body[:6000])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
