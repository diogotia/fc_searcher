# fc_searcher — `/fc.search_once` user guide

## Cursor commands

| Command | File | Purpose |
|---------|------|---------|
| **`/fc.search_once`** | `.cursor/commands/fc.search_once.md` | Default orchestrator; in-group phrases are **`discovery_query + token`** from `.env` / `--in-group-query`. |
| **`/fc.search_once.exact`** | `.cursor/commands/fc.search_once.exact.md` | Same orchestrator, but in-group search uses **exact keywords only** (see below). |

| Item | Detail |
|------|--------|
| **Invoke** | Type **`/`** in Chat/Agent → pick the command |
| **Your task** | Text after the command fills **`$ARGUMENTS`** (the **Task** section). |
| **Fallback** | If you send no task, each command file defines a default. |

If a command does not appear, rename the `.md` file to use hyphens only (e.g. **`fc-search-once-exact.md`**) and invoke the matching name.

### Exact in-group keywords (`--in-group-exact-keywords`)

Facebook **`/search/groups`** still uses the **first** segment of `BROWSER_SEARCH_QUERY` (or `--query`).  
Each in-group phase uses **only** the comma-separated tokens — e.g. **`Бетонщик`**, **`Арматурщик`** — **without** prefixing `ищу работу в Германии`.

```bash
.venv/bin/python scripts/run_agentic_facebook_once.py \
  --query "ищу работу в Германии" \
  --in-group-exact-keywords \
  --in-group-query "Бетонщик,Арматурщик" \
  --group-limit 50
```

**Admin JSON:** `POST /admin/agentic-facebook-sync` with `"in_group_exact_keywords": true`.  
**MCP:** `facebook_agentic_browser_sync(..., in_group_exact_keywords=True)`.

### Facebook UI year filter on in-group search (all seed + discovered groups)

To match the Facebook web “creation time / year” filter on **every** group search URL (same as manually adding a 2026 filter in the UI), set **`BROWSER_POST_PUBLICATION_YEAR=2026`** (or `auto`) and run:

```bash
.venv/bin/python scripts/run_agentic_facebook_once_exact_year.py
```

This appends a built-in **`filters=`** token derived from that year. It does **not** remove server-side post filtering from `.env`; both can apply. The script fails fast if **`BROWSER_POST_PUBLICATION_YEAR`** is unset.

Do not put commas **inside** a single keyword (splitting is comma-based).

## What it does

Loads the **Agentic Facebook Orchestrator**: ROUTER → ANALYST → PLANNER → BROWSER → CRITIC → WRITER → TESTER, using only the **agentic** path (not classic `run_browser_search_once.py`). See `agentic_facebook/PIPELINES.md`.

## Terminal equivalents

| Script | Notes |
|--------|--------|
| `scripts/run_agentic_facebook_once.py` | Strips `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` after loading `.env`. |
| `scripts/run_agentic_facebook_once_anthropic.py` | Same sync; keeps Anthropic for optional Meta challenge vision. |

From repo root:

```bash
.venv/bin/python scripts/run_agentic_facebook_once.py --help
```

## Env the ANALYST checks

`ENABLE_AGENTIC_FACEBOOK_SYNC`, `BROWSER_SEARCH_QUERY`, `BROWSER_IN_GROUP_SEARCH_QUERY`, `BROWSER_GROUP_SCAN_LIMIT`, `BROWSER_POST_LIMIT_PER_GROUP`, `BROWSER_SEED_GROUP_URLS` (seeds are scanned **before** discovery; `group_limit` caps **extra** discovery groups only).

## Multi-trade keyword search

- **`--query "ищу работу в Германии"`** — sets discovery + phrase prefix (first token logic still applies; single phrase here).
- **`--in-group-query "A,B,C"`** — comma-separated tokens; each becomes `<query> <token>` for in-group search. **Do not put commas inside one token** (e.g. use `Монтажник ЖБИ металлоконструкций` instead of commas inside parentheses).
- **`--global-message-contains`** — **one** substring only (`post_matches_global_message_filter`). For “any of many trades”, use multiple **`--in-group-query`** tokens instead of one global filter.

## After the run

JSON includes **`artifacts_dir`**, **`html_report_dir`**. Email agentic HTML:

```bash
.venv/bin/python scripts/send_browser_search_report_email.py --dir /absolute/path/to/report/agentic_search_<stamp>
```

Daily CSV/HTML: `scripts/run_daily_report_once.py`. Anthropic: `ANTHROPIC_README.md`.

## Example: 50 discovery groups + trades (CLI)

```bash
.venv/bin/python scripts/run_agentic_facebook_once.py \
  --query "ищу работу в Германии" \
  --group-limit 50 \
  --post-limit 100 \
  --in-group-query 'Каменщик,Бетонщик,Арматурщик,Монтажник ЖБИ металлоконструкций,Кровельщик,Плотник,Столяр,Штукатур,Маляр,Плиточник (облицовщик),Гипсокартонщик,Фасадчик,Изолировщик'
```

**Duration:** many groups × many phrases ⇒ long Playwright run; login/2FA may be required.

---

## Related

- `agentic_facebook/MASTER_ORCHESTRATOR_PROMPT.md` — copy-paste template  
- `ANTHROPIC_README.md` — Claude / `ANTHROPIC_API_KEY`  
- Main `README.md` — project setup  
