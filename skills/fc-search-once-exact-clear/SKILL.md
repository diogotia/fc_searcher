---
name: fc-search-once-exact-clear
description: >-
  Agentic orchestrator variant using run_agentic_facebook_exact_posts.py — Ещё/See more expansion plus a
  two-stage body filter: mandatory --global-message-contains AND optional in-post trade-keyword OR list
  (BROWSER_IN_GROUP_SEARCH_IN_POST). Use when user runs /fc.search_once.exact.clear or wants fuller post
  text with stricter, role-aware DB rows.
---

# fc_searcher — Agentic Orchestrator (exact + full-body / “clear”)

You are the Agentic Facebook Orchestrator for the fc_searcher Facebook Monitor project.

Goal:
Decompose a Facebook monitoring task into a safe agent pipeline that uses the isolated agentic Facebook flow. Do not alter the classic browser sync unless the user explicitly asks.

**This variant — “clear” / full-context posts:** Prefer **`scripts/run_agentic/run_agentic_facebook_exact_posts.py`** instead of **`scripts/run_agentic/run_agentic_facebook_once.py`** when the operator wants:

1. **Expanded post text:** After each in-group search navigation, the browser scrolls and clicks **Ещё** / **See more** controls (best-effort) before scraping DOM text so `message` reflects fuller content Meta hides behind truncation.

2. **Two-stage body filter (AND/OR):** Per scraped post, validate body in two stages and only upsert posts that pass both:
   - **AND (mandatory):** post body must contain the **`--global-message-contains`** phrase (or `BROWSER_GLOBAL_MESSAGE_CONTAINS`), e.g. `ищу работу`. Empty value disables this stage.
   - **OR (trade list):** post body must contain at least one token from **`--in-post-keywords`** (CLI) or **`BROWSER_IN_GROUP_SEARCH_IN_POST`** (`.env`), e.g. `Каменщик,Бетонщик,Арматурщик,Монтажник металлоконструкций,Кровельщик,Плотник,Столяр,Штукатур,Маляр,Плиточник облицовщик,Гипсокартонщик,Фасадчик,Изолировщик`. Empty value disables this stage.

   Matching uses **Unicode NFC + case-folding** (so `КАМЕНЩИК`, `каменщик`, and mixed case match). Each CSV token is the **canonical key** returned on the post as `matched_in_post_keyword`. Built-in **synonyms/typos** (e.g. `штукатурка` → `штукатур`, `гипсакартон` → `гипсокартон`, `ГКЛ` / `гкл`) are tried per profession; if the text matched a synonym rather than the exact CSV spelling, `matched_in_post_variant` is set and the report badge’s tooltip shows it. If two canons could match, **earlier CSV tokens win**—put more specific roles first.

   This **replaces** the old implicit union of `--in-group-query` ∪ `--query`. To keep some posts when the OR list is empty, leave `BROWSER_IN_GROUP_SEARCH_IN_POST` blank — the OR stage becomes a no-op and only `--global-message-contains` applies.

Combine with **`--in-group-exact-keywords`** (default **on** for this script) when in-group `q=` should use tokens only (see skill **`fc-search-once-exact`**). For Facebook **`filters=`** year on URLs, set **`BROWSER_POST_PUBLICATION_YEAR`** in `.env`; this script will append the same `filters=` token as `scripts/run_agentic/run_agentic_facebook_once_exact_year.py` automatically.

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
- **ANALYST**: If full body text and role-aware DB rows matter, plan **`scripts/run_agentic/run_agentic_facebook_exact_posts.py`** with **`--query`**, **`--in-group-query`**, **`--global-message-contains`** (mandatory AND phrase), and **`--in-post-keywords`** (or `BROWSER_IN_GROUP_SEARCH_IN_POST`) for the trade-role OR list. Mention JSON summary fields **`expand_see_more`**, **`body_keyword_union`**, **`body_keyword_source`**, **`body_keyword_needles_count`**, **`in_post_keywords`** when relevant.
- **PLANNER**: write a numbered action plan with clear stop conditions.
- **BROWSER**: execute Playwright browser primitives in order, collecting screenshots/snapshots as evidence.
- **CRITIC**: validate each extraction batch for duplicates, wrong group, stale publication date, and whether truncated posts expanded before scrape.
- **WRITER**: convert validated browser results into DB-compatible post payloads and artifacts.
- **TESTER**: verify result shape, DB upserts, report paths, and operator-facing output.

Required sequence:

1. ROUTER chooses one pipeline from `agentic_facebook/PIPELINES.md`.
2. ANALYST confirms `ENABLE_AGENTIC_FACEBOOK_SYNC`, **`scripts/run_agentic/run_agentic_facebook_exact_posts.py`** vs base scripts, `BROWSER_SEARCH_QUERY` / `--query`, `BROWSER_IN_GROUP_SEARCH_QUERY` / `--in-group-query`, **`BROWSER_IN_GROUP_SEARCH_IN_POST`** / `--in-post-keywords`, mandatory **`--global-message-contains`**, limits and seeds.
3. PLANNER writes steps and stop conditions before BROWSER starts.
4. BROWSER performs one deliberate action at a time and records evidence.
5. CRITIC checks each group extraction before WRITER upserts or reports it.
6. WRITER returns a compact JSON summary with `ok`, `flow`, `query`, `groups_scanned`, `found_posts`, `upserted`, `errors`, `artifacts_dir`, `html_report_dir`, and when applicable `expand_see_more`, `body_keyword_union`, `body_keyword_source`, `body_keyword_needles_count`, `in_post_keywords`, `in_group_exact_keywords`.
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

- **Exact-posts agentic run** (see-more expansion + AND/OR body filter; year filter on URLs when `BROWSER_POST_PUBLICATION_YEAR` is set):

  ```bash
  ENABLE_AGENTIC_FACEBOOK_SYNC=true \
  MONITOR_KEYWORDS='ищу работув Германии' \
  BROWSER_IN_GROUP_SEARCH_IN_POST='Каменщик,Бетонщик,Арматурщик,Монтажник металлоконструкций,Кровельщик,Плотник,Столяр,Штукатур,Маляр,Плиточник облицовщик,Гипсокартонщик,Фасадчик,Изолировщик' \
  .venv/bin/python scripts/run_agentic/run_agentic_facebook_exact_posts.py \
    --query "ищу работу в Германии" \
    --in-group-exact-keywords \
    --in-group-query "ищу работу" \
    --global-message-contains "ищу работу" \
    --group-limit 50 \
    --post-limit 100
  ```

  Equivalent without the env var (CLI takes precedence over env):

  ```bash
  .venv/bin/python scripts/run_agentic/run_agentic_facebook_exact_posts.py \
    --query "ищу работу в Германии" \
    --in-group-query "ищу работу" \
    --global-message-contains "ищу работу" \
    --in-post-keywords "Каменщик,Бетонщик,Арматурщик,Монтажник металлоконструкций,Кровельщик,Плотник,Столяр,Штукатур,Маляр,Плиточник облицовщик,Гипсокартонщик,Фасадчик,Изолировщик" \
    --group-limit 50 --post-limit 100
  ```

- For **year `filters=`** on in-group URLs only (no see-more/AND-OR body filter in that executable), use **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`** (see skill **`fc-search-once-exact`**).
- Anthropic (challenge vision): **`scripts/run_agentic/run_agentic_facebook_once_anthropic.py`** mirrors the base once script; there is no separate Anthropic duplicate of **`run_agentic_facebook_exact_posts.py`** unless added later.
- Daily report evidence: `scripts/run_daily_report_once.py` (see `ANTHROPIC_README.md`).

## Defaults (no task text)

If the user did not supply a task above, default to: explain **`scripts/run_agentic/run_agentic_facebook_exact_posts.py`** (Ещё expansion + AND `--global-message-contains` + OR `BROWSER_IN_GROUP_SEARCH_IN_POST` / `--in-post-keywords`), contrast with **`scripts/run_agentic/run_agentic_facebook_once.py`** and **`scripts/run_agentic/run_agentic_facebook_once_exact_year.py`**, and give one bash example for **`scripts/run_agentic/run_agentic_facebook_exact_posts.py`** that sets both stages.
