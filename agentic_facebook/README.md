# Agentic Facebook Flow

This directory is a separate usage kit for the opt-in agentic Facebook flow. It does not replace the existing `facebook_browser_search_sync` MCP tool, `/admin/browser-search-sync`, or `scripts/run_browser_search_once.py`.

## Enable

Set these in `.env`:

```bash
ENABLE_AGENTIC_FACEBOOK_SYNC=true
AGENTIC_FACEBOOK_OUTPUT_DIR=output/agentic_facebook
AGENTIC_FACEBOOK_SOURCE=playwright_agentic
ENABLE_BROWSER_SEARCH_SYNC=false
```

`ENABLE_BROWSER_SEARCH_SYNC` can stay false when you only want the agentic flow. Shared search inputs still use the existing browser variables:

```bash
BROWSER_SEARCH_QUERY=ищу работу
BROWSER_IN_GROUP_SEARCH_QUERY=малярные работы,монтаж гипсокартона
BROWSER_GROUP_SCAN_LIMIT=20
BROWSER_POST_LIMIT_PER_GROUP=25
BROWSER_SEED_GROUP_URLS=https://www.facebook.com/groups/934750153812574
```

Seed groups are always processed first, then discovered groups are added up to `BROWSER_GROUP_SCAN_LIMIT`.

## Run

CLI:

```bash
.venv/bin/python scripts/run_agentic_facebook_once.py \
  --query "ищу работу" \
  --in-group-query "малярные работы" \
  --group-limit 5 \
  --post-limit 25 \
  --global-message-contains "ищу работу"
```

Admin API:

```bash
curl -s -X POST http://localhost:5000/admin/agentic-facebook-sync \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"ищу работу","in_group_query":"малярные работы","group_limit":5,"post_limit_per_group":25}' | jq .
```

MCP tool:

```text
facebook_agentic_browser_sync(query="ищу работу", in_group_query="малярные работы", group_limit=5)
```

Artifacts are written under `output/agentic_facebook/<timestamp>`, and HTML summaries are written under `report/agentic_search_<timestamp>/`.

## Files

- `MASTER_ORCHESTRATOR_PROMPT.md`: copyable master prompt for Cursor or Claude.
- `PIPELINES.md`: prebuilt flow references for sync, search, report, and debug.
- `PLAYWRIGHT_ACTION_PLAN.md`: browser primitive sequence and checkpoint rules.
