from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from flask import Blueprint, abort, request
from sqlalchemy import select

from src.config import Settings, get_settings, reload_settings_if_dotenv_mounted
from src.db.db_models import WebhookDelivery
from src.db.session import get_session
from src.services.pipeline import upsert_posts
from src.webhooks.verify import constant_time_equals, verify_meta_signature

logger = logging.getLogger(__name__)

bp = Blueprint("facebook_webhook", __name__)


def _settings() -> Settings:
    reload_settings_if_dotenv_mounted()
    return get_settings()


def _payload_idempotency_key(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _extract_posts_from_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    obj = data.get("object")
    if obj not in {"group", "page"}:
        return posts
    for entry in data.get("entry", []) or []:
        gid = entry.get("id")
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            post_id = value.get("post_id") or value.get("id")
            if not post_id:
                continue
            link = value.get("permalink_url") or value.get("post_permalink") or value.get("url")
            posts.append(
                {
                    "id": str(post_id),
                    "group_id": str(gid or value.get("group_id") or ""),
                    "message": value.get("message") or "",
                    "author_id": str(value.get("from", {}).get("id"))
                    if isinstance(value.get("from"), dict) and value["from"].get("id")
                    else None,
                    "author_name": (value.get("from") or {}).get("name") if isinstance(value.get("from"), dict) else None,
                    "created_time": None,
                    "permalink_url": str(link).strip() if link else None,
                    "raw_json": value,
                }
            )
    return posts


@bp.route("/webhook/facebook", methods=["GET", "POST"])
def facebook_webhook() -> tuple[str, int]:
    settings = _settings()

    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token and challenge and settings.webhook_verify_token:
            if constant_time_equals(settings.webhook_verify_token, token):
                return challenge, 200
        abort(403)

    raw = request.get_data(cache=False, as_text=False)
    if not settings.facebook_app_secret:
        logger.error("Webhook POST rejected: FACEBOOK_APP_SECRET not configured")
        abort(503)

    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw, sig, settings.facebook_app_secret):
        logger.warning("Invalid webhook signature")
        abort(403)

    key = _payload_idempotency_key(raw)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        abort(400)

    with get_session() as session:
        existing = session.execute(
            select(WebhookDelivery).where(WebhookDelivery.idempotency_key == key)
        ).scalar_one_or_none()
        if existing:
            return "OK", 200

        session.add(WebhookDelivery(idempotency_key=key, payload_digest=key))
        posts = _extract_posts_from_payload(data)
        if posts:
            upsert_posts(session, posts, source="webhook")

    return "OK", 200
