from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.config import Settings, get_settings, reload_settings_if_dotenv_mounted
from src.config_anthropic import get_anthropic_settings

bp = Blueprint("health", __name__)


def _settings() -> Settings:
    reload_settings_if_dotenv_mounted()
    return get_settings()


@bp.get("/health")
def health() -> tuple[dict, int]:
    settings = _settings()
    group_ids = settings.group_id_list()
    post_rules = {
        r.rule
        for r in current_app.url_map.iter_rules()
        if r.methods and "POST" in r.methods
    }
    body = {
        "status": "ok",
        "post_admin_report_browser_html_last": "/admin/report-browser-html-last" in post_rules,
        "facebook_configured": settings.facebook_graph_ready(),
        "facebook_mock_feed_json": bool((settings.facebook_mock_feed_json or "").strip()),
        "facebook_sync_mode": settings.facebook_sync_mode,
        "facebook_group_ids_count": len(group_ids),
        "anthropic_configured": bool(get_anthropic_settings().anthropic_api_key),
        "smtp_configured": bool(settings.smtp_user and settings.smtp_password and settings.report_email),
        "webhook_verify_configured": bool(settings.webhook_verify_token and settings.facebook_app_secret),
        "database_url_scheme": settings.database_url.split(":", 1)[0],
        "enable_public_post_search": settings.enable_public_post_search,
        "enable_browser_search_sync": settings.enable_browser_search_sync,
        "enable_agentic_facebook_sync": settings.enable_agentic_facebook_sync,
        "browser_search_query": settings.browser_search_query,
        "browser_headless": settings.browser_headless,
        "browser_seed_group_urls_configured": bool((settings.browser_seed_group_urls or "").strip()),
    }
    return jsonify(body), 200


@bp.get("/metrics")
def metrics() -> Response:
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)
