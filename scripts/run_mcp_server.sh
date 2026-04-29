#!/usr/bin/env bash
# Start the Facebook Monitor MCP stdio server (for Cursor / other MCP clients).
# Requires Python 3.10+ (the `mcp` package does not support Apple/Xcode Python 3.9).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FC_SEARCHER_REPO_ROOT="$ROOT"
cd "$ROOT"

_py_ok() {
  [[ -x "$1" ]] && "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

_try() {
  local py="$1"
  if _py_ok "$py"; then
    exec "$py" -m src.mcp_server
  fi
}

_try "$ROOT/.venv/bin/python"
_try "$ROOT/.venv-py312/bin/python"

if command -v python3.12 >/dev/null 2>&1; then
  _try "$(command -v python3.12)"
fi
_try "/opt/homebrew/bin/python3.12"
_try "/opt/homebrew/bin/python3.11"
_try "/usr/local/bin/python3.12"
_try "/usr/local/bin/python3.11"

if command -v python3.11 >/dev/null 2>&1; then
  _try "$(command -v python3.11)"
fi

if command -v python3 >/dev/null 2>&1; then
  _try "$(command -v python3)"
fi

echo "error: no Python 3.10+ found for MCP (Apple /usr/bin/python3 is often 3.9; the mcp package needs >=3.10)." >&2
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  echo "  Note: $ROOT/.venv exists but its Python is <3.10 (common if .venv was made with Xcode python3)." >&2
  echo "  Run: ./scripts/recreate_venv_for_mcp.sh   or: rm -rf .venv && /opt/homebrew/bin/python3.12 -m venv .venv" >&2
fi
echo "  Fix: install a newer Python, then create a venv and install deps:" >&2
echo "    brew install python@3.12" >&2
echo "    /opt/homebrew/bin/python3.12 -m venv .venv" >&2
echo "    .venv/bin/python -m pip install --upgrade pip" >&2
echo "    .venv/bin/python -m pip install -r requirements-mcp.txt" >&2
echo "  Or:  curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.12 && uv venv -p 3.12 .venv" >&2
exit 1
