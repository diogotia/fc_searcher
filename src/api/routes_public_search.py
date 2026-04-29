from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from src.config import Settings, get_settings, reload_settings_if_dotenv_mounted
from src.services.post_search import search_stored_posts

bp = Blueprint("public_search", __name__)


def _settings() -> Settings:
    reload_settings_if_dotenv_mounted()
    return get_settings()


@bp.get("/search")
def public_search_posts() -> tuple[Any, int]:
    """Unauthenticated search over stored `Post.message` when `ENABLE_PUBLIC_POST_SEARCH=true`."""
    settings = _settings()
    if not settings.enable_public_post_search:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": (
                        "public post search is disabled "
                        "(set ENABLE_PUBLIC_POST_SEARCH=true to enable GET /search)"
                    ),
                }
            ),
            403,
        )
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "query param q is required"}), 400
    raw_limit = request.args.get("limit", "50")
    try:
        limit = int(raw_limit)
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    group_raw = request.args.get("group_id")
    group_id = group_raw.strip() if group_raw else None
    posts = search_stored_posts(query=q, group_id=group_id, limit=limit)
    return jsonify({"ok": True, "count": len(posts), "posts": posts}), 200
