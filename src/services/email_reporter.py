from __future__ import annotations

import csv
import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import Settings

logger = logging.getLogger(__name__)


class EmailReporter:
    def __init__(self, settings: Settings, templates_dir: str | None = None) -> None:
        self._settings = settings
        if templates_dir:
            base = templates_dir
        else:
            base = str(Path(__file__).resolve().parent.parent.parent / "templates")
        self._env = Environment(
            loader=FileSystemLoader(str(Path(base).resolve())),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render_html(self, report: dict, analysis: dict) -> str:
        template = self._env.get_template("report.html.j2")
        return template.render(report=report, analysis=analysis)

    def write_csv(self, rows: list[dict], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def send_report_email(
        self,
        *,
        subject: str,
        report: dict,
        analysis: dict,
        csv_path: Path | None = None,
        extra_attachments: list[Path] | None = None,
    ) -> bool:
        user = self._settings.smtp_user
        password = self._settings.smtp_password
        to_addr = self._settings.report_email
        if not user or not password or not to_addr:
            logger.warning("SMTP or REPORT_EMAIL not configured; skip send")
            return False

        html = self.render_html(report, analysis)
        plain = (
            f"Facebook Monitor Report\nDate: {report.get('date')}\n"
            f"Total posts: {report.get('total_posts', 0)}\n\n"
            f"Summary:\n{analysis.get('summary', '')}\n"
        )

        plain_part = MIMEText(plain, "plain", "utf-8")
        html_part = MIMEText(html, "html", "utf-8")

        attachment_paths: list[Path] = []
        if csv_path and csv_path.exists():
            attachment_paths.append(csv_path)
        for path in extra_attachments or []:
            if path.exists():
                attachment_paths.append(path)

        # RFC 2046: attachments must not be siblings inside multipart/alternative (breaks Gmail and
        # other clients — HTML attachments appear as raw source in the body). Use mixed + nested alternative.
        if attachment_paths:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to_addr
            if self._settings.report_email_cc:
                msg["Cc"] = self._settings.report_email_cc
            alt = MIMEMultipart("alternative")
            alt.attach(plain_part)
            alt.attach(html_part)
            msg.attach(alt)
            for apath in attachment_paths:
                with apath.open("rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", "attachment", filename=apath.name)
                msg.attach(part)
        else:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to_addr
            if self._settings.report_email_cc:
                msg["Cc"] = self._settings.report_email_cc
            msg.attach(plain_part)
            msg.attach(html_part)

        recipients = [to_addr]
        if self._settings.report_email_cc:
            recipients.extend([x.strip() for x in self._settings.report_email_cc.split(",") if x.strip()])

        try:
            with smtplib.SMTP(self._settings.smtp_server, self._settings.smtp_port, timeout=60) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, recipients, msg.as_string())
            return True
        except Exception:
            logger.exception("Failed to send report email")
            return False
