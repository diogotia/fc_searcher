# Cursor agent skills (fc_searcher)

Orchestrator instructions for **Agentic Facebook** live here as reusable **skills**. Cursor commands under `.cursor/commands/` are thin wrappers: they tell the agent to read and follow the matching `SKILL.md`.

| Skill directory | Cursor command (typical) | Purpose |
|-----------------|--------------------------|---------|
| [`fc-search-once/`](fc-search-once/) | `/fc.search_once` | Default agentic pipeline (`run_agentic_facebook_once.py`). |
| [`fc-search-once-exact/`](fc-search-once-exact/) | `/fc.search_once.exact` | `--in-group-exact-keywords`; optional year URL filters (`run_agentic_facebook_once_exact_year.py`). |
| [`fc-search-once-exact-clear/`](fc-search-once-exact-clear/) | `/fc.search_once.exact.clear` | See-more expansion + body keyword union (`run_agentic_facebook_exact_posts.py`). |

Each skill’s **`SKILL.md`** is the source of truth; update skills here and keep command files short so they only reference these paths.
