from __future__ import annotations

from src.logging_config import get_logger
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import Session, sessionmaker

from src.db.db_models import Base

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _is_fc_searcher_repo_root(path: Path) -> bool:
    """True if ``path`` looks like this repository (has ``src/config.py``)."""
    try:
        return (path / "src" / "config.py").is_file()
    except OSError:
        return False


def _repo_base_dir() -> Path:
    """Prefer ``FC_SEARCHER_REPO_ROOT`` when it points at a real checkout; else cwd.

    A mis-set ``FC_SEARCHER_REPO_ROOT`` (e.g. path duplicated) breaks ``sqlite:///./data/...``
    resolution and yields ``.../fc_searcher/Users/.../data/...`` style paths.
    """
    cwd = Path.cwd().resolve()
    root = (os.environ.get("FC_SEARCHER_REPO_ROOT") or "").strip()
    if not root:
        return cwd
    candidate = Path(root).resolve()
    if _is_fc_searcher_repo_root(candidate):
        return candidate
    if _is_fc_searcher_repo_root(cwd):
        logger.warning(
            "FC_SEARCHER_REPO_ROOT=%s is not a valid fc_searcher checkout (missing src/config.py); "
            "using cwd %s for SQLite path resolution",
            candidate,
            cwd,
        )
        return cwd
    return candidate


def normalize_database_url(database_url: str, *, base_dir: Path | None = None) -> str:
    """Make SQLite URLs usable on the host (MCP, scripts) when `.env` has Docker paths or relative paths.

    - Relative file paths resolve against ``FC_SEARCHER_REPO_ROOT`` (set by ``run_mcp_server.sh``) or cwd.
    - ``/app/data/...`` (Docker-only) is rewritten to ``<repo>/data/facebook_monitor.db`` when ``/app`` is absent.
    - ``sqlite:///Users/...`` or ``sqlite:///./Users/...`` (relative-looking home paths) are treated as
      ``/Users/...`` so they are not joined to the repo cwd.
    """
    try:
        u = make_url(database_url)
    except Exception:
        return database_url
    if u.drivername != "sqlite":
        return database_url
    db = (u.database or "").strip()
    if not db or db == ":memory:":
        return database_url
    base = (base_dir or _repo_base_dir()).resolve()
    if db.startswith("/app/") and not Path("/app").exists():
        resolved = (base / "data" / "facebook_monitor.db").resolve()
        return str(URL.create("sqlite", database=str(resolved)))
    path = Path(db)
    if path.is_absolute():
        return database_url
    # ``sqlite:///Users/...`` (three slashes) is a common mistake for an absolute path; SQLAlchemy
    # then yields database ``Users/...`` (no leading slash), which would wrongly join to ``base``.
    # ``sqlite:///./Users/...`` yields ``./Users/...`` — same problem after stripping the leading ``./``.
    posix = db.replace("\\", "/")
    posix_unprefixed = posix[2:] if posix.startswith("./") else posix
    mistaken_unix_abs = (
        posix_unprefixed.startswith("Users/")
        or posix_unprefixed.startswith("home/")
        or posix_unprefixed.startswith("private/")
        or posix_unprefixed.startswith("Volumes/")
    )
    if mistaken_unix_abs:
        abs_path = (Path("/") / posix_unprefixed).resolve()
        return str(URL.create("sqlite", database=str(abs_path)))
    resolved = (base / path).resolve()
    return str(URL.create("sqlite", database=str(resolved)))


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """Create parent directory for file-backed SQLite so local/MCP runs do not fail on missing ./data/."""
    try:
        u = make_url(database_url)
    except Exception:
        return
    if u.drivername != "sqlite":
        return
    db = (u.database or "").strip()
    if not db or db == ":memory:":
        return
    path = Path(db)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Let create_engine surface permission errors (e.g. /app/data on a host without Docker paths).
        pass


def init_engine(database_url: str) -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    database_url = normalize_database_url(database_url)
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        _ensure_sqlite_parent_dir(database_url)
    _engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        raise RuntimeError("Database session factory not initialized.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_post_permalink_column(engine: Engine) -> None:
    """``create_all`` does not add new columns to existing tables (upgrades)."""
    try:
        cols = inspect(engine).get_columns("posts")
    except Exception:
        return
    names = {c["name"] for c in cols}
    if "permalink_url" in names:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE posts ADD COLUMN permalink_url VARCHAR(2048)"))


def init_db() -> None:
    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    _ensure_post_permalink_column(eng)
