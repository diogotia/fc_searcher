#!/usr/bin/env bash
set -euo pipefail

# Example: backup local SQLite used by docker bind mount
SRC="${1:-./data/facebook_monitor.db}"
DEST_DIR="${2:-./backups}"
mkdir -p "${DEST_DIR}"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
cp "${SRC}" "${DEST_DIR}/facebook_monitor_${ts}.db"
echo "Wrote ${DEST_DIR}/facebook_monitor_${ts}.db"
