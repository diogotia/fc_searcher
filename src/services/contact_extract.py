"""Extract phone-like strings and email addresses from post text; normalize for deduplication."""

from __future__ import annotations

import re
from typing import Iterable

# Practical subset; avoids matching inside long unbroken tokens when possible.
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+)\b"
)
# Chunks that start with a digit or + and contain mostly phone-like characters.
_PHONE_CHUNK_RE = re.compile(r"(?:\+?\d[\d\s().\-]{6,22}\d)")


def normalize_email_key(raw: str) -> str:
    return raw.strip().lower()


def normalize_phone_key(raw: str) -> str:
    return _normalize_phone_digits(raw)


def _normalize_phone_digits(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def extract_emails(text: str | None) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _EMAIL_RE.finditer(text):
        raw = m.group(1).strip()
        if not raw or ".." in raw:
            continue
        key = normalize_email_key(raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


def _looks_like_date_slash(s: str) -> bool:
    """Reject e.g. 12/34/5678 mistaken as a phone."""
    if s.count("/") != 2:
        return False
    parts = [p for p in s.split("/") if p.isdigit()]
    return len(parts) == 3 and all(len(p) <= 4 for p in parts)


def extract_phones(text: str | None) -> list[str]:
    if not text:
        return []
    seen_digits: set[str] = set()
    out: list[str] = []
    for m in _PHONE_CHUNK_RE.finditer(text):
        chunk = m.group(0).strip()
        if not chunk or _looks_like_date_slash(chunk):
            continue
        digits = _normalize_phone_digits(chunk)
        if len(digits) < 8 or len(digits) > 15:
            continue
        if len(set(digits)) < 2:
            continue
        if digits in seen_digits:
            continue
        seen_digits.add(digits)
        cleaned = re.sub(r"\s+", " ", chunk)
        out.append(cleaned)
    return out


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out
