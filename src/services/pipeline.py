from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.db_models import Analysis, ExtractedEmail, ExtractedPhone, Post
from src.db.session import _repo_base_dir, get_session
from src.services.contact_extract import (
    extract_emails,
    extract_phones,
    normalize_email_key,
    normalize_phone_key,
)
from src.services.browser_search import (
    BrowserAutomationError,
    ManualLoginRequiredError,
    browser_publication_cutoff_date,
    build_in_group_phrases_for_settings,
    parse_seed_group_urls,
    post_publication_matches_settings_filter,
    primary_browser_search_phrase,
    run_browser_group_search,
)
from src.services.browser_search_html_report import write_browser_search_html_report
from src.services.claude_analyzer import ClaudeAnalyzer
from src.services.daily_report_rows_html import write_daily_report_rows_html
from src.services.email_reporter import EmailReporter
from src.services.facebook_client import USER_FEED_GROUP_ID, FacebookClient
if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


def _permalink_from_post_dict(p: dict[str, Any]) -> str | None:
    u = p.get("permalink_url")
    if u:
        s = str(u).strip()
        if s:
            return s
    raw = p.get("raw_json")
    if isinstance(raw, dict):
        for key in ("permalink_url", "post_url"):
            v = raw.get(key)
            if v:
                s = str(v).strip()
                if s:
                    return s
        nested = raw.get("payload")
        if isinstance(nested, dict):
            ex = nested.get("extracted")
            if isinstance(ex, dict):
                v = ex.get("post_url")
                if v:
                    s = str(v).strip()
                    if s:
                        return s
    return None


def sync_post_contacts(session: Session, post_id: str, message: str | None) -> None:
    """Replace extracted phones/emails for a post from the current message text."""
    session.execute(delete(ExtractedPhone).where(ExtractedPhone.post_id == post_id))
    session.execute(delete(ExtractedEmail).where(ExtractedEmail.post_id == post_id))
    for phone_raw in extract_phones(message):
        nk = normalize_phone_key(phone_raw)
        if not nk:
            continue
        session.add(
            ExtractedPhone(
                post_id=post_id,
                phone_raw=phone_raw[:128],
                phone_normalized=nk[:32],
            )
        )
    for email_raw in extract_emails(message):
        ek = normalize_email_key(email_raw)
        if not ek:
            continue
        session.add(
            ExtractedEmail(
                post_id=post_id,
                email_raw=email_raw[:255],
                email_normalized=ek[:255],
            )
        )


def _effective_browser_queries(
    settings: Settings, query: str | None, in_group_query: str | None
) -> tuple[str, str]:
    """Global discovery uses first comma token of ``BROWSER_SEARCH_QUERY``; in-group list is prefixed with it."""
    raw_sq = (query or settings.browser_search_query or "job").strip() or "job"
    search_q = primary_browser_search_phrase(raw_sq)
    phrases = build_in_group_phrases_for_settings(
        search_q,
        in_group_query=in_group_query,
        settings_in_group=settings.browser_in_group_search_query,
    )
    if len(phrases) == 1:
        in_g = phrases[0]
    else:
        in_g = (
            f"{len(phrases)} phases: " + " | ".join(phrases[:3]) + (" | …" if len(phrases) > 3 else "")
        )
    return search_q, in_g


def upsert_posts(session: Session, posts: list[dict[str, Any]], *, source: str = "graph") -> int:
    """Insert or update posts. Deduplicates by ``id`` (last row wins) so one batch cannot violate UNIQUE."""
    by_id: dict[str, dict[str, Any]] = {}
    for p in posts:
        pid = p.get("id")
        if not pid:
            continue
        by_id[str(pid)] = p
    count = 0
    for p in by_id.values():
        pid = p.get("id")
        if not pid:
            continue
        pid = str(pid)
        link = _permalink_from_post_dict(p)
        existing = session.get(Post, pid)
        if existing:
            existing.message = p.get("message") or existing.message
            existing.author_id = p.get("author_id") or existing.author_id
            existing.author_name = p.get("author_name") or existing.author_name
            existing.created_time = p.get("created_time") or existing.created_time
            existing.raw_json = p.get("raw_json") or existing.raw_json
            existing.source = source
            if link:
                existing.permalink_url = link
            sync_post_contacts(session, pid, existing.message)
        else:
            session.add(
                Post(
                    id=pid,
                    group_id=str(p.get("group_id") or ""),
                    message=p.get("message") or "",
                    author_id=str(p.get("author_id")) if p.get("author_id") else None,
                    author_name=p.get("author_name"),
                    created_time=p.get("created_time"),
                    permalink_url=link,
                    raw_json=p.get("raw_json"),
                    source=source,
                )
            )
            sync_post_contacts(session, pid, p.get("message") or "")
        count += 1
    return count


def run_sync(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.facebook_graph_ready():
        return {
            "ok": False,
            "error": "FACEBOOK_ACCESS_TOKEN not set (or set FACEBOOK_MOCK_FEED_JSON for offline dev)",
            "upserted": 0,
        }
    client = FacebookClient(settings)
    total = 0
    feed: list[dict[str, Any]] = []
    sync_mode = settings.facebook_sync_mode
    src = "mock_json" if (settings.facebook_mock_feed_json or "").strip() else "graph"

    with get_session() as session:
        if sync_mode == "me":
            info = client.fetch_me_feed_with_diagnostics(limit=75)
            posts = info["posts"]
            feed.append(
                {
                    "group_id": USER_FEED_GROUP_ID,
                    "http_status": info["http_status"],
                    "error": info.get("error"),
                    "items_returned": len(posts),
                    "raw_items_first_page": info.get("raw_items_first_page"),
                }
            )
            total += upsert_posts(session, posts, source=src)
            groups_count = 1
        else:
            groups = settings.group_id_list()
            if not groups:
                return {"ok": False, "error": "FACEBOOK_GROUP_IDS empty", "upserted": 0}
            for gid in groups:
                info = client.fetch_group_feed_with_diagnostics(gid, limit=75)
                posts = info["posts"]
                feed.append(
                    {
                        "group_id": gid,
                        "http_status": info["http_status"],
                        "error": info.get("error"),
                        "items_returned": len(posts),
                        "raw_items_first_page": info.get("raw_items_first_page"),
                    }
                )
                total += upsert_posts(session, posts, source=src)
            groups_count = len(groups)

    fetch_failed = any(
        int(f.get("http_status") or 0) != 200 or bool(f.get("error")) for f in feed
    )
    out: dict[str, Any] = {
        "ok": not fetch_failed,
        "upserted": total,
        "groups": groups_count,
        "feed": feed,
        "sync_mode": sync_mode,
    }
    if fetch_failed:
        parts = [
            f"{f['group_id']}: {f.get('error') or f.get('http_status')}"
            for f in feed
            if int(f.get("http_status") or 0) != 200 or f.get("error")
        ]
        out["error"] = "; ".join(parts)[:800]
    return out


def run_analyze_recent(settings: Settings | None = None, *, limit_posts: int = 30) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set", "analyzed": 0}
    analyzer = ClaudeAnalyzer(settings)
    analyzed = 0
    with get_session() as session:
        stmt = select(Post).order_by(Post.fetched_at.desc()).limit(limit_posts)
        posts = list(session.scalars(stmt))
        payload = [
            {
                "id": p.id,
                "group_id": p.group_id,
                "message": p.message,
                "author_name": p.author_name,
            }
            for p in posts
        ]
        if not payload:
            return {"ok": True, "analyzed": 0}
        batch = analyzer.analyze_posts(payload, settings.keyword_list())
        # attach one aggregate analysis row linked to first post for traceability
        if posts:
            session.add(
                Analysis(
                    post_id=posts[0].id,
                    model=settings.claude_model,
                    summary=batch.get("summary") or "",
                    trends_json={
                        "trends": batch.get("trends"),
                        "hot_topics": batch.get("hot_topics"),
                        "recommendations": batch.get("recommendations"),
                        "urgency_level": batch.get("urgency_level"),
                    },
                    raw_response=None,
                )
            )
            analyzed = 1
    return {"ok": True, "analyzed": analyzed}


def _combined_browser_seed_url_text(settings: Settings, seed_group_urls: str | None) -> str:
    parts: list[str] = []
    s = (settings.browser_seed_group_urls or "").strip()
    if s:
        parts.append(s)
    if seed_group_urls is not None:
        e = str(seed_group_urls).strip()
        if e:
            parts.append(e)
    return ",".join(parts)


def run_browser_search_sync(
    settings: Settings | None = None,
    *,
    query: str | None = None,
    in_group_query: str | None = None,
    in_group_queries: Sequence[str] | None = None,
    group_limit: int | None = None,
    post_limit_per_group: int | None = None,
    seed_group_urls: str | None = None,
    global_message_contains: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    cleaned_queries: list[str] | None = None
    if in_group_queries is not None:
        cleaned_queries = [str(p).strip() for p in in_group_queries if str(p).strip()]
        if not cleaned_queries:
            cleaned_queries = None
    if cleaned_queries is not None:
        sq = (query or settings.browser_search_query or "job").strip() or "job"
        ig = (
            cleaned_queries[0]
            if len(cleaned_queries) == 1
            else f"{len(cleaned_queries)} phases: " + " | ".join(cleaned_queries[:3])
            + (" | …" if len(cleaned_queries) > 3 else "")
        )
    else:
        sq, ig = _effective_browser_queries(settings, query, in_group_query)
    browse_result: dict[str, Any] | None = None

    def _with_html_report(out: dict[str, Any]) -> dict[str, Any]:
        report_dir = write_browser_search_html_report(browse_result=browse_result, sync_summary=out)
        if report_dir is not None:
            out["html_report_dir"] = str(report_dir)
        return out

    if not settings.enable_browser_search_sync:
        ig_list = (
            cleaned_queries
            if cleaned_queries is not None
            else build_in_group_phrases_for_settings(
                sq,
                in_group_query=in_group_query,
                settings_in_group=settings.browser_in_group_search_query,
            )
        )
        return _with_html_report(
            {
                "ok": False,
                "error": "browser search sync is disabled (set ENABLE_BROWSER_SEARCH_SYNC=true to enable)",
                "upserted": 0,
                "groups_scanned": 0,
                "groups_with_hits": 0,
                "found_posts": 0,
                "errors": [],
                "query": sq,
                "in_group_query": ig,
                "in_group_queries": ig_list,
                "global_message_contains": (global_message_contains or "").strip() or None,
                "artifacts_dir": None,
            }
        )
    try:
        seed_groups = parse_seed_group_urls(_combined_browser_seed_url_text(settings, seed_group_urls))
        browse_result = run_browser_group_search(
            settings,
            query=query,
            in_group_query=in_group_query,
            in_group_queries=cleaned_queries,
            group_limit=group_limit,
            post_limit_per_group=post_limit_per_group,
            seed_groups=seed_groups,
            global_message_contains=global_message_contains,
        )
    except ManualLoginRequiredError as exc:
        ig_list = (
            cleaned_queries
            if cleaned_queries is not None
            else build_in_group_phrases_for_settings(
                sq,
                in_group_query=in_group_query,
                settings_in_group=settings.browser_in_group_search_query,
            )
        )
        raw_sq = (query or settings.browser_search_query or "job").strip() or "job"
        err_body: dict[str, Any] = {
            "ok": False,
            "error": str(exc),
            "upserted": 0,
            "groups_scanned": 0,
            "groups_with_hits": 0,
            "found_posts": 0,
            "errors": [],
            "query": sq,
            "in_group_query": ig,
            "in_group_queries": ig_list,
            "global_message_contains": (global_message_contains or "").strip() or None,
            "artifacts_dir": None,
        }
        if raw_sq != sq:
            err_body["search_query_raw"] = raw_sq
        return _with_html_report(err_body)
    except BrowserAutomationError as exc:
        ig_list = (
            cleaned_queries
            if cleaned_queries is not None
            else build_in_group_phrases_for_settings(
                sq,
                in_group_query=in_group_query,
                settings_in_group=settings.browser_in_group_search_query,
            )
        )
        raw_sq = (query or settings.browser_search_query or "job").strip() or "job"
        err_body = {
            "ok": False,
            "error": str(exc),
            "upserted": 0,
            "groups_scanned": 0,
            "groups_with_hits": 0,
            "found_posts": 0,
            "errors": [],
            "query": sq,
            "in_group_query": ig,
            "in_group_queries": ig_list,
            "global_message_contains": (global_message_contains or "").strip() or None,
            "artifacts_dir": None,
        }
        if raw_sq != sq:
            err_body["search_query_raw"] = raw_sq
        return _with_html_report(err_body)

    result = browse_result
    assert result is not None
    upserted = 0
    groups_with_hits = 0
    with get_session() as session:
        for group in result.get("groups", []):
            posts = group.get("posts", [])
            if posts:
                groups_with_hits += 1
            upserted += upsert_posts(session, posts, source="playwright_browser")
            session.flush()
    ok_out: dict[str, Any] = {
        "ok": True,
        "query": result.get("query"),
        "in_group_query": result.get("in_group_query"),
        "groups_scanned": int(result.get("groups_scanned") or 0),
        "groups_with_hits": groups_with_hits,
        "upserted": upserted,
        "found_posts": int(result.get("found_posts") or 0),
        "errors": result.get("errors") or [],
        "artifacts_dir": result.get("artifacts_dir"),
    }
    if result.get("in_group_queries"):
        ok_out["in_group_queries"] = result["in_group_queries"]
    if result.get("global_message_contains"):
        ok_out["global_message_contains"] = result["global_message_contains"]
    if result.get("publication_year_filter") is not None:
        ok_out["publication_year_filter"] = result["publication_year_filter"]
    if result.get("publication_from_date"):
        ok_out["publication_from_date"] = result["publication_from_date"]
    return _with_html_report(ok_out)


def build_contact_export_rows(session: Session, post_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rows for phone/email CSVs paired with the main daily report (same ``run_stamp`` in filenames)."""
    if not post_ids:
        return [], []
    meta = {r.id: r for r in session.scalars(select(Post).where(Post.id.in_(post_ids)))}
    phone_rows: list[dict[str, Any]] = []
    for ep in session.scalars(select(ExtractedPhone).where(ExtractedPhone.post_id.in_(post_ids))):
        p = meta.get(ep.post_id)
        phone_rows.append(
            {
                "post_id": ep.post_id,
                "phone": ep.phone_raw,
                "phone_normalized": ep.phone_normalized,
                "post_url": (p.permalink_url or "") if p else "",
                "group_id": p.group_id if p else "",
                "author_name": (p.author_name or "") if p else "",
            }
        )
    email_rows: list[dict[str, Any]] = []
    for ee in session.scalars(select(ExtractedEmail).where(ExtractedEmail.post_id.in_(post_ids))):
        p = meta.get(ee.post_id)
        email_rows.append(
            {
                "post_id": ee.post_id,
                "email": ee.email_raw,
                "email_normalized": ee.email_normalized,
                "post_url": (p.permalink_url or "") if p else "",
                "group_id": p.group_id if p else "",
                "author_name": (p.author_name or "") if p else "",
            }
        )
    return phone_rows, email_rows


def _post_matches_publication_filter_for_report(p: Post, settings: Settings) -> bool:
    """Same rule as browser ingest for ``BROWSER_POST_PUBLICATION_*``."""
    nd = {"message": p.message or "", "created_time": p.created_time}
    return post_publication_matches_settings_filter(nd, settings)


def build_report_context(session: Session, settings: Settings) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    posts = list(session.scalars(select(Post).order_by(Post.fetched_at.desc()).limit(500)))
    year_f = settings.browser_post_publication_year
    cutoff = browser_publication_cutoff_date(settings)
    if year_f is not None:
        posts = [p for p in posts if _post_matches_publication_filter_for_report(p, settings)]
    today = datetime.now(timezone.utc).date().isoformat()
    post_ids = [p.id for p in posts]
    phones_by_post: dict[str, list[str]] = {}
    emails_by_post: dict[str, list[str]] = {}
    if post_ids:
        for ep in session.scalars(select(ExtractedPhone).where(ExtractedPhone.post_id.in_(post_ids))):
            phones_by_post.setdefault(ep.post_id, []).append(ep.phone_raw)
        for ee in session.scalars(select(ExtractedEmail).where(ExtractedEmail.post_id.in_(post_ids))):
            emails_by_post.setdefault(ee.post_id, []).append(ee.email_raw)
    rows: list[dict[str, Any]] = []
    for p in posts:
        rows.append(
            {
                "id": p.id,
                "group_id": p.group_id,
                "author_name": p.author_name or "",
                "created_time": p.created_time.isoformat() if p.created_time else "",
                "post_url": (p.permalink_url or "")[:2048],
                "phones": "; ".join(phones_by_post.get(p.id, [])),
                "emails": "; ".join(emails_by_post.get(p.id, [])),
                "message": (p.message or "")[:2000],
                "source": p.source,
            }
        )
    report: dict[str, Any] = {
        "date": today,
        "total_posts": len(posts),
        "groups": sorted({p.group_id for p in posts if p.group_id}),
    }
    if year_f is not None:
        report["publication_year_filter"] = year_f
    if cutoff is not None:
        report["publication_from_date"] = cutoff.isoformat()
    return report, rows


def _build_daily_report_artifacts(
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[Path], dict[str, Any]]:
    """Write daily CSVs and build ``report`` / ``analysis`` for email. Does not send."""
    reporter = EmailReporter(settings)
    with get_session() as session:
        report, rows = build_report_context(session, settings)
        analysis: dict[str, Any]
        if settings.anthropic_api_key:
            analyzer = ClaudeAnalyzer(settings)
            analysis = analyzer.analyze_posts(rows[:80], settings.keyword_list())
        else:
            analysis = {"summary": "AI analysis skipped (no ANTHROPIC_API_KEY).", "trends": [], "recommendations": []}
        phone_rows, email_rows = build_contact_export_rows(session, {str(r["id"]) for r in rows})

    reports_dir = Path(settings.reports_dir)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"report_{report['date']}_{run_stamp}"
    csv_path = reports_dir / f"{base_name}.csv"
    reporter.write_csv(rows, csv_path)

    extra_attachments: list[Path] = []
    phones_csv = reports_dir / f"{base_name}_phones.csv"
    emails_csv = reports_dir / f"{base_name}_emails.csv"
    if phone_rows:
        reporter.write_csv(phone_rows, phones_csv)
        extra_attachments.append(phones_csv)
    if email_rows:
        reporter.write_csv(email_rows, emails_csv)
        extra_attachments.append(emails_csv)

    daily_html_path = reports_dir / f"daily_posts_{run_stamp}.html"
    write_daily_report_rows_html(daily_html_path, report=report, rows=rows, run_stamp=run_stamp)
    extra_attachments.append(daily_html_path)

    out: dict[str, Any] = {
        "ok": True,
        "date": report["date"],
        "run_stamp": run_stamp,
        "csv": str(csv_path),
        "rows": len(rows),
        "phones_exported": len(phone_rows),
        "emails_exported": len(email_rows),
        "daily_posts_html": str(daily_html_path),
    }
    if report.get("publication_year_filter") is not None:
        out["publication_year_filter"] = report["publication_year_filter"]
    if report.get("publication_from_date"):
        out["publication_from_date"] = report["publication_from_date"]
    if phone_rows:
        out["phones_csv"] = str(phones_csv)
    if email_rows:
        out["emails_csv"] = str(emails_csv)
    return report, analysis, csv_path, extra_attachments, out


def run_daily_report(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    report, analysis, csv_path, extras, out = _build_daily_report_artifacts(settings)
    reporter = EmailReporter(settings)
    subject = f"Facebook Monitor daily report — {report['date']} ({out['run_stamp']})"
    sent = reporter.send_report_email(
        subject=subject,
        report=report,
        analysis=analysis,
        csv_path=csv_path,
        extra_attachments=extras or None,
    )
    out["email_sent"] = sent
    return out


def resolve_browser_search_html_report_dir(folder: str) -> Path:
    """Resolve ``report/search_<stamp>/`` under the repo from a folder name or UTC stamp."""
    raw = (folder or "").strip()
    if not raw:
        raise ValueError("folder is empty")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    repo = _repo_base_dir()
    if raw.startswith("search_"):
        return (repo / "report" / raw).resolve()
    return (repo / "report" / f"search_{raw}").resolve()


def send_browser_search_html_report_email(
    settings: Settings | None = None,
    *,
    search_folder: str | None = None,
    report_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Email ``index.html`` from a browser-search HTML folder (not the daily DB CSV report).

    ``search_folder`` may be ``search_20260426T113551Z`` or just ``20260426T113551Z``.
    ``report_dir`` overrides and may be absolute.
    """
    settings = settings or get_settings()
    if report_dir is not None:
        d = Path(report_dir).resolve()
    elif search_folder:
        d = resolve_browser_search_html_report_dir(search_folder)
    else:
        return {"ok": False, "error": "Provide search_folder or report_dir"}
    index = d / "index.html"
    if not index.is_file():
        return {"ok": False, "error": f"missing index.html under {d}"}

    reporter = EmailReporter(settings)
    today = datetime.now(timezone.utc).date().isoformat()
    report: dict[str, Any] = {"date": today, "total_posts": 0, "groups": []}
    analysis = {
        "summary": (
            f"This message attaches the Playwright browser search HTML export from folder “{d.name}”. "
            "Open the .html attachment in a browser. It is not the daily database report "
            "(that is produced by POST /admin/report and uses posts in SQLite/Postgres)."
        ),
        "trends": [],
        "recommendations": [],
    }
    tmp_attach = Path(tempfile.gettempdir()) / f"browser_search_{d.name}.html"
    try:
        shutil.copyfile(index, tmp_attach)
        subject = f"Facebook browser search — {d.name}"
        sent = reporter.send_report_email(
            subject=subject,
            report=report,
            analysis=analysis,
            csv_path=None,
            extra_attachments=[tmp_attach],
        )
    finally:
        tmp_attach.unlink(missing_ok=True)

    return {
        "ok": True,
        "email_sent": sent,
        "html_report_dir": str(d),
        "attachment": tmp_attach.name,
    }


def _browser_html_folder_stamp(folder: Path) -> str:
    """UTC token from ``report/search_<stamp>/`` (folder basename without ``search_`` prefix)."""
    name = folder.name
    if name.startswith("search_"):
        return name[len("search_") :]
    return name


def find_latest_browser_search_report_dir() -> Path:
    """Return ``report/search_<stamp>/`` with the newest UTC stamp in the folder name.

    Uses lexicographic order on ``search_YYYYMMDDTHHMMSSZ`` (same as time order). **Not** ``index.html``
    mtime — an older failed run can have a fresher mtime if the file was re-saved, which wrongly beat a
    newer successful report when picking ``report-browser-html-last``.
    """
    report = _repo_base_dir() / "report"
    if not report.is_dir():
        raise FileNotFoundError(f"no report directory: {report}")
    dirs = [p for p in report.glob("search_*") if p.is_dir() and (p / "index.html").is_file()]
    if not dirs:
        raise FileNotFoundError(f"no report/search_*/index.html under {report}")
    return max(dirs, key=lambda p: p.name).resolve()


def run_daily_report_with_latest_browser_html_email(settings: Settings | None = None) -> dict[str, Any]:
    """Build the daily CSV report and send **one** email with CSVs, CSV-aligned HTML, and Playwright HTML.

    Always attaches ``daily_posts_<run_stamp>.html`` (same rows as the main CSV) plus the latest
    ``report/search_*/index.html`` copy when available.

    JSON matches the daily ``POST /admin/report`` payload (``csv``, ``rows``, ``run_stamp``, …,
    ``daily_posts_html``, …) and adds ``html_report_dir``, ``browser_html_search_stamp``,
    ``browser_html_email_sent``, and ``browser_html_attachment`` (Playwright file name).

    ``run_stamp`` identifies **this** daily CSV build; ``browser_html_search_stamp`` identifies the
    **browser sync** report folder for the Playwright attachment (timestamps can differ slightly).

    If no ``report/search_*/index.html`` exists, falls back to :func:`run_daily_report` (daily email only)
    and sets browser fields to indicate skip/failure.
    """
    settings = settings or get_settings()
    try:
        d = find_latest_browser_search_report_dir()
    except FileNotFoundError as exc:
        out = run_daily_report(settings)
        out["html_report_dir"] = None
        out["browser_html_email_sent"] = False
        out["browser_html_ok"] = False
        out["browser_html_error"] = str(exc)
        return out

    report, analysis, csv_path, extras, out = _build_daily_report_artifacts(settings)
    if not out.get("ok"):
        return out

    reporter = EmailReporter(settings)
    index = d / "index.html"
    if not index.is_file():
        sent = reporter.send_report_email(
            subject=f"Facebook Monitor daily report — {report['date']} ({out['run_stamp']})",
            report=report,
            analysis=analysis,
            csv_path=csv_path,
            extra_attachments=extras or None,
        )
        out["email_sent"] = sent
        out["html_report_dir"] = str(d)
        out["browser_html_email_sent"] = False
        out["browser_html_ok"] = False
        out["browser_html_error"] = f"missing index.html under {d}"
        return out

    html_stamp = _browser_html_folder_stamp(d)
    daily_stamp = out["run_stamp"]
    tmp_attach = Path(tempfile.gettempdir()) / f"browser_search_{html_stamp}_daily_{daily_stamp}.html"
    attach_name = tmp_attach.name
    try:
        shutil.copyfile(index, tmp_attach)
        extras_all = list(extras) + [tmp_attach]
        subject = f"Facebook Monitor daily report + browser HTML — {report['date']} ({daily_stamp})"
        sent = reporter.send_report_email(
            subject=subject,
            report=report,
            analysis=analysis,
            csv_path=csv_path,
            extra_attachments=extras_all,
        )
    finally:
        tmp_attach.unlink(missing_ok=True)

    out["email_sent"] = sent
    out["html_report_dir"] = str(d)
    out["browser_html_search_stamp"] = html_stamp
    out["browser_html_email_sent"] = sent
    out["browser_html_ok"] = True
    out["browser_html_attachment"] = attach_name
    return out


def register_pipeline_jobs(app: "Flask") -> None:
    """Placeholder for future job registration hooks."""
    _ = app
