# Delivery manifest — Agentic Facebook orchestrator docs

**Location in repo:** `agentic_facebook/docs/`  
**Purpose:** Modular operator docs aligned with `run_agentic_facebook_*` scripts and `src/services/agentic_facebook/`.

## Contents

| File | Role |
|------|------|
| `INDEX.txt` | Manifest and pointers |
| `README_ORCHESTRATOR.md` | Navigation by role |
| `OPTIMIZATION_SUMMARY.md` | Rationale and metrics (from optimization pass) |
| `AGENTIC_ORCHESTRATOR_OPTIMIZED.md` | Full orchestration narrative + tables |
| `AGENTIC_DECISION_TREES.md` | Trees, checklists, cheat sheet |
| `AGENTIC_DEPLOYMENT_RUNBOOK.md` | Env names, runbooks, troubleshooting |
| `QUICK_REFERENCE_CARD.txt` | Short printable reference |

## Supporting repo files

- [`scripts/agentic_preflight.sh`](../../scripts/agentic_preflight.sh) — optional local checks (venv, flags, scripts exist).
- [`docs/FC_COMMAND.md`](../../docs/FC_COMMAND.md) — command-line reference.
- [`agentic_facebook/README.md`](../README.md) — compact enable/run entry.

## Accuracy notes (repo-specific)

- Body keyword union is **OR** across needles (not AND).
- **`AGENTIC_FACEBOOK_OUTPUT_DIR`** — not `AGENTIC_OUTPUT_DIR`.
- **`run_agentic_facebook_once_exact_year.py`** uses **`BROWSER_POST_PUBLICATION_YEAR`**; there is no `--year` CLI flag. URL **`filters=`** is an encoded UI token, not `filters=year:YYYY`.

## Maintenance

When scripts or env vars change, update `AGENTIC_DEPLOYMENT_RUNBOOK.md` §1.2 and the matrix in `AGENTIC_ORCHESTRATOR_OPTIMIZED.md`.
