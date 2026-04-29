from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from src.db.db_models import Post
from src.db.session import get_session


def _escape_like_fragment(s: str) -> str:
    """Escape `%`, `_`, and `\\` for SQL LIKE with a backslash escape character."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_stored_posts(
    *,
    query: str,
    group_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Case-insensitive substring search on `Post.message` (stored posts only)."""
    raw = query.strip()
    if not raw:
        return []
    pat = f"%{_escape_like_fragment(raw.lower())}%"
    lim = max(1, min(limit, 200))
    with get_session() as session:
        stmt = select(Post).where(func.lower(Post.message).like(pat, escape="\\"))
        if group_id is not None and group_id.strip():
            stmt = stmt.where(Post.group_id == group_id.strip())
        stmt = stmt.order_by(Post.fetched_at.desc()).limit(lim)
        rows = session.scalars(stmt).all()
        out: list[dict[str, Any]] = []
        for p in rows:
            out.append(
                {
                    "id": p.id,
                    "group_id": p.group_id,
                    "message": p.message,
                    "author_id": p.author_id,
                    "author_name": p.author_name,
                    "created_time": p.created_time.isoformat() if p.created_time else None,
                    "source": p.source,
                    "fetched_at": p.fetched_at.isoformat(),
                }
            )
        return out
