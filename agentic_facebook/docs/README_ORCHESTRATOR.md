# Agentic Facebook orchestrator — navigation

Use this folder when you need **which script**, **which env vars**, or **how to debug** — not when editing application code.

**Cursor:** long-form orchestrator instructions for `/fc.search_once` commands live in the repo **`skills/`** directory ([`skills/README.md`](../../skills/README.md)); `.cursor/commands/*.md` only points the agent at those `SKILL.md` files.

## Read order by role

| Role | Start here | Then |
|------|------------|------|
| Operator / dev | [QUICK_REFERENCE_CARD.txt](QUICK_REFERENCE_CARD.txt) | [AGENTIC_DEPLOYMENT_RUNBOOK.md](AGENTIC_DEPLOYMENT_RUNBOOK.md) |
| Architect / lead | [AGENTIC_ORCHESTRATOR_OPTIMIZED.md](AGENTIC_ORCHESTRATOR_OPTIMIZED.md) | [PIPELINES.md](../PIPELINES.md) |
| On-call debug | [AGENTIC_DECISION_TREES.md](AGENTIC_DECISION_TREES.md) | Run logs + `output/agentic_facebook/` |
| PM / skim | Script matrix at top of [AGENTIC_ORCHESTRATOR_OPTIMIZED.md](AGENTIC_ORCHESTRATOR_OPTIMIZED.md) | — |

## Canonical CLI reference

- **[docs/FC_COMMAND.md](../../docs/FC_COMMAND.md)** — flags, examples, env overview.

## Scripts (repo root)

| Script | Use when |
|--------|----------|
| `scripts/run_agentic/run_agentic_facebook_exact_posts.py` | Ещё expansion + body keyword **OR** filter |
| `scripts/run_agentic/run_agentic_facebook_once.py` | Default agentic run (fastest) |
| `scripts/run_agentic/run_agentic_facebook_once_exact_year.py` | **`BROWSER_POST_PUBLICATION_YEAR`** → `filters=` on URLs |
| `scripts/run_agentic/run_agentic_facebook_once_anthropic.py` | Same as `once` but Anthropic env allowed |

Optional: `./scripts/agentic_preflight.sh` from repo root.

## Legacy prompts (unchanged)

- [MASTER_ORCHESTRATOR_PROMPT.md](../MASTER_ORCHESTRATOR_PROMPT.md)
- [PLAYWRIGHT_ACTION_PLAN.md](../PLAYWRIGHT_ACTION_PLAN.md)

## Cursor commands (local only)

Cursor command markdown under `.cursor/commands/` is **not** in git (`.cursor/` is gitignored). Operators relying on Git alone should use this `docs/` bundle.

## Full index

See [INDEX.txt](INDEX.txt).
