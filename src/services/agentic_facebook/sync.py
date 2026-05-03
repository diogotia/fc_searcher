"""Runtime entry point for the opt-in agentic Facebook flow."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.config import Settings, get_settings
from src.db.session import get_session
from src.services.agentic_facebook.report import write_agentic_facebook_html_report
from src.services.browser_search import (
    BrowserAutomationError,
    ManualLoginRequiredError,
    build_in_group_phrases_for_settings,
    parse_seed_group_urls,
    primary_browser_search_phrase,
    run_browser_group_search,
)
from src.services.pipeline import upsert_posts


def _split_csv_text(*values: str | None) -> str:
    parts: list[str] = []
    for value in values:
        raw = (value or "").strip()
        if raw:
            parts.append(raw)
    return ",".join(parts)


def _clean_in_group_queries(raw: Sequence[str] | None) -> list[str] | None:
    if raw is None:
        return None
    cleaned = [str(item).strip() for item in raw if str(item).strip()]
    return cleaned or None


def _agentic_query_summary(
    settings: Settings,
    *,
    query: str | None,
    in_group_query: str | None,
    in_group_queries: list[str] | None,
    in_group_exact_keywords: bool = False,
) -> tuple[str, str, list[str]]:
    discovery_query = primary_browser_search_phrase((query or settings.browser_search_query or "job").strip())
    phrases = in_group_queries or build_in_group_phrases_for_settings(
        discovery_query,
        in_group_query=in_group_query,
        settings_in_group=settings.browser_in_group_search_query,
        exact_keywords=in_group_exact_keywords,
    )
    in_group_summary = (
        phrases[0]
        if len(phrases) == 1
        else f"{len(phrases)} phases: " + " | ".join(phrases[:3]) + (" | ..." if len(phrases) > 3 else "")
    )
    return discovery_query, in_group_summary, phrases


def _with_agentic_report(
    *,
    browse_result: dict[str, Any] | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    report_dir = write_agentic_facebook_html_report(browse_result=browse_result, sync_summary=summary)
    if report_dir is not None:
        summary["html_report_dir"] = str(report_dir)
    return summary


def run_agentic_facebook_sync(
    settings: Settings | None = None,
    *,
    query: str | None = None,
    in_group_query: str | None = None,
    in_group_queries: Sequence[str] | None = None,
    group_limit: int | None = None,
    post_limit_per_group: int | None = None,
    seed_group_urls: str | None = None,
    global_message_contains: str | None = None,
    in_group_exact_keywords: bool = False,
    facebook_ui_year_filter: bool = False,
    expand_see_more_before_extract: bool = False,
    body_keyword_union: bool = False,
) -> dict[str, Any]:
    """Run the isolated agentic Facebook flow and upsert posts with a distinct source."""
    settings = settings or get_settings()
    cleaned_queries = _clean_in_group_queries(in_group_queries)
    discovery_query, in_group_summary, phrases = _agentic_query_summary(
        settings,
        query=query,
        in_group_query=in_group_query,
        in_group_queries=cleaned_queries,
        in_group_exact_keywords=in_group_exact_keywords,
    )
    gmc = (global_message_contains or "").strip() or None

    if not settings.enable_agentic_facebook_sync:
        return _with_agentic_report(
            browse_result=None,
            summary={
                "ok": False,
                "flow": "agentic_facebook",
                "error": "agentic Facebook sync is disabled (set ENABLE_AGENTIC_FACEBOOK_SYNC=true to enable)",
                "upserted": 0,
                "groups_scanned": 0,
                "groups_with_hits": 0,
                "found_posts": 0,
                "errors": [],
                "query": discovery_query,
                "in_group_query": in_group_summary,
                "in_group_queries": phrases,
                "global_message_contains": gmc,
                "artifacts_dir": None,
            },
        )

    browse_result: dict[str, Any] | None = None
    try:
        seeds = parse_seed_group_urls(_split_csv_text(settings.browser_seed_group_urls, seed_group_urls))
        browse_result = run_browser_group_search(
            settings,
            query=query,
            in_group_query=in_group_query,
            in_group_queries=cleaned_queries,
            group_limit=group_limit,
            post_limit_per_group=post_limit_per_group,
            seed_groups=seeds,
            global_message_contains=gmc,
            output_base_dir=Path(settings.agentic_facebook_output_dir),
            in_group_exact_keywords=in_group_exact_keywords,
            facebook_ui_year_filter=facebook_ui_year_filter,
            expand_see_more_before_extract=expand_see_more_before_extract,
            body_keyword_union=body_keyword_union,
        )
    except (ManualLoginRequiredError, BrowserAutomationError) as exc:
        return _with_agentic_report(
            browse_result=browse_result,
            summary={
                "ok": False,
                "flow": "agentic_facebook",
                "error": str(exc),
                "upserted": 0,
                "groups_scanned": 0,
                "groups_with_hits": 0,
                "found_posts": 0,
                "errors": [],
                "query": discovery_query,
                "in_group_query": in_group_summary,
                "in_group_queries": phrases,
                "global_message_contains": gmc,
                "artifacts_dir": None,
            },
        )

    result = browse_result
    groups_with_hits = 0
    upserted = 0
    with get_session() as session:
        for group in result.get("groups", []):
            posts = group.get("posts") or []
            if posts:
                groups_with_hits += 1
            upserted += upsert_posts(session, posts, source=settings.agentic_facebook_source)
            session.flush()

    out: dict[str, Any] = {
        "ok": True,
        "flow": "agentic_facebook",
        "query": result.get("query"),
        "in_group_query": result.get("in_group_query"),
        "groups_scanned": int(result.get("groups_scanned") or 0),
        "groups_with_hits": groups_with_hits,
        "upserted": upserted,
        "found_posts": int(result.get("found_posts") or 0),
        "errors": result.get("errors") or [],
        "artifacts_dir": result.get("artifacts_dir"),
        "source": settings.agentic_facebook_source,
    }
    if result.get("in_group_queries"):
        out["in_group_queries"] = result["in_group_queries"]
    if result.get("global_message_contains"):
        out["global_message_contains"] = result["global_message_contains"]
    if result.get("publication_year_filter") is not None:
        out["publication_year_filter"] = result["publication_year_filter"]
    if result.get("publication_from_date"):
        out["publication_from_date"] = result["publication_from_date"]
    if result.get("search_query_raw"):
        out["search_query_raw"] = result["search_query_raw"]
    if result.get("in_group_exact_keywords"):
        out["in_group_exact_keywords"] = True
    if result.get("facebook_ui_year_filter"):
        out["facebook_ui_year_filter"] = True
    if result.get("facebook_ui_filter_year") is not None:
        out["facebook_ui_filter_year"] = result.get("facebook_ui_filter_year")
    if result.get("expand_see_more"):
        out["expand_see_more"] = True
    if result.get("body_keyword_union"):
        out["body_keyword_union"] = True
    if result.get("body_keyword_needles_count") is not None:
        out["body_keyword_needles_count"] = result["body_keyword_needles_count"]
    return _with_agentic_report(browse_result=result, summary=out)
