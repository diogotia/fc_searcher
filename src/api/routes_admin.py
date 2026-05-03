from __future__ import annotations

from src.logging_config import get_logger
import secrets
from collections.abc import Callable
from typing import Any

from flask import Blueprint, abort, jsonify, request

from src.config import Settings, get_settings, reload_settings_if_dotenv_mounted
from src.services.agentic_facebook import run_agentic_facebook_sync
from src.services.pipeline import (
    run_analyze_recent,
    run_browser_search_sync,
    run_daily_report,
    run_daily_report_with_latest_browser_html_email,
    run_sync,
    send_browser_search_html_report_email,
)
from src.services.post_search import search_stored_posts

logger = get_logger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _settings() -> Settings:
    reload_settings_if_dotenv_mounted()
    return get_settings()


def _require_admin() -> None:
    settings = _settings()
    if not settings.admin_token:
        abort(503, description="ADMIN_TOKEN is not configured")
    header = request.headers.get("X-Admin-Token", "")
    auth = request.headers.get("Authorization", "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.lower().startswith("bearer ") else ""
    if not secrets.compare_digest(settings.admin_token, header) and not secrets.compare_digest(
        settings.admin_token, bearer
    ):
        abort(401, description="Invalid admin token")


def _safe_run(name: str, fn: Callable[[], dict[str, Any]]) -> tuple[Any, int]:
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 — return JSON for operators
        logger.exception("%s failed", name)
        return jsonify({"ok": False, "error": str(exc), "step": name}), 500
    return jsonify(result), 200 if result.get("ok") else 400


@bp.post("/sync")
def admin_sync() -> tuple[dict[str, Any], int]:
    _require_admin()
    return _safe_run("sync", run_sync)


@bp.post("/report")
def admin_report() -> tuple[dict[str, Any], int]:
    _require_admin()
    return _safe_run("report", run_daily_report)


@bp.post("/report-browser-html")
def admin_report_browser_html() -> tuple[Any, int]:
    """Email ``index.html`` from ``report/search_<UTC>/`` (Playwright HTML export), not the daily DB CSV."""
    _require_admin()
    payload = request.get_json(silent=True) or {}
    folder = payload.get("search_folder") or payload.get("html_report_dir")
    if folder is None or not str(folder).strip():
        return jsonify({"ok": False, "error": "JSON body needs search_folder or html_report_dir"}), 400
    sf = str(folder).strip()
    return _safe_run(
        "report-browser-html",
        lambda: send_browser_search_html_report_email(_settings(), search_folder=sf),
    )


@bp.post("/report-browser-html-last")
def admin_report_browser_html_last() -> tuple[Any, int]:
    """Daily DB report (same JSON as ``POST /admin/report``) plus email latest ``report/search_*`` HTML."""
    _require_admin()
    return _safe_run(
        "report-browser-html-last",
        lambda: run_daily_report_with_latest_browser_html_email(_settings()),
    )


@bp.post("/analyze")
def admin_analyze() -> tuple[dict[str, Any], int]:
    _require_admin()
    return _safe_run("analyze", run_analyze_recent)


@bp.post("/browser-search-sync")
def admin_browser_search_sync() -> tuple[Any, int]:
    _require_admin()
    payload = request.get_json(silent=True) or {}
    query = payload.get("query")
    in_group_query = payload.get("in_group_query")
    raw_igq = payload.get("in_group_queries")
    in_group_queries: list[str] | None = None
    if isinstance(raw_igq, list):
        in_group_queries = [str(x).strip() for x in raw_igq if str(x).strip()]
        if not in_group_queries:
            in_group_queries = None
    raw_gmc = payload.get("global_message_contains")
    global_message_contains = str(raw_gmc).strip() if raw_gmc is not None else None
    if not global_message_contains:
        global_message_contains = None
    group_limit = payload.get("group_limit")
    post_limit_per_group = payload.get("post_limit_per_group")
    raw_seed = payload.get("seed_group_urls")
    if raw_seed is None:
        seed_group_urls = None
    elif isinstance(raw_seed, list):
        seed_group_urls = ",".join(str(x).strip() for x in raw_seed if str(x).strip())
    else:
        seed_group_urls = str(raw_seed).strip() or None
    return _safe_run(
        "browser-search-sync",
        lambda: run_browser_search_sync(
            query=query,
            in_group_query=in_group_query,
            in_group_queries=in_group_queries,
            group_limit=group_limit,
            post_limit_per_group=post_limit_per_group,
            seed_group_urls=seed_group_urls,
            global_message_contains=global_message_contains,
        ),
    )


@bp.post("/agentic-facebook-sync")
def admin_agentic_facebook_sync() -> tuple[Any, int]:
    _require_admin()
    payload = request.get_json(silent=True) or {}
    query = payload.get("query")
    in_group_query = payload.get("in_group_query")
    raw_igq = payload.get("in_group_queries")
    in_group_queries: list[str] | None = None
    if isinstance(raw_igq, list):
        in_group_queries = [str(x).strip() for x in raw_igq if str(x).strip()]
        if not in_group_queries:
            in_group_queries = None
    raw_gmc = payload.get("global_message_contains")
    global_message_contains = str(raw_gmc).strip() if raw_gmc is not None else None
    if not global_message_contains:
        global_message_contains = None
    group_limit = payload.get("group_limit")
    post_limit_per_group = payload.get("post_limit_per_group")
    raw_seed = payload.get("seed_group_urls")
    if raw_seed is None:
        seed_group_urls = None
    elif isinstance(raw_seed, list):
        seed_group_urls = ",".join(str(x).strip() for x in raw_seed if str(x).strip())
    else:
        seed_group_urls = str(raw_seed).strip() or None
    raw_exact = payload.get("in_group_exact_keywords")
    if raw_exact is None:
        in_group_exact_keywords = False
    elif isinstance(raw_exact, bool):
        in_group_exact_keywords = raw_exact
    elif isinstance(raw_exact, str):
        in_group_exact_keywords = raw_exact.strip().lower() in {"1", "true", "yes", "on"}
    else:
        in_group_exact_keywords = bool(raw_exact)
    raw_fb_year = payload.get("facebook_ui_year_filter")
    if raw_fb_year is None:
        facebook_ui_year_filter = False
    elif isinstance(raw_fb_year, bool):
        facebook_ui_year_filter = raw_fb_year
    elif isinstance(raw_fb_year, str):
        facebook_ui_year_filter = raw_fb_year.strip().lower() in {"1", "true", "yes", "on"}
    else:
        facebook_ui_year_filter = bool(raw_fb_year)
    return _safe_run(
        "agentic-facebook-sync",
        lambda: run_agentic_facebook_sync(
            _settings(),
            query=query,
            in_group_query=in_group_query,
            in_group_queries=in_group_queries,
            group_limit=group_limit,
            post_limit_per_group=post_limit_per_group,
            seed_group_urls=seed_group_urls,
            global_message_contains=global_message_contains,
            in_group_exact_keywords=in_group_exact_keywords,
            facebook_ui_year_filter=facebook_ui_year_filter,
        ),
    )


@bp.get("/posts/search")
def admin_posts_search() -> tuple[Any, int]:
    """Search stored post bodies by substring (`q`). Optional `group_id`, `limit` (1–200)."""
    _require_admin()
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
