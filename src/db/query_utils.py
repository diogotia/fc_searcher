"""Query helpers (eager loading, common filters)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.db_models import Post


def fetch_posts_for_group_with_analyses(
    session: Session,
    group_id: str,
    *,
    limit: int = 100,
) -> list[Post]:
    """Return recent posts for a group with ``analyses`` preloaded (avoids N+1)."""
    lim = max(1, min(limit, 500))
    stmt = (
        select(Post)
        .where(Post.group_id == group_id)
        .options(selectinload(Post.analyses))
        .order_by(Post.fetched_at.desc())
        .limit(lim)
    )
    return list(session.scalars(stmt).all())
