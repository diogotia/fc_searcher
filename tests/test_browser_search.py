from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.config import Settings
from src.services.browser_search import (
    BrowserAutomationError,
    BrowserFoundPost,
    DiscoveredGroup,
    build_body_keyword_needles,
    build_in_group_phrases_for_settings,
    infer_publication_date_from_browser_post,
    infer_publication_year_from_browser_post,
    match_in_post_keyword_canonical,
    normalize_for_in_post_match,
    parse_in_post_keywords,
    post_matches_body_keyword_union,
    post_matches_global_message_filter,
    post_publication_matches_settings_filter,
    post_publication_year_matches_filter,
    _parse_playwright_cli_run_code_json_payload,
    build_group_search_url,
    _build_group_search_extract_run_code,
    _build_group_search_scroll_extract_run_code,
    build_post_id,
    derive_group_key,
    extract_group_id,
    extract_group_job_posts,
    extract_post_external_id,
    merge_discovered_group_lists,
    normalize_browser_post,
    parse_seed_group_urls,
)


def test_extract_group_id_from_url():
    assert extract_group_id("https://www.facebook.com/groups/123456789/?ref=share") == "123456789"
    assert extract_group_id("https://www.facebook.com/groups/934750153812574") == "934750153812574"
    assert extract_group_id("https://www.facebook.com/groups/934750153812574/") == "934750153812574"


def test_extract_post_external_id_from_permalink_patterns():
    assert extract_post_external_id("https://www.facebook.com/groups/42/posts/99/") == "99"
    assert extract_post_external_id("https://www.facebook.com/permalink.php?story_fbid=555&id=42") == "555"


def test_build_post_id_uses_hash_fallback():
    found = BrowserFoundPost(
        external_id=None,
        group_id="42",
        group_name="Jobs",
        group_url="https://www.facebook.com/groups/42",
        post_url="https://www.facebook.com/groups/42/posts/abc",
        message="Job text",
        author_name="Author",
        created_time=None,
        raw_payload={},
    )
    pid = build_post_id(found)
    assert pid.startswith("pw_")
    assert len(pid) <= 64


def test_normalize_browser_post_keeps_report_search_fields():
    found = BrowserFoundPost(
        external_id="post-1",
        group_id=derive_group_key("https://www.facebook.com/groups/example"),
        group_name="Example Jobs",
        group_url="https://www.facebook.com/groups/example",
        post_url="https://www.facebook.com/groups/example/posts/post-1",
        message="Remote job in Berlin",
        author_name="Jane",
        created_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        raw_payload={"foo": "bar"},
    )
    post = normalize_browser_post(found, query="job")
    assert post["id"] == "post-1"
    assert post["author_name"] == "Jane"
    assert post["message"] == "Remote job in Berlin"
    assert post["raw_json"]["source_type"] == "playwright_browser"
    assert post["raw_json"]["query"] == "job"


def test_build_group_search_url_encodes_keyword():
    assert build_group_search_url("https://www.facebook.com/groups/example", "job berlin").endswith("/search/?q=job%20berlin")


def test_build_group_search_url_encodes_cyrillic_in_group():
    url = build_group_search_url("https://www.facebook.com/groups/934750153812574", "ищу работу")
    assert "934750153812574/search/?q=" in url
    assert "%D0%B8%D1%89%D1%83" in url


def test_build_in_group_phrases_comma_list_prefixes_search_query():
    phrases = build_in_group_phrases_for_settings(
        "ищу работу",
        in_group_query=None,
        settings_in_group="малярные работы, монтаж гипсокартона ,электромонтажные",
    )
    assert phrases == [
        "ищу работу малярные работы",
        "ищу работу монтаж гипсокартона",
        "ищу работу электромонтажные",
    ]


def test_build_in_group_phrases_single_token_prefixes_when_different():
    phrases = build_in_group_phrases_for_settings(
        "job",
        in_group_query="Berlin",
        settings_in_group="",
    )
    assert phrases == ["job Berlin"]


def test_build_in_group_phrases_single_token_same_as_search_collapses():
    phrases = build_in_group_phrases_for_settings(
        "job",
        in_group_query="job",
        settings_in_group="",
    )
    assert phrases == ["job"]


def test_build_in_group_phrases_empty_settings_uses_search_only():
    assert build_in_group_phrases_for_settings("x", in_group_query=None, settings_in_group="") == ["x"]


def test_parse_seed_group_urls_accepts_url_and_numeric():
    raw = "https://www.facebook.com/groups/934750153812574/, 934750153812574"
    groups = parse_seed_group_urls(raw)
    assert len(groups) == 1
    assert groups[0].group_url == "https://www.facebook.com/groups/934750153812574"
    assert groups[0].group_name == "Group 934750153812574"


def test_parse_playwright_cli_raises_on_error_section():
    out = "### Error\nError: page.evaluate: boom\n### Ran"
    try:
        _parse_playwright_cli_run_code_json_payload(out)
    except BrowserAutomationError as exc:
        assert "page.evaluate" in str(exc)
    else:
        raise AssertionError("expected BrowserAutomationError")


def test_parse_playwright_cli_json_codex_markdown_result():
    out = (
        '### Result\n'
        '"{\\"logged_in\\":false}"\n'
        "### Ran Playwright code\n"
        "```js\nawait 1;\n```"
    )
    assert _parse_playwright_cli_run_code_json_payload(out) == {"logged_in": False}


def test_parse_playwright_cli_json_bare_line():
    assert _parse_playwright_cli_run_code_json_payload('  {"ok": true}\n') == {"ok": True}


def test_facebook_web_credentials_configured():
    assert Settings(facebook_web_login="a@b.co", facebook_web_password="x").facebook_web_credentials_configured()
    assert not Settings(facebook_web_login="a@b.co", facebook_web_password=None).facebook_web_credentials_configured()
    assert not Settings(facebook_web_login=None, facebook_web_password="x").facebook_web_credentials_configured()


def test_infer_publication_year_russian_and_filter():
    nd = {"message": "16 октябрь 2023 г.\nищу работу", "created_time": None}
    assert infer_publication_year_from_browser_post(nd) == 2023
    assert post_publication_year_matches_filter(nd, 2026) is False
    assert post_publication_year_matches_filter(nd, 2023) is True
    assert post_publication_year_matches_filter(nd, None) is True
    nd_unknown = {"message": "no date here", "created_time": None}
    assert infer_publication_year_from_browser_post(nd_unknown) is None
    assert post_publication_year_matches_filter(nd_unknown, 2026) is False
    assert post_publication_year_matches_filter(nd_unknown, 2026, keep_unknown_year=True) is True
    nd_fb_header = {
        "message": "Сергей 13 январь · Ищу работу сварщиком",
        "created_time": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    assert infer_publication_year_from_browser_post(nd_fb_header) == 2024
    nd_year_only_in_body = {
        "message": "Иванов 13 январь · вакансия 2024 г. срочно",
        "created_time": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }
    assert infer_publication_year_from_browser_post(nd_year_only_in_body) == 2024
    nd_header_ru = {"message": "Абдурахман 24 февраль 2024 г. · Я МАСТЕР ПО ПЛИТКЕ", "created_time": None}
    assert infer_publication_year_from_browser_post(nd_header_ru) == 2024
    nd_header_vs_ct = {
        "message": "Басовский 3 сентябрь 2025 г. · ищу работу в строительстве",
        "created_time": datetime(2026, 4, 27, tzinfo=timezone.utc),
    }
    assert infer_publication_year_from_browser_post(nd_header_vs_ct) == 2025


def test_infer_publication_date_russian_header():
    nd = {"message": "15 апрель 2026 г.\nищу работу", "created_time": None}
    assert infer_publication_date_from_browser_post(nd) == date(2026, 4, 15)
    nd_iso = {"message": "2026-04-28 · body", "created_time": None}
    assert infer_publication_date_from_browser_post(nd_iso) == date(2026, 4, 28)


def test_infer_publication_date_russian_relative_and_dm_no_year():
    ref = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    nd_days = {"message": "Daniil Poldd 3 дн. · Ищу работу Штутгарт", "created_time": ref}
    assert infer_publication_date_from_browser_post(nd_days) == date(2026, 4, 26)
    nd_hours = {"message": "David Chira 21 ч. · Ищу людей для работы", "created_time": ref}
    assert infer_publication_date_from_browser_post(nd_hours) == date(2026, 4, 28)
    nd_dm_clock = {"message": "Ковальов Влад 13 апрель в 15:52 · ищу работу", "created_time": ref}
    assert infer_publication_date_from_browser_post(nd_dm_clock) == date(2026, 4, 13)
    nd_march = {"message": "Вера Чивилева 13 март · ВАКАНСИЯ В БЕРЛИНЕ", "created_time": ref}
    assert infer_publication_date_from_browser_post(nd_march) == date(2026, 3, 13)


def test_post_publication_cutoff_respects_russian_relative_and_facebook_dm():
    ref = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    s = Settings(
        browser_post_publication_year=2026,
        browser_post_publication_month=4,
        browser_post_publication_day=27,
        browser_post_publication_keep_unknown_year=False,
    )
    nd_old_rel = {"message": "Someone 3 дн. · текст", "created_time": ref}
    assert post_publication_matches_settings_filter(nd_old_rel, s) is False
    nd_recent_rel = {"message": "Someone 21 ч. · текст", "created_time": ref}
    assert post_publication_matches_settings_filter(nd_recent_rel, s) is True
    nd_apr13 = {"message": "X 13 апрель в 15:52 · текст", "created_time": ref}
    assert post_publication_matches_settings_filter(nd_apr13, s) is False
    nd_apr28 = {"message": "Y 28 апрель в 09:00 · текст", "created_time": ref}
    assert post_publication_matches_settings_filter(nd_apr28, s) is True


def test_post_publication_matches_settings_filter_from_date():
    s = Settings(
        browser_post_publication_year=2026,
        browser_post_publication_month=4,
        browser_post_publication_day=27,
        browser_post_publication_keep_unknown_year=False,
    )
    before = {"message": "20 апрель 2026 г.\nтекст", "created_time": None}
    on_day = {"message": "27 апрель 2026 г.\nтекст", "created_time": None}
    after = {"message": "28 апрель 2026 г.\nтекст", "created_time": None}
    assert post_publication_matches_settings_filter(before, s) is False
    assert post_publication_matches_settings_filter(on_day, s) is True
    assert post_publication_matches_settings_filter(after, s) is True

    ct_only = {
        "message": "",
        "created_time": datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
    }
    assert post_publication_matches_settings_filter(ct_only, s) is True

    s_year_only = Settings(browser_post_publication_year=2026, browser_post_publication_keep_unknown_year=False)
    assert post_publication_matches_settings_filter(before, s_year_only) is True


def test_post_matches_global_message_filter():
    assert post_matches_global_message_filter("Ищу работу в Берлине", "ищу работу") is True
    assert post_matches_global_message_filter("No match here", "ищу работу") is False
    assert post_matches_global_message_filter("x", None) is True
    assert post_matches_global_message_filter("x", "") is True


def test_build_body_keyword_needles_dedupes_and_orders_phrases_then_discovery():
    needles = build_body_keyword_needles(
        "ищу работу в Германии",
        ["ищу работу Бетонщик", "ищу работу Бетонщик", "ищу работу Арматурщик"],
    )
    assert needles == [
        "ищу работу Бетонщик",
        "ищу работу Арматурщик",
        "ищу работу в Германии",
    ]


def test_post_matches_body_keyword_union():
    needles = ["ищу работу Бетонщик", "ищу работу в Германии"]
    assert post_matches_body_keyword_union("Вакансия ищу работу Бетонщик в Munich", needles) is True
    assert post_matches_body_keyword_union("ищу работу в Германии только", needles) is True
    assert post_matches_body_keyword_union("Другое объявление", needles) is False
    assert post_matches_body_keyword_union("x", []) is True


def test_parse_in_post_keywords_splits_csv_and_newlines():
    raw = "Каменщик, Бетонщик ,\n  Монтажник металлоконструкций\nКровельщик,"
    assert parse_in_post_keywords(raw) == [
        "Каменщик",
        "Бетонщик",
        "Монтажник металлоконструкций",
        "Кровельщик",
    ]
    assert parse_in_post_keywords(None) == []
    assert parse_in_post_keywords("") == []
    assert parse_in_post_keywords("   ") == []


def test_normalize_for_in_post_match_unicode_and_case():
    assert normalize_for_in_post_match("  КАМЕНЩИК  ") == "каменщик"
    hay = normalize_for_in_post_match("ищу КАМЕНЩИКА в Кёльне")
    assert normalize_for_in_post_match("Каменщик") in hay


def test_match_in_post_keyword_canonical_casefold_and_synonyms():
    needles = ["Каменщик", "Гипсокартонщик", "штукатурка", "Гипсакартон"]
    canon, variant = match_in_post_keyword_canonical("Вакансия КАМЕНЩИК срочно", needles)
    assert canon == "Каменщик"
    assert variant == "Каменщик"

    canon2, var2 = match_in_post_keyword_canonical("нужен гипсокартон на объект", needles)
    assert canon2 == "Гипсокартонщик"
    assert var2 == "гипсокартон"

    canon3, var3 = match_in_post_keyword_canonical("отделка штукатуром", needles)
    assert canon3 == "штукатурка"
    assert var3 == "штукатур"

    canon4, var4 = match_in_post_keyword_canonical("монтаж гипсокартон потолок", needles)
    assert canon4 == "Гипсокартонщик"
    assert var4 == "гипсокартон"

    canon5, var5 = match_in_post_keyword_canonical("объявление Гипсакартон стены", needles)
    assert canon5 == "Гипсакартон"
    assert var5 == "Гипсакартон"

    assert match_in_post_keyword_canonical("совсем другой текст", needles) == (None, None)


def test_merge_discovered_group_lists_dedupes_and_prioritizes():
    a = DiscoveredGroup(group_name="A", group_url="https://www.facebook.com/groups/1", group_id="1")
    b = DiscoveredGroup(group_name="B", group_url="https://www.facebook.com/groups/2", group_id="2")
    c = DiscoveredGroup(group_name="C", group_url="https://www.facebook.com/groups/1", group_id="1")
    merged = merge_discovered_group_lists([a], [b, c], discovery_limit=10)
    assert len(merged) == 2
    assert merged[0].group_id == "1"
    assert merged[1].group_id == "2"


def test_merge_discovered_group_lists_keeps_all_seeds_caps_discovery_only():
    """Seeds are never dropped when discovery_limit is small; limit applies only to /search/groups picks."""
    seeds = [
        DiscoveredGroup(group_name="S1", group_url="https://www.facebook.com/groups/101", group_id="101"),
        DiscoveredGroup(group_name="S2", group_url="https://www.facebook.com/groups/102", group_id="102"),
        DiscoveredGroup(group_name="S3", group_url="https://www.facebook.com/groups/103", group_id="103"),
    ]
    discovered = [
        DiscoveredGroup(group_name="D1", group_url="https://www.facebook.com/groups/201", group_id="201"),
        DiscoveredGroup(group_name="D2", group_url="https://www.facebook.com/groups/202", group_id="202"),
        DiscoveredGroup(group_name="D3", group_url="https://www.facebook.com/groups/203", group_id="203"),
    ]
    merged = merge_discovered_group_lists(seeds, discovered, discovery_limit=2)
    assert [g.group_id for g in merged] == ["101", "102", "103", "201", "202"]


class _FakeExtractRunner:
    """Minimal PlaywrightCliRunner stand-in for extract_group_job_posts."""

    def __init__(self, extract_stdout_json: str | list[str]) -> None:
        self._queue: list[str] = (
            [extract_stdout_json] if isinstance(extract_stdout_json, str) else list(extract_stdout_json)
        )
        self.snapshot_calls = 0

    def open(self, url: str) -> None:
        return None

    def snapshot(self, label: str) -> Path:
        self.snapshot_calls += 1
        return Path("/tmp/fc-searcher-test-snapshot.txt")

    def run_code(self, code: str) -> str:
        if not self._queue:
            return "{}"
        return self._queue.pop(0)


def test_build_group_search_extract_run_code_substitutes_scroll_params():
    code = _build_group_search_extract_run_code(scroll_rounds=4, scroll_pause_ms=900)
    assert "__SCROLL_ROUNDS__" not in code
    assert "__SCROLL_PAUSE_MS__" not in code
    assert "for (let _fcI = 0; _fcI < 4; _fcI += 1)" in code
    assert "await _fcSleep(900);" in code


def test_build_group_search_scroll_extract_run_code_substitutes_scroll_params():
    code = _build_group_search_scroll_extract_run_code(scroll_rounds=4, scroll_pause_ms=900)
    assert "__SCROLL_ROUNDS__" not in code
    assert "__SCROLL_PAUSE_MS__" not in code
    assert "for (let _fcI = 0; _fcI < 4; _fcI += 1)" in code


def test_extract_group_job_posts_empty_search_payload_returns_no_posts():
    import json

    group = DiscoveredGroup(
        group_name="Test Group",
        group_url="https://www.facebook.com/groups/12345",
        group_id="12345",
    )
    probe = {"inaccessible": False, "empty_search": True}
    runner = _FakeExtractRunner(json.dumps(probe))
    posts = extract_group_job_posts(group, "keyword", 10, runner)
    assert posts == []
    assert runner.snapshot_calls == 0


def test_extract_group_job_posts_with_post_rows():
    import json

    group = DiscoveredGroup(
        group_name="Jobs",
        group_url="https://www.facebook.com/groups/99",
        group_id="99",
    )
    probe = {"inaccessible": False, "empty_search": False}
    extract_payload = {
        "inaccessible": False,
        "empty_search": False,
        "posts": [
            {
                "post_url": "https://www.facebook.com/groups/99/posts/111/",
                "message": "Hello job",
                "author_name": "A",
                "created_time": "2026-01-15T12:00:00.000Z",
            }
        ],
    }
    runner = _FakeExtractRunner([json.dumps(probe), json.dumps(extract_payload)])
    posts = extract_group_job_posts(group, "keyword", 10, runner)
    assert len(posts) == 1
    assert posts[0].post_url.endswith("/posts/111/")
    assert posts[0].message == "Hello job"
    assert runner.snapshot_calls == 1


def test_extract_group_job_posts_inaccessible_raises():
    import json

    group = DiscoveredGroup(
        group_name="X",
        group_url="https://www.facebook.com/groups/1",
        group_id="1",
    )
    runner = _FakeExtractRunner(json.dumps({"inaccessible": True, "empty_search": False}))
    with pytest.raises(BrowserAutomationError):
        extract_group_job_posts(group, "k", 5, runner)
    assert runner.snapshot_calls == 0
