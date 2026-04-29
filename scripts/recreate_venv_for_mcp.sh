#!/usr/bin/env bash
# Remove repo .venv and recreate it with Python 3.12+ so `mcp` (requires >=3.10) can install.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pick_py() {
  for c in \
    "${PYTHON312:-}" \
    "$(command -v python3.12 2>/dev/null)" \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12 \
    "$(command -v python3.11 2>/dev/null)" \
    /opt/homebrew/bin/python3.11 \
    /usr/local/bin/python3.11
  do
    [[ -z "$c" || ! -x "$c" ]] && continue
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

PY="$(pick_py || true)"
if [[ -z "$PY" ]]; then
  echo "error: need Python 3.10+ (3.12 recommended). Install e.g.:" >&2
  echo "  brew install python@3.12" >&2
  echo "Then re-run this script." >&2
  exit 1
fi

echo "Using: $PY ($("$PY" -c 'import sys; print(sys.version)'))"
if [[ "${RECREATE_VENV_FORCE:-}" != "1" ]]; then
  read -r -p "Remove $ROOT/.venv and recreate? [y/N] " ans
  if [[ ! "${ans:-}" =~ ^[yY]$ ]]; then
    echo "Aborted."
    exit 1
  fi
fi

rm -rf "$ROOT/.venv"
"$PY" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-mcp.txt"
echo "Done. Run: ./scripts/run_mcp_server.sh"
