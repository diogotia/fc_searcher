from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from src.config import Settings
from src.logging_config import get_logger
from src.services.rate_limit import request_with_graph_backoff

logger = get_logger(__name__)

# Stored in DB `posts.group_id` when syncing `GET /me/feed` (not a Facebook group id).
USER_FEED_GROUP_ID = "user"


def _parse_fb_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Graph returns ISO8601 like 2024-01-15T12:00:00+0000
        from dateutil import parser as date_parser

        return date_parser.parse(value)
    except Exception:
        return None


class FacebookClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._mock_path = (settings.facebook_mock_feed_json or "").strip()
        if self._mock_path:
            self._token = settings.facebook_access_token or "mock"
            self._base = ""
            return
        if not settings.facebook_access_token:
            raise ValueError("FACEBOOK_ACCESS_TOKEN is not configured")
        self._token = settings.facebook_access_token
        ver = settings.graph_api_version.strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        self._base = f"https://graph.facebook.com/{ver}"

    def _mock_feed_items(self, group_id: str) -> tuple[list[dict[str, Any]], str | None]:
        """Load Graph-shaped JSON; return (raw items, error or None)."""
        path = Path(self._mock_path).expanduser()
        if not path.is_file():
            return [], f"FACEBOOK_MOCK_FEED_JSON not found: {path.resolve()}"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [], f"mock JSON read error: {exc}"
        items = payload.get("data") if isinstance(payload, dict) else payload
        if items is None:
            return [], "mock JSON must be an object with `data` array or a top-level array"
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return [], "mock JSON `data` must be a list"
        return items, None

    def fetch_group_feed_with_diagnostics(
        self,
        group_id: str,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch `/{group-id}/feed` and return posts plus first-page HTTP status / Meta error text."""
        if self._mock_path:
            items, err = self._mock_feed_items(group_id)
            if err:
                return {
                    "posts": [],
                    "http_status": 500,
                    "error": err,
                    "raw_items_first_page": None,
                }
            mock_posts: list[dict[str, Any]] = []
            for idx, item in enumerate(items[:limit]):
                if not isinstance(item, dict):
                    continue
                from_obj = item.get("from") or {}
                oid = item.get("id")
                if oid is None:
                    oid = f"mock_{idx}"
                pid = str(oid) if str(oid).startswith(f"{group_id}_") else f"{group_id}_{oid}"
                pu = item.get("permalink_url")
                mock_posts.append(
                    {
                        "id": pid,
                        "group_id": group_id,
                        "message": item.get("message") or "",
                        "author_id": from_obj.get("id"),
                        "author_name": from_obj.get("name"),
                        "created_time": _parse_fb_time(item.get("created_time")),
                        "permalink_url": str(pu).strip() if pu else None,
                        "raw_json": item,
                    }
                )
            clean = [p for p in mock_posts if p.get("id")]
            return {
                "posts": clean,
                "http_status": 200,
                "error": None,
                "raw_items_first_page": len(clean),
            }

        fields = "id,message,from,created_time,permalink_url"
        url = f"{self._base}/{group_id}/feed"
        params: dict[str, str | int] = {
            "fields": fields,
            "limit": min(limit, 100),
            "access_token": self._token,
        }
        posts: list[dict[str, Any]] = []
        first_status: int | None = None
        first_error: str | None = None
        last_payload: dict[str, Any] = {}
        first_ok_payload: dict[str, Any] | None = None

        while url and len(posts) < limit:
            def do_request() -> requests.Response:
                return requests.get(url, params=params, timeout=30)

            resp = request_with_graph_backoff(do_request)
            if first_status is None:
                first_status = resp.status_code
            if resp.status_code != 200:
                first_error = self._graph_error_snippet(resp)
                logger.warning(
                    "Graph API error for group %s: %s %s",
                    group_id,
                    resp.status_code,
                    resp.text[:500],
                )
                break
            last_payload = resp.json()
            if first_ok_payload is None:
                first_ok_payload = last_payload
            for item in last_payload.get("data", []):
                from_obj = item.get("from") or {}
                pu = item.get("permalink_url")
                posts.append(
                    {
                        "id": item.get("id"),
                        "group_id": group_id,
                        "message": item.get("message") or "",
                        "author_id": from_obj.get("id"),
                        "author_name": from_obj.get("name"),
                        "created_time": _parse_fb_time(item.get("created_time")),
                        "permalink_url": str(pu).strip() if pu else None,
                        "raw_json": item,
                    }
                )
                if len(posts) >= limit:
                    break

            paging = last_payload.get("paging") or {}
            next_url = paging.get("next")
            if not next_url or len(posts) >= limit:
                break
            url = next_url
            params = {}

        clean = [p for p in posts if p.get("id")]
        return {
            "posts": clean,
            "http_status": first_status or 0,
            "error": first_error,
            "raw_items_first_page": len(first_ok_payload.get("data", []))
            if first_status == 200 and first_ok_payload
            else None,
        }

    def fetch_me_feed_with_diagnostics(self, *, limit: int = 50) -> dict[str, Any]:
        """Fetch ``/me/feed`` (authenticated user's posts). Requires appropriate Meta permissions (often ``user_posts``)."""
        gid = USER_FEED_GROUP_ID
        if self._mock_path:
            items, err = self._mock_feed_items(gid)
            if err:
                return {
                    "posts": [],
                    "http_status": 500,
                    "error": err,
                    "raw_items_first_page": None,
                }
            mock_posts: list[dict[str, Any]] = []
            for idx, item in enumerate(items[:limit]):
                if not isinstance(item, dict):
                    continue
                from_obj = item.get("from") or {}
                oid = item.get("id")
                if oid is None:
                    oid = f"mock_{idx}"
                pid = str(oid) if str(oid).startswith(f"{gid}_") else f"{gid}_{oid}"
                pu = item.get("permalink_url")
                mock_posts.append(
                    {
                        "id": pid,
                        "group_id": gid,
                        "message": item.get("message") or "",
                        "author_id": from_obj.get("id"),
                        "author_name": from_obj.get("name"),
                        "created_time": _parse_fb_time(item.get("created_time")),
                        "permalink_url": str(pu).strip() if pu else None,
                        "raw_json": item,
                    }
                )
            clean = [p for p in mock_posts if p.get("id")]
            return {
                "posts": clean,
                "http_status": 200,
                "error": None,
                "raw_items_first_page": len(clean),
            }

        fields = "id,message,from,created_time,permalink_url"
        url = f"{self._base}/me/feed"
        params: dict[str, str | int] = {
            "fields": fields,
            "limit": min(limit, 100),
            "access_token": self._token,
        }
        posts: list[dict[str, Any]] = []
        first_status: int | None = None
        first_error: str | None = None
        last_payload: dict[str, Any] = {}
        first_ok_payload: dict[str, Any] | None = None

        while url and len(posts) < limit:
            def do_request() -> requests.Response:
                return requests.get(url, params=params, timeout=30)

            resp = request_with_graph_backoff(do_request)
            if first_status is None:
                first_status = resp.status_code
            if resp.status_code != 200:
                first_error = self._graph_error_snippet(resp)
                logger.warning("Graph API error for me/feed: %s %s", resp.status_code, resp.text[:500])
                break
            last_payload = resp.json()
            if first_ok_payload is None:
                first_ok_payload = last_payload
            for item in last_payload.get("data", []):
                from_obj = item.get("from") or {}
                pu = item.get("permalink_url")
                posts.append(
                    {
                        "id": item.get("id"),
                        "group_id": gid,
                        "message": item.get("message") or "",
                        "author_id": from_obj.get("id"),
                        "author_name": from_obj.get("name"),
                        "created_time": _parse_fb_time(item.get("created_time")),
                        "permalink_url": str(pu).strip() if pu else None,
                        "raw_json": item,
                    }
                )
                if len(posts) >= limit:
                    break

            paging = last_payload.get("paging") or {}
            next_url = paging.get("next")
            if not next_url or len(posts) >= limit:
                break
            url = next_url
            params = {}

        clean = [p for p in posts if p.get("id")]
        return {
            "posts": clean,
            "http_status": first_status or 0,
            "error": first_error,
            "raw_items_first_page": len(first_ok_payload.get("data", []))
            if first_status == 200 and first_ok_payload
            else None,
        }

    def fetch_me_feed(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.fetch_me_feed_with_diagnostics(limit=limit)["posts"]

    @staticmethod
    def _graph_error_snippet(resp: requests.Response) -> str:
        try:
            body = resp.json()
            err = body.get("error") or {}
            msg = err.get("message") or err.get("error_user_msg") or resp.text
            return str(msg)[:400]
        except Exception:
            return (resp.text or "")[:400]

    def fetch_group_feed(self, group_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return normalized post dicts from Graph `/{group-id}/feed`."""
        return self.fetch_group_feed_with_diagnostics(group_id, limit=limit)["posts"]

    def search_group_feed_keyword(
        self,
        group_id: str,
        keyword: str,
        *,
        max_posts_scan: int = 100,
    ) -> list[dict[str, Any]]:
        """Client-side filter of recent feed posts containing keyword (case-insensitive)."""
        keyword_lower = keyword.lower()
        matched: list[dict[str, Any]] = []
        for post in self.fetch_group_feed(group_id, limit=max_posts_scan):
            msg = (post.get("message") or "").lower()
            if keyword_lower in msg:
                matched.append({**post, "matched_keyword": keyword})
        return matched

    def search_me_feed_keyword(
        self,
        keyword: str,
        *,
        max_posts_scan: int = 100,
    ) -> list[dict[str, Any]]:
        """Client-side filter of recent ``/me/feed`` posts containing keyword (case-insensitive)."""
        keyword_lower = keyword.lower()
        matched: list[dict[str, Any]] = []
        for post in self.fetch_me_feed(limit=max_posts_scan):
            msg = (post.get("message") or "").lower()
            if keyword_lower in msg:
                matched.append({**post, "matched_keyword": keyword})
        return matched
