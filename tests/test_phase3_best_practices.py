"""Phase 3 — reliability / best-practices (health probes, circuit breaker, query helpers)."""

from __future__ import annotations

import pytest

from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


def test_health_alive(client):
    resp = client.get("/health/alive")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "alive"}


def test_health_ready(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.get_json() == {"ready": True}


def test_circuit_breaker_opens_then_blocks():
    cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=3600)

    def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        cb.call(boom)
    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.state == CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        cb.call(lambda: None)

    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_timing_context_runs():
    from src.context_managers import timing_context

    with timing_context("noop"):
        pass


def test_error_handling_suppress():
    from src.context_managers import error_handling

    with error_handling("x", on_error="suppress"):
        raise RuntimeError("ignored")


def test_fetch_posts_for_group_with_analyses(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from src.config import clear_settings_caches, get_settings
    from src.db.db_models import Analysis, Post
    from src.db.query_utils import fetch_posts_for_group_with_analyses
    from src.db.session import get_session, init_db, init_engine

    db_path = tmp_path / "q.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:////{db_path}")
    clear_settings_caches()
    init_engine(get_settings().database_url)
    init_db()

    with get_session() as session:
        session.add(
            Post(
                id="p1",
                group_id="g1",
                message="hello",
                created_time=datetime.now(timezone.utc),
                source="graph",
            )
        )
        session.add(
            Analysis(post_id="p1", model="m", summary="s"),
        )

    with get_session() as session:
        posts = fetch_posts_for_group_with_analyses(session, "g1", limit=10)
        assert len(posts) == 1
        assert posts[0].id == "p1"
        assert len(posts[0].analyses) == 1
