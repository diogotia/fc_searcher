from __future__ import annotations

from pathlib import Path

from src.config import get_settings
from src.db.session import init_db, init_engine
from src.services import pipeline as pl


def _stub_fc_repo_root(path: Path) -> None:
    """So ``FC_SEARCHER_REPO_ROOT=path`` passes ``src/db/session._is_fc_searcher_repo_root`` in tests."""
    (path / "src").mkdir(parents=True, exist_ok=True)
    (path / "src" / "config.py").write_text("# test stub\n", encoding="utf-8")


def _reset_db(monkeypatch, tmp_path, name: str) -> None:
    db_path = tmp_path / name
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")
    get_settings.cache_clear()
    settings = get_settings()
    init_engine(settings.database_url)
    init_db()


def test_run_daily_report_csv_paths_include_run_stamp(monkeypatch, tmp_path):
    rep_dir = tmp_path / "reports"
    rep_dir.mkdir()
    monkeypatch.setenv("REPORTS_DIR", str(rep_dir))
    _reset_db(monkeypatch, tmp_path, "dailyrep.db")

    def fake_send(self, *, subject, report, analysis, csv_path=None, extra_attachments=None):
        return False

    monkeypatch.setattr(pl.EmailReporter, "send_report_email", fake_send)
    settings = get_settings()
    out = pl.run_daily_report(settings)
    assert out["ok"] is True
    stamp = out.get("run_stamp")
    assert stamp and len(stamp) >= 15
    csv_p = Path(out["csv"])
    assert csv_p.name == f"report_{out['date']}_{stamp}.csv"
    assert csv_p.is_file()
    daily_html = Path(out["daily_posts_html"])
    assert daily_html.is_file()
    assert daily_html.name == f"daily_posts_{stamp}.html"


def test_run_daily_report_with_latest_sends_one_email_with_csv_and_browser_html(monkeypatch, tmp_path):
    """Combined admin flow attaches daily CSV (+ contact CSVs) and browser HTML in one message."""
    repo = tmp_path / "checkout"
    _stub_fc_repo_root(repo)
    (repo / "report" / "search_combo").mkdir(parents=True)
    (repo / "report" / "search_combo" / "index.html").write_text("<html>playwright</html>", encoding="utf-8")
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(repo))

    rep_dir = tmp_path / "reports"
    rep_dir.mkdir()
    monkeypatch.setenv("REPORTS_DIR", str(rep_dir))
    _reset_db(monkeypatch, tmp_path, "combo_email.db")

    calls: list[dict] = []

    def fake_send(self, *, subject, report, analysis, csv_path=None, extra_attachments=None):
        calls.append(
            {
                "subject": subject,
                "csv_path": csv_path,
                "extras": list(extra_attachments or []),
            }
        )
        return True

    monkeypatch.setattr(pl.EmailReporter, "send_report_email", fake_send)
    settings = get_settings()
    out = pl.run_daily_report_with_latest_browser_html_email(settings)
    assert out["ok"] is True
    assert out["email_sent"] is True
    assert out["browser_html_email_sent"] is True
    assert len(calls) == 1
    assert "browser HTML" in calls[0]["subject"]
    assert calls[0]["csv_path"] is not None
    assert calls[0]["csv_path"].suffix == ".csv"
    extras = calls[0]["extras"]
    assert any(p.name.startswith("browser_search_") and p.suffix == ".html" for p in extras)
    assert out["browser_html_search_stamp"] == "combo"
    assert "_daily_" in out["browser_html_attachment"]
    assert out["browser_html_attachment"].endswith(".html")
    assert "daily_posts_" in out["daily_posts_html"]
    assert Path(out["daily_posts_html"]).is_file()
    html_paths = [p for p in extras if p.suffix == ".html"]
    assert len(html_paths) == 2
    assert any("daily_posts_" in p.name for p in html_paths)
    assert any("browser_search_" in p.name for p in html_paths)


def test_build_report_context_respects_publication_year_filter(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from src.db.db_models import Post
    from src.db.session import get_session

    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    _reset_db(monkeypatch, tmp_path, "report-year.db")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    get_settings.cache_clear()
    settings = get_settings()
    with get_session() as session:
        session.add(
            Post(
                id="old_ru",
                group_id="1",
                message="Ирина Шевченко 19 декабрь 2024 г.\nищу работу",
                source="graph",
            )
        )
        session.add(
            Post(
                id="new_ru",
                group_id="1",
                message="15 апрель 2026 г.\nищу работу",
                source="graph",
            )
        )
        session.add(
            Post(
                id="no_year_in_header",
                group_id="1",
                message="Сергей 13 январь · Ищу работу сварщиком",
                created_time=datetime(2025, 3, 1, tzinfo=timezone.utc),
                source="graph",
            )
        )
    with get_session() as session:
        report, rows = pl.build_report_context(session, settings)
    assert report.get("publication_year_filter") == 2026
    assert len(rows) == 1
    assert rows[0]["id"] == "new_ru"


def test_build_report_context_respects_publication_from_date(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from src.db.db_models import Post
    from src.db.session import get_session

    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_KEEP_UNKNOWN_YEAR", raising=False)
    _reset_db(monkeypatch, tmp_path, "report-from-date.db")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_MONTH", "4")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_DAY", "27")
    get_settings.cache_clear()
    settings = get_settings()
    with get_session() as session:
        session.add(
            Post(
                id="before_cutoff",
                group_id="1",
                message="20 апрель 2026 г.\nищу работу",
                source="graph",
            )
        )
        session.add(
            Post(
                id="on_cutoff",
                group_id="1",
                message="27 апрель 2026 г.\nищу работу",
                source="graph",
            )
        )
        session.add(
            Post(
                id="created_after",
                group_id="1",
                message="no parseable date",
                created_time=datetime(2026, 5, 1, tzinfo=timezone.utc),
                source="graph",
            )
        )
    with get_session() as session:
        report, rows = pl.build_report_context(session, settings)
    assert report.get("publication_from_date") == "2026-04-27"
    assert {r["id"] for r in rows} == {"on_cutoff", "created_after"}


def test_build_report_context_publication_year_keep_unknown(monkeypatch, tmp_path):
    from src.db.db_models import Post
    from src.db.session import get_session

    monkeypatch.delenv("BROWSER_POST_PUBLICATION_YEAR", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_MONTH", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_DAY", raising=False)
    monkeypatch.delenv("BROWSER_POST_PUBLICATION_KEEP_UNKNOWN_YEAR", raising=False)
    _reset_db(monkeypatch, tmp_path, "report-year-unknown.db")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_YEAR", "2026")
    monkeypatch.setenv("BROWSER_POST_PUBLICATION_KEEP_UNKNOWN_YEAR", "true")
    get_settings.cache_clear()
    settings = get_settings()
    with get_session() as session:
        session.add(
            Post(
                id="unknown_header",
                group_id="1",
                message="Сергей 13 январь · Ищу работу",
                source="graph",
            )
        )
        session.add(
            Post(
                id="match_2026",
                group_id="1",
                message="1 январь 2026 г. · текст",
                source="graph",
            )
        )
    with get_session() as session:
        report, rows = pl.build_report_context(session, settings)
    assert len(rows) == 2
    assert {r["id"] for r in rows} == {"unknown_header", "match_2026"}


def test_resolve_browser_search_html_report_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    _stub_fc_repo_root(tmp_path)
    d = tmp_path / "report" / "search_mytest"
    d.mkdir(parents=True)
    assert pl.resolve_browser_search_html_report_dir("mytest") == d.resolve()
    assert pl.resolve_browser_search_html_report_dir("search_mytest") == d.resolve()


def test_send_browser_search_html_report_email_missing_index(tmp_path):
    from src.config import Settings

    missing = tmp_path / "empty_dir"
    missing.mkdir()
    out = pl.send_browser_search_html_report_email(Settings(), report_dir=missing)
    assert out["ok"] is False
    assert "missing index.html" in (out.get("error") or "")


def test_run_sync_ok_false_when_graph_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "dummy-user-token")
    monkeypatch.setenv("FACEBOOK_GROUP_IDS", "161516504400077")
    _reset_db(monkeypatch, tmp_path, "t.db")

    class _FakeClient:
        def fetch_group_feed_with_diagnostics(self, group_id: str, *, limit: int = 75):
            return {
                "posts": [],
                "http_status": 400,
                "error": "(#3) Missing Permission",
                "raw_items_first_page": None,
            }

    monkeypatch.setattr(pl, "FacebookClient", lambda _s: _FakeClient())

    out = pl.run_sync()
    assert out["ok"] is False
    assert out["upserted"] == 0
    assert "Missing Permission" in (out.get("error") or "")
    assert out["feed"][0]["http_status"] == 400


def test_run_sync_ok_true_when_graph_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "dummy-user-token")
    monkeypatch.setenv("FACEBOOK_GROUP_IDS", "111")
    _reset_db(monkeypatch, tmp_path, "t2.db")

    class _FakeClient:
        def fetch_group_feed_with_diagnostics(self, group_id: str, *, limit: int = 75):
            return {
                "posts": [
                    {
                        "id": "111_1",
                        "group_id": group_id,
                        "message": "hi",
                        "author_id": "9",
                        "author_name": "A",
                        "created_time": None,
                        "raw_json": {},
                    }
                ],
                "http_status": 200,
                "error": None,
                "raw_items_first_page": 1,
            }

    monkeypatch.setattr(pl, "FacebookClient", lambda _s: _FakeClient())

    out = pl.run_sync()
    assert out["ok"] is True
    assert out["upserted"] == 1
    assert "error" not in out


def test_run_sync_me_mode_calls_me_feed(monkeypatch, tmp_path):
    monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "dummy-user-token")
    monkeypatch.setenv("FACEBOOK_GROUP_IDS", "")
    monkeypatch.setenv("FACEBOOK_SYNC_MODE", "me")
    _reset_db(monkeypatch, tmp_path, "t3.db")

    class _FakeClient:
        def fetch_me_feed_with_diagnostics(self, *, limit: int = 75):
            return {
                "posts": [
                    {
                        "id": "me_post_1",
                        "group_id": "user",
                        "message": "timeline",
                        "author_id": "1",
                        "author_name": "Self",
                        "created_time": None,
                        "raw_json": {},
                    }
                ],
                "http_status": 200,
                "error": None,
                "raw_items_first_page": 1,
            }

    monkeypatch.setattr(pl, "FacebookClient", lambda _s: _FakeClient())

    out = pl.run_sync()
    assert out.get("sync_mode") == "me"
    assert out["ok"] is True
    assert out["upserted"] == 1
    assert out["groups"] == 1
    assert out["feed"][0]["group_id"] == "user"


def test_run_browser_search_sync_disabled_returns_error(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("ENABLE_BROWSER_SEARCH_SYNC", raising=False)
    _reset_db(monkeypatch, tmp_path, "browser-disabled.db")

    out = pl.run_browser_search_sync()
    assert out["ok"] is False
    assert "disabled" in (out.get("error") or "")
    assert out.get("html_report_dir")
    assert (tmp_path / "report").is_dir()


def test_run_browser_search_sync_upserts_posts(monkeypatch, tmp_path):
    from sqlalchemy import select

    from src.db.db_models import Post
    from src.db.session import get_session

    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_BROWSER_SEARCH_SYNC", "true")
    monkeypatch.setenv("BROWSER_SEARCH_QUERY", "job")
    _reset_db(monkeypatch, tmp_path, "browser-upsert.db")

    def _fake_browser_search(
        _settings,
        *,
        query=None,
        in_group_query=None,
        in_group_queries=None,
        group_limit=None,
        post_limit_per_group=None,
        seed_groups=None,
        runner_factory=None,
        global_message_contains=None,
    ):
        _ = (
            group_limit,
            post_limit_per_group,
            runner_factory,
            seed_groups,
            in_group_queries,
            global_message_contains,
        )
        sq = query or "job"
        ig = (in_group_query or "").strip() or sq
        return {
            "ok": True,
            "query": sq,
            "in_group_query": ig,
            "groups_scanned": 2,
            "found_posts": 1,
            "errors": [],
            "groups": [
                {
                    "group_name": "Group A",
                    "group_id": "111",
                    "group_url": "https://www.facebook.com/groups/111",
                    "posts": [
                        {
                            "id": "pw_post_1",
                            "group_id": "111",
                            "message": "Senior job opening in Berlin",
                            "author_id": None,
                            "author_name": "Recruiter",
                            "created_time": None,
                            "raw_json": {"source_type": "playwright_browser"},
                        }
                    ],
                }
            ],
            "artifacts_dir": "output/playwright/test",
        }

    monkeypatch.setattr(pl, "run_browser_group_search", _fake_browser_search)

    out = pl.run_browser_search_sync(query="job", in_group_query="Berlin onsite")
    assert out["ok"] is True
    assert out.get("html_report_dir")
    assert (tmp_path / "report").is_dir()
    assert out["upserted"] == 1
    assert out["groups_scanned"] == 2
    assert out["groups_with_hits"] == 1
    assert out["in_group_query"] == "Berlin onsite"

    with get_session() as session:
        post = session.scalar(select(Post).where(Post.id == "pw_post_1"))
        assert post is not None
        assert post.source == "playwright_browser"
        assert "Berlin" in post.message


def test_run_browser_search_sync_passes_in_group_queries(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_BROWSER_SEARCH_SYNC", "true")
    _reset_db(monkeypatch, tmp_path, "browser-multi-ig.db")

    seen: dict[str, object] = {}

    def _fake(_settings, **kwargs):
        seen["in_group_queries"] = kwargs.get("in_group_queries")
        seen["global_message_contains"] = kwargs.get("global_message_contains")
        return {
            "ok": True,
            "query": "job",
            "in_group_query": "a",
            "in_group_queries": ["a", "b"],
            "global_message_contains": kwargs.get("global_message_contains"),
            "groups_scanned": 0,
            "groups": [],
            "found_posts": 0,
            "errors": [],
            "artifacts_dir": "",
        }

    monkeypatch.setattr(pl, "run_browser_group_search", _fake)
    out = pl.run_browser_search_sync(
        in_group_queries=["a", "b"],
        global_message_contains="ищу работу",
    )
    assert out["ok"] is True
    assert seen["in_group_queries"] == ["a", "b"]
    assert seen["global_message_contains"] == "ищу работу"
    assert out.get("in_group_queries") == ["a", "b"]
    assert out.get("global_message_contains") == "ищу работу"


def test_run_browser_search_sync_handles_login_timeout(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_BROWSER_SEARCH_SYNC", "true")
    _reset_db(monkeypatch, tmp_path, "browser-login.db")

    def _fake_browser_search(
        _settings,
        *,
        query=None,
        in_group_query=None,
        in_group_queries=None,
        group_limit=None,
        post_limit_per_group=None,
        seed_groups=None,
        runner_factory=None,
        global_message_contains=None,
    ):
        _ = (
            query,
            in_group_query,
            in_group_queries,
            group_limit,
            post_limit_per_group,
            runner_factory,
            seed_groups,
            global_message_contains,
        )
        raise pl.ManualLoginRequiredError("manual Facebook login was not completed before timeout")

    monkeypatch.setattr(pl, "run_browser_group_search", _fake_browser_search)

    out = pl.run_browser_search_sync()
    assert out["ok"] is False
    assert "manual Facebook login" in (out.get("error") or "")
    assert out.get("html_report_dir")


def test_run_browser_search_sync_duplicate_post_id_across_groups_commits(monkeypatch, tmp_path):
    """Same post id in two groups must not raise UNIQUE (regression: autoflush=False + pending inserts)."""
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_BROWSER_SEARCH_SYNC", "true")
    _reset_db(monkeypatch, tmp_path, "browser-dup-groups.db")

    post = {
        "id": "shared_story_id",
        "group_id": "111",
        "message": "dup",
        "author_id": None,
        "author_name": None,
        "created_time": None,
        "raw_json": {},
    }

    def _fake_browser_search(_settings, **kwargs):
        _ = kwargs.get("in_group_queries")
        return {
            "ok": True,
            "query": "job",
            "in_group_query": "job",
            "groups_scanned": 2,
            "found_posts": 2,
            "errors": [],
            "groups": [
                {
                    "group_name": "A",
                    "group_id": "111",
                    "group_url": "https://www.facebook.com/groups/111",
                    "posts": [post],
                },
                {
                    "group_name": "B",
                    "group_id": "222",
                    "group_url": "https://www.facebook.com/groups/222",
                    "posts": [{**post, "group_id": "222"}],
                },
            ],
            "artifacts_dir": "output/playwright/dup",
        }

    monkeypatch.setattr(pl, "run_browser_group_search", _fake_browser_search)
    out = pl.run_browser_search_sync()
    assert out["ok"] is True
    assert out["upserted"] == 2


def test_run_browser_search_sync_forwards_seed_group_urls(monkeypatch, tmp_path):
    _stub_fc_repo_root(tmp_path)
    monkeypatch.setenv("FC_SEARCHER_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ENABLE_BROWSER_SEARCH_SYNC", "true")
    monkeypatch.delenv("BROWSER_SEED_GROUP_URLS", raising=False)
    _reset_db(monkeypatch, tmp_path, "browser-seed-forward.db")

    seen: dict[str, object] = {}

    def _fake(settings, **kwargs):
        seen["seed_groups"] = kwargs.get("seed_groups")
        return {
            "ok": True,
            "query": kwargs.get("query") or "job",
            "groups_scanned": 0,
            "groups": [],
            "found_posts": 0,
            "errors": [],
            "artifacts_dir": "",
        }

    monkeypatch.setattr(pl, "run_browser_group_search", _fake)

    out = pl.run_browser_search_sync(seed_group_urls="https://www.facebook.com/groups/934750153812574/")
    assert out.get("html_report_dir")
    sg = seen.get("seed_groups")
    assert sg is not None
    assert len(sg) == 1
    assert sg[0].group_url == "https://www.facebook.com/groups/934750153812574"


def test_upsert_posts_stores_permalink_and_extracts_contacts(monkeypatch, tmp_path):
    from sqlalchemy import select

    from src.db.db_models import ExtractedEmail, ExtractedPhone, Post
    from src.db.session import get_session

    _reset_db(monkeypatch, tmp_path, "contacts.db")
    batch = [
        {
            "id": "p1",
            "group_id": "g1",
            "message": "Call +1 415-555-0100 or email hiring@example.com",
            "author_id": None,
            "author_name": "A",
            "created_time": None,
            "permalink_url": "https://www.facebook.com/groups/g1/posts/123/",
            "raw_json": {},
        }
    ]
    with get_session() as session:
        n = pl.upsert_posts(session, batch, source="graph")
        assert n == 1
    with get_session() as session:
        row = session.scalar(select(Post).where(Post.id == "p1"))
        assert row is not None
        assert row.permalink_url and "facebook.com" in row.permalink_url
        phones = list(session.scalars(select(ExtractedPhone).where(ExtractedPhone.post_id == "p1")))
        emails = list(session.scalars(select(ExtractedEmail).where(ExtractedEmail.post_id == "p1")))
        assert len(phones) >= 1
        assert any("415" in p.phone_normalized for p in phones)
        assert len(emails) == 1
        assert "hiring@example.com" in emails[0].email_normalized


def test_upsert_posts_deduplicates_duplicate_ids_in_one_batch(monkeypatch, tmp_path):
    from sqlalchemy import select

    from src.db.db_models import Post
    from src.db.session import get_session

    _reset_db(monkeypatch, tmp_path, "dedupe.db")
    dupes = [
        {"id": "same_id", "group_id": "1", "message": "first", "author_id": None, "author_name": None, "created_time": None, "raw_json": {}},
        {"id": "same_id", "group_id": "1", "message": "second wins", "author_id": None, "author_name": None, "created_time": None, "raw_json": {}},
    ]
    with get_session() as session:
        n = pl.upsert_posts(session, dupes, source="playwright_browser")
        assert n == 1
    with get_session() as session:
        row = session.scalar(select(Post).where(Post.id == "same_id"))
        assert row is not None
        assert row.message == "second wins"
