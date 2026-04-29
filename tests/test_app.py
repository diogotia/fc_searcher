from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "facebook_group_ids_count" in data
    assert "facebook_mock_feed_json" in data
    assert "facebook_sync_mode" in data
    assert data.get("enable_public_post_search") is False
    assert data.get("enable_browser_search_sync") is False
    assert data.get("browser_search_query") == "job"
    assert data.get("browser_headless") is False
    assert data.get("browser_seed_group_urls_configured") is False


def test_metrics(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"# HELP" in resp.data or b"# TYPE" in resp.data


def test_webhook_verify_success(client):
    resp = client.get(
        "/webhook/facebook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "123456",
        },
    )
    assert resp.status_code == 200
    assert resp.data.decode() == "123456"


def test_webhook_verify_failure(client):
    resp = client.get(
        "/webhook/facebook",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "123456",
        },
    )
    assert resp.status_code == 403


def test_admin_sync_requires_token(client):
    resp = client.post("/admin/sync")
    assert resp.status_code == 401


def test_admin_sync_without_graph_token(client):
    resp = client.post("/admin/sync", headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False


def test_admin_posts_search_requires_token(client):
    resp = client.get("/admin/posts/search?q=hello")
    assert resp.status_code == 401


def test_admin_report_browser_html_requires_token(client):
    resp = client.post("/admin/report-browser-html", json={"search_folder": "search_x"})
    assert resp.status_code == 401


def test_admin_report_browser_html_requires_search_folder(client):
    resp = client.post(
        "/admin/report-browser-html",
        headers={"X-Admin-Token": "test-admin-token"},
        json={},
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_admin_report_browser_html_ok(client, monkeypatch):
    monkeypatch.setattr(
        "src.api.routes_admin.send_browser_search_html_report_email",
        lambda _settings, **kw: {
            "ok": True,
            "email_sent": False,
            "html_report_dir": "/tmp/report/search_x",
            "attachment": "browser_search_search_x.html",
        },
    )
    resp = client.post(
        "/admin/report-browser-html",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"search_folder": "search_20260426T113551Z"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["html_report_dir"] == "/tmp/report/search_x"


def test_admin_report_browser_html_last_merges_daily_shape(client, monkeypatch):
    def _fake_combined(_settings):
        return {
            "ok": True,
            "date": "2026-04-29",
            "run_stamp": "20260429T999999Z",
            "email_sent": True,
            "csv": "/app/reports/report_2026-04-29_20260429T999999Z.csv",
            "rows": 12,
            "phones_exported": 1,
            "emails_exported": 0,
            "publication_year_filter": 2026,
            "publication_from_date": "2026-04-27",
            "phones_csv": "/app/reports/x_phones.csv",
            "html_report_dir": "/app/report/search_latest",
            "browser_html_email_sent": True,
            "browser_html_ok": True,
            "browser_html_attachment": "browser_search_search_latest.html",
        }

    monkeypatch.setattr(
        "src.api.routes_admin.run_daily_report_with_latest_browser_html_email",
        _fake_combined,
    )
    resp = client.post(
        "/admin/report-browser-html-last",
        headers={"X-Admin-Token": "test-admin-token"},
        json={},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["rows"] == 12
    assert body["csv"].endswith(".csv")
    assert body["html_report_dir"] == "/app/report/search_latest"
    assert body["browser_html_email_sent"] is True


def test_admin_browser_search_sync_requires_token(client):
    resp = client.post("/admin/browser-search-sync")
    assert resp.status_code == 401


def test_admin_browser_search_sync_disabled_by_default(client):
    resp = client.post("/admin/browser-search-sync", headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert "disabled" in body["error"]


def test_admin_browser_search_sync_uses_payload(client, monkeypatch):
    def _fake_run(
        settings=None,
        *,
        query=None,
        in_group_query=None,
        in_group_queries=None,
        group_limit=None,
        post_limit_per_group=None,
        seed_group_urls=None,
        global_message_contains=None,
    ):
        return {
            "ok": True,
            "query": query,
            "in_group_query": in_group_query or query,
            "in_group_queries": in_group_queries,
            "global_message_contains": global_message_contains,
            "groups_scanned": int(group_limit or 0),
            "groups_with_hits": 1,
            "upserted": int(post_limit_per_group or 0),
            "found_posts": int(post_limit_per_group or 0),
            "errors": [],
        }

    monkeypatch.setattr("src.api.routes_admin.run_browser_search_sync", _fake_run)
    resp = client.post(
        "/admin/browser-search-sync",
        headers={"X-Admin-Token": "test-admin-token"},
        json={
            "query": "designer",
            "in_group_query": "UX lead",
            "group_limit": 3,
            "post_limit_per_group": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["query"] == "designer"
    assert body["in_group_query"] == "UX lead"
    assert body["groups_scanned"] == 3
    assert body["upserted"] == 5


def test_admin_browser_search_sync_forwards_global_message_contains(client, monkeypatch):
    captured: dict[str, object] = {}

    def _fake_run(settings=None, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "errors": []}

    monkeypatch.setattr("src.api.routes_admin.run_browser_search_sync", _fake_run)
    resp = client.post(
        "/admin/browser-search-sync",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"global_message_contains": "ищу работу"},
    )
    assert resp.status_code == 200
    assert captured.get("global_message_contains") == "ищу работу"


def test_admin_browser_search_sync_forwards_in_group_queries(client, monkeypatch):
    captured: dict[str, object] = {}

    def _fake_run(settings=None, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "errors": []}

    monkeypatch.setattr("src.api.routes_admin.run_browser_search_sync", _fake_run)
    resp = client.post(
        "/admin/browser-search-sync",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"in_group_queries": ["ищу работу", "рабочий строительства"]},
    )
    assert resp.status_code == 200
    assert captured.get("in_group_queries") == ["ищу работу", "рабочий строительства"]


def test_admin_posts_search_requires_q(client):
    resp = client.get("/admin/posts/search", headers={"X-Admin-Token": "test-admin-token"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_admin_posts_search_finds_message(client, app):
    from datetime import datetime, timezone

    from sqlalchemy import select

    from src.db.db_models import Post
    from src.db.session import get_session

    with app.app_context():
        with get_session() as session:
            session.add(
                Post(
                    id="p1",
                    group_id="999",
                    message="Berlin office space available",
                    author_id="u1",
                    author_name="A",
                    created_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    raw_json=None,
                    source="mock_json",
                )
            )
        with get_session() as session:
            assert session.scalar(select(Post).where(Post.id == "p1")) is not None

    resp = client.get(
        "/admin/posts/search?q=berlin",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["posts"][0]["id"] == "p1"
    assert "Berlin" in data["posts"][0]["message"]

    resp2 = client.get(
        "/admin/posts/search?q=berlin&group_id=888",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert resp2.status_code == 200
    assert resp2.get_json()["count"] == 0


def test_public_search_disabled_by_default(client):
    resp = client.get("/search?q=test")
    assert resp.status_code == 403
    assert resp.get_json()["ok"] is False


def test_public_search_requires_q(client_public_search):
    resp = client_public_search.get("/search")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_public_search_finds_without_admin_token(client_public_search, app_public_search):
    from datetime import datetime, timezone

    from src.db.db_models import Post
    from src.db.session import get_session

    with app_public_search.app_context():
        with get_session() as session:
            session.add(
                Post(
                    id="pub1",
                    group_id="999",
                    message="Munich workshop this weekend",
                    author_id="u2",
                    author_name="B",
                    created_time=datetime(2025, 2, 1, tzinfo=timezone.utc),
                    raw_json=None,
                    source="mock_json",
                )
            )

    resp = client_public_search.get("/search?q=munich")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["posts"][0]["id"] == "pub1"
