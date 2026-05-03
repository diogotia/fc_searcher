from __future__ import annotations

import os
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Intentionally no `env_file` here: `create_app()` calls `load_dotenv()` so `.env`
    # is merged into the process environment before `get_settings()` runs. Tests set
    # `RUNNING_PYTEST=1` and skip `load_dotenv()` so a repo `.env` cannot leak into pytest.
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    database_url: str = Field(
        default="sqlite:///./data/facebook_monitor.db",
        validation_alias="DATABASE_URL",
        description="SQLAlchemy URL; use sqlite:///./data/... for local/MCP (cwd = repo). Docker image sets /app/data.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = Field(default="UTC", validation_alias="TIMEZONE")

    graph_api_version: str = Field(default="v21.0", validation_alias="GRAPH_API_VERSION")
    facebook_access_token: str | None = Field(default=None, validation_alias="FACEBOOK_ACCESS_TOKEN")
    facebook_app_secret: str | None = Field(default=None, validation_alias="FACEBOOK_APP_SECRET")
    facebook_group_ids: str = Field(
        default="",
        validation_alias="FACEBOOK_GROUP_IDS",
        description="Comma-separated numeric group IDs to monitor",
    )
    facebook_mock_feed_json: str | None = Field(
        default=None,
        validation_alias="FACEBOOK_MOCK_FEED_JSON",
        description="Path to JSON file (Graph feed shape with `data` array) for offline dev without calling Meta",
    )
    facebook_sync_mode: Literal["groups", "me"] = Field(
        default="groups",
        validation_alias="FACEBOOK_SYNC_MODE",
        description="groups = /{group-id}/feed; me = /me/feed (no FACEBOOK_GROUP_IDS required)",
    )

    smtp_server: str = Field(default="smtp.gmail.com", validation_alias="SMTP_SERVER")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, validation_alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    report_email: str | None = Field(default=None, validation_alias="REPORT_EMAIL")
    report_email_cc: str | None = Field(default=None, validation_alias="REPORT_EMAIL_CC")

    webhook_verify_token: str | None = Field(default=None, validation_alias="WEBHOOK_VERIFY_TOKEN")

    report_cron: str = Field(default="0 7 * * *", validation_alias="REPORT_CRON")
    sync_cron: str = Field(default="15 */6 * * *", validation_alias="SYNC_CRON")
    enable_scheduler: bool = Field(default=True, validation_alias="ENABLE_SCHEDULER")
    enable_public_post_search: bool = Field(
        default=False,
        validation_alias="ENABLE_PUBLIC_POST_SEARCH",
        description="When true, GET /search queries stored posts without admin auth (use only behind a reverse proxy / VPN)",
    )
    enable_browser_search_sync: bool = Field(default=False, validation_alias="ENABLE_BROWSER_SEARCH_SYNC")
    browser_search_query: str = Field(default="job", validation_alias="BROWSER_SEARCH_QUERY")
    browser_in_group_search_query: str = Field(
        default="",
        validation_alias=AliasChoices("BROWSER_IN_GROUP_SEARCH_QUERY", "browser_in_group_search_query"),
        description="Comma-separated tokens: each becomes /groups/{id}/search/?q= with BROWSER_SEARCH_QUERY prefixed. "
        "Single token not equal to BROWSER_SEARCH_QUERY is prefixed. Empty = use BROWSER_SEARCH_QUERY only.",
    )
    browser_group_scan_limit: int = Field(
        default=20,
        validation_alias="BROWSER_GROUP_SCAN_LIMIT",
        description="Max groups taken from Facebook /search/groups (1..100). BROWSER_SEED_GROUP_URLS are always kept in full, then this many discovery groups are added.",
    )
    browser_post_limit_per_group: int = Field(default=25, validation_alias="BROWSER_POST_LIMIT_PER_GROUP")
    browser_headless: bool = Field(default=False, validation_alias="BROWSER_HEADLESS")
    browser_seed_group_urls: str = Field(
        default="",
        validation_alias="BROWSER_SEED_GROUP_URLS",
        description="Comma-separated facebook.com/groups/... URLs (or numeric ids) scanned first before group search results",
    )
    playwright_storage_state_path: str | None = Field(
        default=None,
        validation_alias="PLAYWRIGHT_STORAGE_STATE_PATH",
    )
    browser_search_timeout_seconds: int = Field(
        default=45,
        validation_alias="BROWSER_SEARCH_TIMEOUT_SECONDS",
    )
    browser_post_publication_year: int | None = Field(
        default=None,
        validation_alias="BROWSER_POST_PUBLICATION_YEAR",
        description="When set (or 'auto' = current UTC year), browser sync and daily reports filter by publication time. "
        "If BROWSER_POST_PUBLICATION_MONTH is unset: keep posts whose inferred year equals this value "
        "(Russian/ISO/г. in the post header first, else created_time year). "
        "If MONTH is set: keep posts on or after that calendar date (see BROWSER_POST_PUBLICATION_DAY). "
        "Posts with an unparsed year are dropped unless BROWSER_POST_PUBLICATION_KEEP_UNKNOWN_YEAR=true. "
        "Unset = no year filter.",
    )
    browser_post_publication_keep_unknown_year: bool = Field(
        default=False,
        validation_alias="BROWSER_POST_PUBLICATION_KEEP_UNKNOWN_YEAR",
        description="When true with BROWSER_POST_PUBLICATION_YEAR, posts with no parsable publication year are kept.",
    )
    browser_post_publication_month: int | None = Field(
        default=None,
        validation_alias="BROWSER_POST_PUBLICATION_MONTH",
        description="With BROWSER_POST_PUBLICATION_YEAR, optional 1–12: keep posts on or after that month (UTC date). "
        "Day defaults to 1 unless BROWSER_POST_PUBLICATION_DAY is set (e.g. 27.04.2026 → year=2026, month=4, day=27). "
        "Unset = only the year filter applies (exact year match).",
    )
    browser_post_publication_day: int | None = Field(
        default=None,
        validation_alias="BROWSER_POST_PUBLICATION_DAY",
        description="With year and month, optional 1–31 for the minimum publication date (inclusive). "
        "Unset with month set = first day of that month.",
    )
    facebook_web_login: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FACEBOOK_WEB_LOGIN", "facebook_web_login"),
        description="Optional email or phone for Playwright web login (browser search); pair with FACEBOOK_WEB_PASSWORD",
    )
    facebook_web_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FACEBOOK_WEB_PASSWORD", "facebook_web_password"),
        description="Optional password for Playwright web login — high risk in .env; prefer manual login or storage state when possible",
        repr=False,
    )
    enable_browser_meta_challenge_vision: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ENABLE_BROWSER_META_CHALLENGE_VISION",
            "enable_browser_meta_challenge_vision",
        ),
        description="When true and ANTHROPIC_API_KEY is set, try Claude vision + ArrowRight/Submit on Meta post-login visual puzzles (fragile; off by default)",
    )
    enable_agentic_facebook_sync: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_AGENTIC_FACEBOOK_SYNC", "enable_agentic_facebook_sync"),
        description="Opt-in separate agentic Facebook browser flow; does not affect ENABLE_BROWSER_SEARCH_SYNC.",
    )
    agentic_facebook_output_dir: str = Field(
        default="output/agentic_facebook",
        validation_alias=AliasChoices("AGENTIC_FACEBOOK_OUTPUT_DIR", "agentic_facebook_output_dir"),
        description="Artifact root for the isolated agentic Facebook flow.",
    )
    agentic_facebook_source: str = Field(
        default="playwright_agentic",
        validation_alias=AliasChoices("AGENTIC_FACEBOOK_SOURCE", "agentic_facebook_source"),
        description="Post.source value used for rows written by the agentic Facebook flow.",
    )

    @field_validator(
        "enable_scheduler",
        "enable_public_post_search",
        "enable_browser_search_sync",
        "browser_headless",
        "enable_browser_meta_challenge_vision",
        "browser_post_publication_keep_unknown_year",
        "enable_agentic_facebook_sync",
        mode="before",
    )
    @classmethod
    def parse_bool(cls, value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    monitor_keywords: str = Field(
        default="",
        validation_alias="MONITOR_KEYWORDS",
        description="Comma-separated keywords to highlight in reports",
    )

    reports_dir: str = Field(default="/app/reports", validation_alias="REPORTS_DIR")
    admin_token: str | None = Field(default=None, validation_alias="ADMIN_TOKEN")

    @field_validator("facebook_sync_mode", mode="before")
    @classmethod
    def normalize_sync_mode(cls, v: object) -> str:
        s = str(v or "groups").strip().lower()
        return s if s in {"groups", "me"} else "groups"

    @field_validator(
        "facebook_group_ids",
        "monitor_keywords",
        "browser_search_query",
        "browser_in_group_search_query",
        "browser_seed_group_urls",
        "agentic_facebook_output_dir",
        "agentic_facebook_source",
        mode="before",
    )
    @classmethod
    def strip_string(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("facebook_web_login", mode="before")
    @classmethod
    def strip_optional_login(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("facebook_web_password", mode="before")
    @classmethod
    def coerce_web_password(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v)
        return s if s else None

    def facebook_web_credentials_configured(self) -> bool:
        return bool(self.facebook_web_login and self.facebook_web_password)

    @field_validator("browser_group_scan_limit", mode="before")
    @classmethod
    def clamp_browser_group_scan_limit(cls, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 20
        return max(1, min(parsed, 100))

    @field_validator("browser_post_limit_per_group", mode="before")
    @classmethod
    def clamp_browser_post_limit_per_group(cls, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 25
        return max(1, min(parsed, 100))

    @field_validator("browser_post_publication_year", mode="before")
    @classmethod
    def parse_browser_post_publication_year(cls, value: object) -> int | None:
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s or s in ("off", "false", "no", "0", "none", "disable", "disabled"):
            return None
        if s == "auto":
            return datetime.now(timezone.utc).year
        try:
            y = int(s, 10)
        except ValueError:
            return None
        if 1990 <= y <= 2100:
            return y
        return None

    @field_validator("browser_post_publication_month", mode="before")
    @classmethod
    def parse_browser_post_publication_month(cls, value: object) -> int | None:
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s or s in ("off", "false", "no", "0", "none", ""):
            return None
        try:
            m = int(s, 10)
        except ValueError:
            return None
        if 1 <= m <= 12:
            return m
        return None

    @field_validator("browser_post_publication_day", mode="before")
    @classmethod
    def parse_browser_post_publication_day(cls, value: object) -> int | None:
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s or s in ("off", "false", "no", "0", "none", ""):
            return None
        try:
            d = int(s, 10)
        except ValueError:
            return None
        if 1 <= d <= 31:
            return d
        return None

    @model_validator(mode="after")
    def validate_publication_month_day(self) -> Settings:
        y, m, d = self.browser_post_publication_year, self.browser_post_publication_month, self.browser_post_publication_day
        if m is not None and y is None:
            raise ValueError("BROWSER_POST_PUBLICATION_MONTH requires BROWSER_POST_PUBLICATION_YEAR to be set")
        if d is not None and m is None:
            raise ValueError("BROWSER_POST_PUBLICATION_DAY requires BROWSER_POST_PUBLICATION_MONTH to be set")
        if y is not None and m is not None:
            day = d if d is not None else 1
            try:
                date(y, m, day)
            except ValueError as e:
                raise ValueError("Invalid BROWSER_POST_PUBLICATION_YEAR/MONTH/DAY calendar date") from e
        return self

    @field_validator("browser_search_timeout_seconds", mode="before")
    @classmethod
    def clamp_browser_timeout_seconds(cls, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 45
        return max(10, min(parsed, 300))

    def group_id_list(self) -> list[str]:
        return [g.strip() for g in self.facebook_group_ids.split(",") if g.strip()]

    def keyword_list(self) -> list[str]:
        return [k.strip() for k in self.monitor_keywords.split(",") if k.strip()]

    def facebook_graph_ready(self) -> bool:
        """True if sync can run: real token, or mock feed JSON path is set."""
        return bool(self.facebook_access_token) or bool((self.facebook_mock_feed_json or "").strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_caches() -> None:
    """Invalidate both main settings and Anthropic settings (same env, separate caches)."""
    get_settings.cache_clear()
    from src.config_anthropic import get_anthropic_settings

    get_anthropic_settings.cache_clear()


def reload_settings_if_dotenv_mounted() -> None:
    """If host `.env` is mounted at `/app/.env`, merge it into `os.environ` and invalidate settings cache.

    Docker Compose otherwise injects env only at container **create** time; mounting `.env` lets you
    change `FACEBOOK_GROUP_IDS` (etc.) without rebuilding the image. Admin and webhook handlers call this.
    """
    if os.environ.get("RUNNING_PYTEST") == "1":
        return
    from pathlib import Path

    from dotenv import load_dotenv

    path = Path("/app/.env")
    if not path.is_file():
        return
    load_dotenv(path, override=True)
    clear_settings_caches()
