from __future__ import annotations

from email import policy
from email.parser import Parser
from pathlib import Path
from unittest.mock import patch

from src.config import Settings
from src.services.email_reporter import EmailReporter


def test_send_report_email_uses_mixed_multipart_when_attaching_csv(monkeypatch, tmp_path: Path) -> None:
    """Attachments must not sit inside multipart/alternative (Gmail shows them as raw body text)."""
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("REPORT_EMAIL", "to@example.com")
    settings = Settings()
    reporter = EmailReporter(settings)
    csv_path = tmp_path / "report_2026-04-26.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    captured: dict[str, str] = {}

    class _FakeSMTP:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, *a, **k) -> None:
            pass

        def sendmail(self, _from, _recipients, msg_string: str) -> None:
            captured["raw"] = msg_string

    with patch("src.services.email_reporter.smtplib.SMTP", _FakeSMTP):
        ok = reporter.send_report_email(
            subject="Test",
            report={"date": "2026-04-26", "total_posts": 0, "groups": []},
            analysis={"summary": "hi", "trends": [], "recommendations": []},
            csv_path=csv_path,
        )
    assert ok is True
    root = Parser(policy=policy.default).parsestr(captured["raw"])
    assert root.get_content_type() == "multipart/mixed"
    children = root.get_payload()
    assert len(children) >= 2
    assert children[0].get_content_type() == "multipart/alternative"
    alt_parts = children[0].get_payload()
    assert len(alt_parts) == 2
    assert alt_parts[0].get_content_type() == "text/plain"
    assert alt_parts[1].get_content_type() == "text/html"
    assert "attachment" in (children[1].get("Content-Disposition") or "").lower()


def test_send_report_email_alternative_only_without_attachments(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("REPORT_EMAIL", "to@example.com")
    settings = Settings()
    reporter = EmailReporter(settings)
    captured: dict[str, str] = {}

    class _FakeSMTP:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, *a, **k) -> None:
            pass

        def sendmail(self, _from, _recipients, msg_string: str) -> None:
            captured["raw"] = msg_string

    with patch("src.services.email_reporter.smtplib.SMTP", _FakeSMTP):
        ok = reporter.send_report_email(
            subject="No files",
            report={"date": "2026-04-26", "total_posts": 0, "groups": []},
            analysis={"summary": "x", "trends": [], "recommendations": []},
            csv_path=None,
            extra_attachments=None,
        )
    assert ok is True
    root = Parser(policy=policy.default).parsestr(captured["raw"])
    assert root.get_content_type() == "multipart/alternative"
