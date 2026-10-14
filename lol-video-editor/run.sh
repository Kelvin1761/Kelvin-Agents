#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${LOL_EDITOR_PYTHON:-}" ]; then
  PY="$LOL_EDITOR_PYTHON"
elif [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
elif [ -x "$HERE/../.video_env/bin/python" ]; then
  PY="$HERE/../.video_env/bin/python"
else
  PY=python3
fi
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m lol_editor.cli "$@"
