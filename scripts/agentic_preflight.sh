#!/usr/bin/env bash
# Minimal preflight for agentic Facebook CLI runs (optional; no network to Facebook).
# From repo root:  ./scripts/agentic_preflight.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export FC_SEARCHER_REPO_ROOT="$ROOT"

echo "=== Agentic Facebook preflight (repo: $ROOT) ==="
ok=0

if [[ ! -x .venv/bin/python ]]; then
  echo "  ✗ Missing .venv/bin/python"
  exit 1
fi

.venv/bin/python - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from load_repo_env import load_dotenv_file

load_dotenv_file()
import os

v = (os.environ.get("ENABLE_AGENTIC_FACEBOOK_SYNC") or "").strip().lower()
if v not in ("1", "true", "yes"):
    print("  ✗ ENABLE_AGENTIC_FACEBOOK_SYNC not true after loading .env")
    sys.exit(1)
print("  ✓ ENABLE_AGENTIC_FACEBOOK_SYNC")
PY

for s in scripts/run_agentic_facebook_once.py scripts/run_agentic_facebook_exact_posts.py scripts/run_agentic_facebook_once_exact_year.py; do
  [[ -f "$s" ]] || { echo "  ✗ Missing $s"; ok=1; }
done
[[ "$ok" -eq 0 ]] || exit 1

if .venv/bin/python -c "import pydantic, sqlalchemy" 2>/dev/null; then
  echo "  ✓ Python deps import OK"
else
  echo "  ✗ pip install -r requirements-mcp.txt (or requirements.txt)"
  exit 1
fi

mkdir -p output/agentic_facebook report logs 2>/dev/null || true
echo "  ✓ Artifact dirs creatable"
echo "=== Ready (set DATABASE_URL, Facebook credentials; use BROWSER_POST_PUBLICATION_YEAR for exact_year). ==="
exit 0
