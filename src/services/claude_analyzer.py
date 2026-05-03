from __future__ import annotations

import json
from src.logging_config import get_logger
import re
from typing import Any

from anthropic import Anthropic

from src.config_anthropic import get_anthropic_settings

logger = get_logger(__name__)


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


class ClaudeAnalyzer:
    def __init__(self) -> None:
        ai = get_anthropic_settings()
        if not ai.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        self._client = Anthropic(api_key=ai.anthropic_api_key)
        self._model = ai.claude_model

    def analyze_posts(self, posts: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any]:
        if not posts:
            return {
                "summary": "No posts to analyze.",
                "trends": [],
                "hot_topics": [],
                "recommendations": [],
                "urgency_level": "low",
                "top_post_ids": [],
            }

        trimmed = []
        for p in posts[:80]:
            trimmed.append(
                {
                    "id": p.get("id"),
                    "group_id": p.get("group_id"),
                    "author_name": p.get("author_name"),
                    "text": (p.get("message") or "")[:800],
                }
            )

        prompt = f"""Analyze the following Facebook group posts.

Keywords of interest: {", ".join(keywords) if keywords else "(none specified)"}

Posts JSON:
{json.dumps(trimmed, ensure_ascii=False, indent=2)}

Return ONLY valid JSON with this exact shape:
{{
  "summary": "2-3 sentence executive summary",
  "trends": ["short trend strings"],
  "hot_topics": ["topic strings"],
  "recommendations": ["actionable strings"],
  "urgency_level": "low|medium|high",
  "top_post_ids": ["post id strings from input"]
}}
"""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            parsed = _extract_json_object(text)
            parsed.setdefault("summary", "")
            parsed.setdefault("trends", [])
            parsed.setdefault("hot_topics", [])
            parsed.setdefault("recommendations", [])
            parsed.setdefault("urgency_level", "low")
            parsed.setdefault("top_post_ids", [])
            return parsed
        except Exception as exc:
            logger.exception("Claude analysis failed: %s", exc)
            return {
                "summary": f"Analysis failed: {exc!s}",
                "trends": [],
                "hot_topics": [],
                "recommendations": [],
                "urgency_level": "unknown",
                "top_post_ids": [],
            }

    def analyze_single_post(self, post: dict[str, Any]) -> dict[str, Any]:
        text = (post.get("message") or "").strip()
        if not text:
            return {"summary": "Empty post.", "tags": []}

        prompt = f"""Summarize this Facebook post in one short paragraph and suggest 3-5 topical tags.

Post:
{text[:4000]}

Return ONLY JSON: {{"summary": "...", "tags": ["..."]}}"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        try:
            data = _extract_json_object(raw)
        except Exception:
            summary = re.sub(r"\s+", " ", raw).strip()[:500]
            data = {"summary": summary, "tags": []}
        data.setdefault("summary", "")
        data.setdefault("tags", [])
        return data
