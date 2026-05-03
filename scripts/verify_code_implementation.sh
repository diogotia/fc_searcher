#!/usr/bin/env bash
# Phase 2 — automated implementation checks (no Facebook login).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "${ROOT}/.venv/bin/python" -m pytest tests/test_code_verification_phase2.py -q "$@"
