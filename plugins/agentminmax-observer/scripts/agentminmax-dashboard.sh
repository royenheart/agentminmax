#!/usr/bin/env bash
set -euo pipefail

ROOT="${AGENTMINMAX_ROOT:-$(pwd)}"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -e '.[dev]'
fi

.venv/bin/python -m agentminmax demo --out dashboard-dist
.venv/bin/python -m agentminmax dashboard --bundle dashboard-dist --port "${AGENTMINMAX_PORT:-8765}"
