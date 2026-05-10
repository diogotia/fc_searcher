"""Anthropic / Claude settings isolated from :class:`src.config.Settings`.

Daily reports, ``run_analyze_recent``, and optional Meta challenge vision read credentials here.
Agentic Facebook sync without Anthropic should strip ``ANTHROPIC_API_KEY`` from the environment
before imports (see ``scripts/run_agentic/run_agentic_facebook_once.py``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnthropicSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-3-5-sonnet-20241022", validation_alias="CLAUDE_MODEL")


@lru_cache
def get_anthropic_settings() -> AnthropicSettings:
    return AnthropicSettings()
