#!/usr/bin/env bash
# 保存今日嘅改動 —— 一條命令搞掂 commit + push。
#
#   ./保存.sh                 自動寫 commit 訊息
#   ./保存.sh "修好場地狀況"   自己寫
#   ./保存.sh --no-check      跳過檢查（唔建議）
#
# 佢會：
#   1. 先跑 ./檢查.sh --quick —— 唔過就唔准 commit（呢個先係重點）
#   2. 如果你而家企喺 main，自動幫你開一條新分支（唔會直接改 main）
#   3. commit + push
#   4. 印返個 PR 連結俾你撳
set -uo pipefail
cd "$(dirname "$0")"

RUN_CHECK=1
MESSAGE=""
for arg in "$@"; do
  case "$arg" in
    --no-check) RUN_CHECK=0 ;;
    *) MESSAGE="$arg" ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }

# ── 有嘢改咗未？ ──────────────────────────────────────────────────────────
if [ -z "$(git status --porcelain)" ]; then
  green "冇嘢改過，唔使保存。"
  exit 0
fi

bold "── 你改咗啲咩 ──"
git status --short | head -40
TOTAL=$(git status --porcelain | wc -l | tr -d ' ')
[ "$TOTAL" -gt 40 ] && echo "   …仲有 $((TOTAL - 40)) 個檔案"
echo
git diff --stat HEAD | tail -1
echo

# ── 檢查 ─────────────────────────────────────────────────────────────────
if [ "$RUN_CHECK" = "1" ]; then
  bold "── 保存之前先檢查 ──"
  if ! ./檢查.sh --quick; then
    echo
    red "檢查唔過，冇 commit。"
    echo "上面印咗係邊一項、點解、點修。修好再跑一次 ./保存.sh 就得。"
    echo "真係要照 commit（唔建議）：./保存.sh --no-check"
    exit 1
  fi
fi

# ── 唔好直接改 main ───────────────────────────────────────────────────────
BRANCH="$(git branch --show-current)"
if [ "$BRANCH" = "main" ] || [ -z "$BRANCH" ]; then
  NEW="work/$(date +%Y-%m-%d-%H%M)"
  bold "── 你企喺 main，開一條新分支：$NEW ──"
  git checkout -b "$NEW" || exit 1
  BRANCH="$NEW"
fi

# ── commit 訊息 ──────────────────────────────────────────────────────────
if [ -z "$MESSAGE" ]; then
  FILES=$(git status --porcelain | awk '{print $NF}' | head -3 | xargs -n1 basename 2>/dev/null | paste -sd, -)
  MESSAGE="chore: 更新 $FILES（$TOTAL 個檔案）"
fi

git add -A
git commit -q -m "$MESSAGE" || { red "commit 失敗"; exit 1; }
green "✅ 已 commit：$MESSAGE"

# ── push ─────────────────────────────────────────────────────────────────
bold "── 推上 GitHub ──"
if git push -u origin "$BRANCH" 2>&1 | tail -4; then
  green "✅ 已推上 $BRANCH"
  REMOTE=$(git remote get-url origin | sed 's/\.git$//' | sed 's#git@github.com:#https://github.com/#')
  echo
  echo "開 PR（撳個連結）："
  echo "  $REMOTE/compare/main...$BRANCH?expand=1"
else
  red "push 失敗。改動已經 commit 咗喺本機，唔會唔見。"
  exit 1
fi
