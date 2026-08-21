#!/usr/bin/env bash
# 重新生成 AU + HKJC 嘅模型說明。跑完會覆蓋呢個資料夾入面嘅 .md / .html。
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON_BIN:-python3}"
GEN=".agents/skills/shared_racing/scripts/explain_model.py"
STATUS=0
for platform in au hkjc; do
  echo "── $platform ─────────────────────────────"
  "$PY" "$GEN" --platform "$platform" || STATUS=1
done
exit "$STATUS"
