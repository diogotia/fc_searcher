from __future__ import annotations

from src.logging_config import get_logger
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config import Settings, get_settings, reload_settings_if_dotenv_mounted
from src.services.pipeline import run_daily_report, run_sync

if TYPE_CHECKING:
    from flask import Flask

logger = get_logger(__name__)


def _cron_trigger(expr: str, tz_name: str) -> CronTrigger:
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %s, falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    return CronTrigger.from_crontab(expr, timezone=tz)


def start_scheduler(app: "Flask") -> BackgroundScheduler | None:
    settings: Settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("APScheduler disabled (ENABLE_SCHEDULER=false)")
        return None

    def sync_job() -> None:
        with app.app_context():
            try:
                reload_settings_if_dotenv_mounted()
                result = run_sync(get_settings())
                if not result.get("ok"):
                    logger.warning("Scheduled sync finished with Graph errors: %s", result.get("error"))
            except Exception:
                logger.exception("Scheduled sync failed")

    def report_job() -> None:
        with app.app_context():
            try:
                reload_settings_if_dotenv_mounted()
                settings = get_settings()
                result = run_daily_report(settings)
                smtp_ready = bool(settings.smtp_user and settings.smtp_password and settings.report_email)
                logger.info(
                    "Scheduled daily report job finished: email_sent=%s smtp_configured=%s "
                    "date=%s rows=%s phones_exported=%s emails_exported=%s csv=%s",
                    result.get("email_sent"),
                    smtp_ready,
                    result.get("date"),
                    result.get("rows"),
                    result.get("phones_exported"),
                    result.get("emails_exported"),
                    result.get("csv"),
                )
                if result.get("phones_csv"):
                    logger.info("Scheduled daily report phones_csv=%s", result.get("phones_csv"))
                if result.get("emails_csv"):
                    logger.info("Scheduled daily report emails_csv=%s", result.get("emails_csv"))
                if not result.get("email_sent") and smtp_ready:
                    logger.warning(
                        "Scheduled daily report: SMTP configured but email_sent=false (check logs above)."
                    )
                if not smtp_ready:
                    logger.info(
                        "Scheduled daily report: email not sent (set SMTP_USER, SMTP_PASSWORD, REPORT_EMAIL)."
                    )
            except Exception:
                logger.exception("Scheduled report failed")

    sched = BackgroundScheduler()
    sched.add_job(sync_job, _cron_trigger(settings.sync_cron, settings.timezone), id="graph_sync", replace_existing=True)
    sched.add_job(
        report_job,
        _cron_trigger(settings.report_cron, settings.timezone),
        id="daily_report",
        replace_existing=True,
    )
    sched.start()
    logger.info("APScheduler started (sync=%s report=%s tz=%s)", settings.sync_cron, settings.report_cron, settings.timezone)
    return sched
