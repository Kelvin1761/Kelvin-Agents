#!/usr/bin/env bash
# Separate dependencies keep Evidently out of production scoring interpreters.
set -euo pipefail
TASK_MONITOR_DIR="$(cd "$(dirname "$0")" && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/wongchoi-evidently-uv-cache}"
uv venv --python 3.12 "$TASK_MONITOR_DIR/.venv"
uv pip install --python "$TASK_MONITOR_DIR/.venv/bin/python" -r "$TASK_MONITOR_DIR/requirements.lock"
