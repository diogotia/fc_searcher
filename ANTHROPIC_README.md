# Anthropic (`ANTHROPIC_API_KEY`) usage

This document describes how **Claude / Anthropic** credentials are loaded and where they are used in fc_searcher. It does **not** repeat full project setup; see the main [README.md](README.md) for general installation.

## Environment variables

| Variable | Purpose |
|----------|---------|
| **`ANTHROPIC_API_KEY`** | API key for Anthropic Claude (server-side only). Optional: many flows work without it. |
| **`CLAUDE_MODEL`** | Model id for API calls (default: `claude-3-5-sonnet-20241022`). |

Copy from [.env.example](.env.example) into your local `.env` (Anthropic keys live in the **Anthropic** section; optional **`ENABLE_BROWSER_META_CHALLENGE_VISION`** sits under Playwright). **Never commit `.env` or paste keys into chats or logs.**

## Configuration in code

Anthropic settings live in **`src/config_anthropic.py`**:

- **`AnthropicSettings`** — reads `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` from the process environment.
- **`get_anthropic_settings()`** — cached accessor (invalidate with **`clear_settings_caches()`** from `src.config` when env changes).

They are **not** fields on the main **`Settings`** class in `src/config.py`.

## What uses Anthropic

1. **Daily report AI summary** — `run_daily_report` in `src/services/pipeline.py` calls Claude only if **`ANTHROPIC_API_KEY`** is set (trends/summary for the email bundle). If unset, analysis is skipped with a short placeholder message.

2. **`run_analyze_recent`** — admin-style analysis of recent posts; **requires** the key or it returns an error.

3. **Optional Meta login challenge vision** — when **`ENABLE_BROWSER_META_CHALLENGE_VISION=true`** *and* **`ANTHROPIC_API_KEY`** is set, browser automation may use Claude vision for certain post-login puzzles (`src/services/facebook_challenge_vision.py`). **Off by default**; fragile and policy-sensitive.

4. **Health** — `GET /health` exposes **`anthropic_configured`**: `true` if a non-empty key is present (`src/api/routes_health.py`).

**Agentic Facebook sync** (`src/services/agentic_facebook/`) does **not** call Claude for ingestion; it only shares the browser stack with optional challenge vision if you allow Anthropic in that process (see below).

## Agentic scripts: with vs without Anthropic

| Script | Anthropic in process |
|--------|----------------------|
| **`scripts/run_agentic/run_agentic_facebook_once.py`** | **Removed** after loading `.env` (`ANTHROPIC_API_KEY` and `CLAUDE_MODEL` are popped). Use this for a clean agentic run without Claude or challenge vision. |
| **`scripts/run_agentic/run_agentic_facebook_once_anthropic.py`** | **Kept** — same sync as above, but keys stay available for **`ENABLE_BROWSER_META_CHALLENGE_VISION`** if you enable it. |

Example (from repo root, with your venv):

```bash
.venv/bin/python scripts/run_agentic/run_agentic_facebook_once.py
.venv/bin/python scripts/run_agentic/run_agentic_facebook_once_anthropic.py --group-limit 5 --post-limit 25
```

## Daily report from the CLI

```bash
.venv/bin/python scripts/run_daily_report_once.py
```

If **`ANTHROPIC_API_KEY`** is set and billing allows, Claude analysis runs; otherwise the report still builds CSV/HTML and may email without AI analysis.

## Operational notes

- **Billing / quota**: failed Claude calls surface as errors in logs; daily report may fail if analysis throws before send (fix credits or temporarily unset **`ANTHROPIC_API_KEY`** for CSV-only runs).
- **Cache**: after changing `.env`, restart long-lived processes (Flask, MCP) or rely on **`reload_settings_if_dotenv_mounted()`** / **`clear_settings_caches()`** as applicable.
