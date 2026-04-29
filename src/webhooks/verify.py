from __future__ import annotations

import hashlib
import hmac
import secrets


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Validate Meta `X-Hub-Signature-256` (sha256=...)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = signature_header.split("=", 1)[1].strip()
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        return secrets.compare_digest(expected, digest)
    except Exception:
        return False


def constant_time_equals(expected: str, supplied: str) -> bool:
    return secrets.compare_digest(expected, supplied)
