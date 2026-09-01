#!/usr/bin/env bash
# 安全保存入口：exact-scope check → commit → push → release manifest → Telegram。
#
#   ./保存.sh --path docs/plan.md "docs: update plan"
#   ./保存.sh --path src/a.py --path tests/test_a.py "fix: correct A"
#   ./保存.sh --path src/a.py --dry-run "fix: preview A"
#
# 呢個 wrapper 刻意冇「自動掃晒所有 dirty files」。同一時間可能有多個 agent
# worktree；只有 caller 知道邊啲檔案屬於今次工作。Central release manager 會按
# exact scope 分類風險、跑 gate、commit、push、寫 immutable manifest 同通知 Telegram。
set -uo pipefail
cd "$(dirname "$0")"

PY="${PYTHON_BIN:-python3}"
CENTRAL=".agents/skills/central_wong_choi/scripts/central_wong_choi.py"
MESSAGE=""
DRY_RUN=0
ALLOW_UNRELATED=0
NO_NOTIFY=0
ACTIVATION_BASE=""
PATHS=()

usage() {
  cat <<'EOF'
用法：
  ./保存.sh --path <今次改嘅檔案或目錄> [--path ...] "commit message"

選項：
  --path PATH          只保存呢個 scope；可以重覆
  --dry-run            只顯示 risk／gate／activation plan，唔改 git
  --allow-unrelated    容許 worktree 有其他未 stage 改動，但永遠唔會收埋佢哋
  --activation-base SHA  用已部署 SHA 計算真正 activation delta
  --no-notify          唔發 Telegram（一般唔建議）

code/model/automation/deployment 只會 commit + push；Telegram /approve SHA 後先會
重新驗證、merge 同 activate。docs/tests-only 通過 policy gate 後可以自動 merge。
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --path)
      [ "$#" -ge 2 ] || { echo "❌ --path 後面要有路徑"; exit 2; }
      PATHS+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --allow-unrelated)
      ALLOW_UNRELATED=1
      shift
      ;;
    --activation-base)
      [ "$#" -ge 2 ] || { echo "❌ --activation-base 後面要有 SHA"; exit 2; }
      ACTIVATION_BASE="$2"
      shift 2
      ;;
    --no-notify)
      NO_NOTIFY=1
      shift
      ;;
    --no-check)
      echo "❌ Central release 唔接受跳過 gate；修好紅燈再保存。"
      exit 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "❌ 未知選項：$1"
      usage
      exit 2
      ;;
    *)
      if [ -n "$MESSAGE" ]; then
        echo "❌ commit message 請用一個 quoted argument。"
        exit 2
      fi
      MESSAGE="$1"
      shift
      ;;
  esac
done

if [ "${#PATHS[@]}" -eq 0 ]; then
  echo "❌ 冇指定今次改動 scope；為免收埋其他 agent 嘅工作，唔會 git add -A。"
  echo
  git status --short | head -40
  echo
  usage
  exit 2
fi

if [ -z "$MESSAGE" ]; then
  MESSAGE="chore: 更新 ${PATHS[0]}"
fi

ARGS=(--repo "$PWD" release --message "$MESSAGE" --json)
for path in "${PATHS[@]}"; do
  ARGS+=(--path "$path")
done
[ "$DRY_RUN" -eq 1 ] && ARGS+=(--dry-run)
[ "$ALLOW_UNRELATED" -eq 1 ] && ARGS+=(--allow-unrelated)
[ "$NO_NOTIFY" -eq 1 ] && ARGS+=(--no-notify)
[ -n "$ACTIVATION_BASE" ] && ARGS+=(--activation-base "$ACTIVATION_BASE")

exec "$PY" "$CENTRAL" "${ARGS[@]}"
