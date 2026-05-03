#!/usr/bin/env python3
"""Print per-group activity vs the same rules as the daily CSV (top 500 by fetched_at + publication filter).

Run **from your fc_searcher repository root** (not a literal ``/path/to/...``).

Host::

    python scripts/analyze_watch_groups_report_slice.py

Production SQLite **inside** the default container (pipe script; image has no ``scripts/``)::

    docker compose exec -T -e FC_SEARCHER_REPO_ROOT=/app facebook-monitor \\
      sh -c 'cd /app && PYTHONPATH=/app python -' < scripts/analyze_watch_groups_report_slice.py

``docker-compose.prod.yml`` adds Postgres and requires ``POSTGRES_PASSWORD`` in the environment
before ``docker compose`` parses the file; omit ``-f docker-compose.prod.yml`` if you use SQLite only.

Copy DB then analyze on host::

    docker cp facebook-monitor:/app/data/facebook_monitor.db ./data/facebook_monitor.production.sqlite
    DATABASE_URL=sqlite:////$(pwd)/data/facebook_monitor.production.sqlite python scripts/analyze_watch_groups_report_slice.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select


def _repo_root() -> Path:
    env = (os.environ.get("FC_SEARCHER_REPO_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = globals().get("__file__")
    if here:
        return Path(here).resolve().parent.parent
    return Path.cwd().resolve()


def _load_env(root: Path) -> None:
    if (root / "scripts" / "load_repo_env.py").is_file():
        sys.path.insert(0, str(root / "scripts"))
        from load_repo_env import load_dotenv_file

        load_dotenv_file(root / ".env")
        return
    dotenv_path = root / ".env"
    if dotenv_path.is_file():
        from dotenv import load_dotenv

        load_dotenv(dotenv_path, override=False)


def main() -> None:
    root = _repo_root()
    sys.path.insert(0, str(root))
    _load_env(root)

    from src.config import clear_settings_caches, get_settings
    from src.db.db_models import Post
    from src.db.session import get_session, init_engine, normalize_database_url
    from src.services.browser_search import parse_seed_group_urls
    from src.services.pipeline import _post_matches_publication_filter_for_report, build_report_context

    clear_settings_caches()
    settings = get_settings()
    db_url = normalize_database_url(settings.database_url, base_dir=root)
    init_engine(db_url)

    seeds = parse_seed_group_urls(settings.browser_seed_group_urls)
    seed_ids = {g.group_id for g in seeds if g.group_id}
    graph_ids = set(settings.group_id_list())
    watch_ids = seed_ids | graph_ids

    with get_session() as session:
        report, rows = build_report_context(session, settings)
        groups_in_report = set(report.get("groups") or [])

        all_posts = list(session.scalars(select(Post)).all())
        if settings.browser_post_publication_year is not None:
            all_posts = [p for p in all_posts if _post_matches_publication_filter_for_report(p, settings)]

        counts_total: dict[str, int] = defaultdict(int)
        counts_browser: dict[str, int] = defaultdict(int)
        for p in all_posts:
            gid = p.group_id or ""
            counts_total[gid] += 1
            if p.source == "playwright_browser":
                counts_browser[gid] += 1

        posts500 = list(session.scalars(select(Post).order_by(Post.fetched_at.desc()).limit(500)).all())
        if settings.browser_post_publication_year is not None:
            posts500 = [p for p in posts500 if _post_matches_publication_filter_for_report(p, settings)]
        groups_in_top500 = {p.group_id for p in posts500 if p.group_id}

    def keyf(x: str) -> int:
        return int(x) if x.isdigit() else 0

    print("DATABASE_URL (normalized):", db_url)
    print("Publication filter:", report.get("publication_year_filter"), report.get("publication_from_date"))
    print("Report rows:", len(rows), "| distinct groups in report:", len(groups_in_report))
    print()
    print("Seed IDs:", sorted(seed_ids, key=keyf))
    print("FACEBOOK_GROUP_IDS:", sorted(graph_ids, key=keyf))
    print()

    no_posts: list[str] = []
    not_in_report: list[str] = []
    for gid in sorted(watch_ids, key=keyf):
        in_rep = gid in groups_in_report
        tot = counts_total.get(gid, 0)
        br = counts_browser.get(gid, 0)
        in_top = gid in groups_in_top500
        if tot == 0 and br == 0:
            flag = "NO_MATCHING_POSTS_IN_DB"
            no_posts.append(gid)
        elif not in_rep:
            flag = "NOT_IN_CURRENT_REPORT_TOP500"
            not_in_report.append(gid)
        else:
            flag = "in_report"
        print(f"{gid}\t total={tot}\t playwright={br}\t in_report={in_rep}\t in_top500={in_top}\t {flag}")

    keep = sorted(watch_ids - set(no_posts), key=keyf)
    print()
    print("=== Suggested remove (zero matching posts) ===")
    print(no_posts)
    print("Crowded out of 500-row slice (has posts, not in current report):", not_in_report)
    print()
    print("=== Suggested FACEBOOK_GROUP_IDS (keep) ===")
    print(",".join(keep))
    seed_urls = [g.group_url for g in seeds if g.group_id and g.group_id not in set(no_posts)]
    if seed_urls:
        print("=== Suggested BROWSER_SEED_GROUP_URLS (keep) ===")
        print(",".join(seed_urls))


if __name__ == "__main__":
    main()
