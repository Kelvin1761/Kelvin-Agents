#!/usr/bin/env bash
# Thin front door: all analysis remains in the existing domain engines.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() {
  cat <<'EOF'
旺財 — 四條線，一個入口

  ./旺財.sh status                       四線狀態
  ./旺財.sh run au|hkjc <URL或場次資料夾> [原有選項]
  ./旺財.sh run nba --date YYYY-MM-DD [原有選項]
  ./旺財.sh run tennis --date YYYY-MM-DD
  ./旺財.sh review au|hkjc <場次資料夾> [原有選項]
  ./旺財.sh review nba|tennis --date YYYY-MM-DD [原有選項]

普通覆盤跳過額外歷史實驗。參數原樣傳入各線原有入口。
詳細選項：./旺財.sh run <線名> --help
備份：./備份.sh；營運檢查：./健康.sh；程式檢查：./檢查.sh
EOF
}
ACTION="${1:-help}"
case "$ACTION" in help|-h|--help) usage; exit 0;; esac
shift
DOMAIN=""
if [[ "$ACTION" != status ]]; then
  [[ $# -gt 0 ]] || { usage >&2; exit 2; }
  DOMAIN="$1"; shift
fi
case "$ACTION:$DOMAIN" in
  status:) ENTRY="$ROOT/.agents/skills/central_wong_choi/scripts/central_wong_choi.py"; set -- status "$@";;
  run:au) ENTRY="$ROOT/.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py";;
  run:hkjc) ENTRY="$ROOT/.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py";;
  run:nba) ENTRY="$ROOT/.agents/skills/nba/nba_orchestrator.py";;
  review:au) ENTRY="$ROOT/.agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py"; set -- --skip-backtest "$@";;
  review:hkjc) ENTRY="$ROOT/.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py"; set -- --skip-review "$@";;
  review:nba) ENTRY="$ROOT/.agents/skills/nba/nba_reflector/scripts/nba_reflector_orchestrator.py"; set -- --skip-ml "$@";;
  run:tennis|review:tennis) ENTRY="tennis";;
  *) usage >&2; exit 2;;
esac
# Use installed dependencies; an explicit PYTHON_BIN always takes precedence.
PY="${PYTHON_BIN:-}"
if [[ -z "$PY" ]]; then
  if [[ "$DOMAIN" == tennis && -x "$ROOT/tennis-wong-choi/.venv/bin/python" ]]; then
    PY="$ROOT/tennis-wong-choi/.venv/bin/python"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  else
    PY=python3
  fi
fi
export PYTHONDONTWRITEBYTECODE=1
if [[ "$ENTRY" == tennis ]]; then
  cd "$ROOT/tennis-wong-choi"
  export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
  if [[ "$ACTION" == run ]]; then ACTION=price; fi
  exec "$PY" -m tennis_wc.cli "$ACTION" "$@"
fi
# Keep the caller's working directory so relative meeting paths stay valid.
exec "$PY" "$ENTRY" "$@"
