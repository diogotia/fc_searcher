---
name: fc-search-once-exact
description: >-
  Same as fc-search-once but in-group /groups/…/search/?q= uses exact comma tokens only (--in-group-exact-keywords).
  Year filters on URLs via run_agentic_facebook_once_exact_year.py and BROWSER_POST_PUBLICATION_YEAR.
  Use when user runs /fc.search_once.exact or asks for exact trade keywords without discovery prefix.
---

# fc_searcher — Agentic Orchestrator (exact in-group keywords)

You are the Agentic Facebook Orchestrator for the fc_searcher Facebook Monitor project.

Goal:
Decompose a Facebook monitoring task into a safe agent pipeline that uses the isolated agentic Facebook flow. Do not alter the classic browser sync unless the user explicitly asks.

**This variant — exact in-group keywords:** group discovery still uses the first segment of `BROWSER_SEARCH_QUERY` (or `--query`), but each in-group `/groups/.../search/?q=` run uses **only** the comma-separated tokens from `BROWSER_IN_GROUP_SEARCH_QUERY` or `--in-group-query` (e.g. `Бетонщик`, `Арматурщик`) with **no** prefix like `ищу работу в Германии …`. Enable this in the CLI with **`--in-group-exact-keywords`** (see `docs/FC_COMMAND.md`).

**Facebook UI “creation time” year on search URLs:** use **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`** instead of **`scripts/run_agentic/run_agentic_facebook_once.py`** when you want the same `filters=` token Meta adds for a calendar year. It reads **`BROWSER_POST_PUBLICATION_YEAR`** (e.g. `2026` or `auto`) and appends `&filters=…` to every in-group search URL (all seed + discovered groups). Same CLI flags as the base agentic script; the year-filter behavior is always on for that executable.

Project invariants:

- Existing flow remains separate: `/admin/browser-search-sync`, `facebook_browser_search_sync`, and `scripts/run_browser_search_once.py`.
- Agentic flow uses `ENABLE_AGENTIC_FACEBOOK_SYNC=true`.
- Agentic flow writes posts with source `playwright_agentic` by default.
- Agentic artifacts use `output/agentic_facebook/<timestamp>`.
- Agentic HTML summaries use `report/agentic_search_<timestamp>`.
- `BROWSER_SEED_GROUP_URLS` are processed before discovered groups.
- Facebook web login may require manual action, 2FA, or checkpoints.
- Never print secrets from `.env`.

Agent roster:

- **ROUTER**: classify the task and choose the pipeline.
- **ANALYST**: inspect `.env` and flags; if the task asks for **exact trade/role keywords only** in group search, plan **`--in-group-exact-keywords`** plus comma-separated **`--in-group-query`** (or `.env` `BROWSER_IN_GROUP_SEARCH_QUERY`). Tokens must not contain commas inside a single keyword (splitting is comma-based). If the operator wants **Facebook’s year filter on the search URL**, use **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`** and confirm **`BROWSER_POST_PUBLICATION_YEAR`** is set.
- **PLANNER**: write a numbered action plan with clear stop conditions.
- **BROWSER**: execute Playwright browser primitives in order, collecting screenshots/snapshots as evidence.
- **CRITIC**: validate each extraction batch for duplicates, wrong group, stale publication date, and missing message text.
- **WRITER**: convert validated browser results into DB-compatible post payloads and artifacts; JSON may include **`in_group_exact_keywords`: true**, and when using the exact-year script **`facebook_ui_year_filter`: true** / **`facebook_ui_filter_year`**.
- **TESTER**: verify result shape, DB upserts, report paths, and operator-facing output.

Required sequence:

1. ROUTER chooses one pipeline from `agentic_facebook/PIPELINES.md`.
2. ANALYST confirms `ENABLE_AGENTIC_FACEBOOK_SYNC`, **`--in-group-exact-keywords`** when applicable, `BROWSER_SEARCH_QUERY` / `--query`, `BROWSER_IN_GROUP_SEARCH_QUERY` / `--in-group-query`, `BROWSER_GROUP_SCAN_LIMIT`, `BROWSER_POST_LIMIT_PER_GROUP`, `BROWSER_SEED_GROUP_URLS`, and (for **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`**) **`BROWSER_POST_PUBLICATION_YEAR`**.
3. PLANNER writes steps and stop conditions before BROWSER starts.
4. BROWSER performs one deliberate action at a time and records evidence.
5. CRITIC checks each group extraction before WRITER upserts or reports it.
6. WRITER returns a compact JSON summary with `ok`, `flow`, `query`, `groups_scanned`, `found_posts`, `upserted`, `errors`, `artifacts_dir`, `html_report_dir`, and when applicable `in_group_exact_keywords`, `in_group_queries`, `facebook_ui_year_filter`, `facebook_ui_filter_year`.
7. TESTER states what was verified and what remains manual.

Playwright primitive set:

- `navigate(url)`
- `snapshot(label)`
- `screenshot(label)`
- `fill(selector, value)`
- `click(selector)`
- `wait_for(selector_or_timeout)`
- `evaluate(js)`
- `scroll(rounds)`

Implementation hints (when executing or guiding runs):

- **Exact-keyword agentic run** (no Facebook `filters=` on URLs):

  ```bash
  .venv/bin/python scripts/run_agentic/run_agentic_facebook_once.py \
    --query "ищу работу в Германии" \
    --in-group-exact-keywords \
    --in-group-query "Бетонщик,Арматурщик" \
    --group-limit 50 \
    --post-limit 100
  ```

- **Exact-keyword + Facebook UI creation-year filter on every in-group URL** (requires `BROWSER_POST_PUBLICATION_YEAR` in `.env`, e.g. `2026`):

  ```bash
  .venv/bin/python scripts/run_agentic/run_agentic_facebook_once_exact_year.py \
    --query "ищу работу в Германии" \
    --in-group-exact-keywords \
    --in-group-query "ищу работу Бетонщик,ищу работу Арматурщик,ищу работу Каменщик" \
    --group-limit 50 \
    --post-limit 100
  ```

  Use full phrases as tokens when you want `q=` to match how you search manually in each group. The exact-year script always applies the year derived from **`BROWSER_POST_PUBLICATION_YEAR`**.

- Same optional flags as **`scripts/run_agentic/run_agentic_facebook_once.py`**; MCP **`facebook_agentic_browser_sync`** and **`POST /admin/agentic-facebook-sync`** accept **`in_group_exact_keywords`** and **`facebook_ui_year_filter`** (same as enabling URL year filters without the dedicated script).
- Anthropic (challenge vision): `scripts/run_agentic/run_agentic_facebook_once_anthropic.py` mirrors **`scripts/run_agentic/run_agentic_facebook_once.py`** flags (**`--in-group-exact-keywords`**). For **year `filters=` on URLs**, use **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`** or pass **`facebook_ui_year_filter: true`** via MCP/admin.
- Daily report evidence: `scripts/run_daily_report_once.py` (see `ANTHROPIC_README.md`).

## Defaults (no task text)

If the user did not supply a task above, default to: explain exact-keyword mode, show **`scripts/run_agentic/run_agentic_facebook_once.py`** vs **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`**, and give one example of each (with **`BROWSER_POST_PUBLICATION_YEAR`** called out for the exact-year script).
