"""Application-level exceptions."""

from __future__ import annotations

from typing import Any


class FacebookMonitorError(Exception):
    """Base exception for application errors."""

    error_code: str = "UNKNOWN_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        self.context = context or {}


class FacebookAPIError(FacebookMonitorError):
    """Facebook/Meta API errors."""

    error_code = "FACEBOOK_API_ERROR"
    http_status = 502


class FacebookAuthenticationError(FacebookMonitorError):
    """Authentication/token errors."""

    error_code = "FACEBOOK_AUTH_ERROR"
    http_status = 401


class BrowserAutomationError(FacebookMonitorError):
    """Playwright/browser automation errors."""

    error_code = "BROWSER_ERROR"
    http_status = 500


class ConfigurationError(FacebookMonitorError):
    """Configuration errors."""

    error_code = "CONFIG_ERROR"
    http_status = 400


class DatabaseError(FacebookMonitorError):
    """Database errors."""

    error_code = "DATABASE_ERROR"
    http_status = 500
