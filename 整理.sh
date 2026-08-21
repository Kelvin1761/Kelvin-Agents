#!/usr/bin/env bash
# 整理散落嘅分支同工作副本。
#
#   ./整理.sh            只睇，唔郁任何嘢
#   ./整理.sh --做       真係刪
#
# 只會刪「已經完全合併入 main」嘅嘢 —— 即係佢嘅每一個 commit 都已經喺 main 入面，
# 刪咗一行 code 都唔會少。有未合併改動嘅分支一律唔會掂，會另外列出嚟。
set -uo pipefail
cd "$(dirname "$0")"

DO=0
[ "${1:-}" = "--做" ] && DO=1
[ "${1:-}" = "--do" ] && DO=1

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$1"; }

git fetch origin --quiet 2>/dev/null || true
CURRENT="$(git branch --show-current)"

# ── 1. 分支 ──────────────────────────────────────────────────────────────
SAFE=(); KEEP=()
for b in $(git for-each-ref --format='%(refname:short)' refs/heads); do
  [ "$b" = "main" ] && continue
  [ "$b" = "$CURRENT" ] && continue
  # 有 worktree 佔住就唔可以刪
  if git worktree list --porcelain | grep -q "branch refs/heads/$b$"; then
    KEEP+=("$b|有工作副本佔住"); continue
  fi
  ahead=$(git rev-list --count origin/main.."$b" 2>/dev/null || echo "?")
  if [ "$ahead" = "0" ]; then
    SAFE+=("$b")
  else
    KEEP+=("$b|仲有 $ahead 個未合併嘅 commit")
  fi
done

bold "分支（合共 $(git for-each-ref refs/heads | wc -l | tr -d ' ') 條）"
if [ "${#SAFE[@]}" -gt 0 ]; then
  green "可以安全刪走（已完全合併入 main，冇任何嘢會失去）："
  for b in "${SAFE[@]}"; do printf '   %s\n' "$b"; done
else
  echo "   冇分支可以刪。"
fi
if [ "${#KEEP[@]}" -gt 0 ]; then
  echo
  yellow "唔會掂（仲有未合併嘅嘢）："
  for entry in "${KEEP[@]}"; do printf '   %-45s %s\n' "${entry%%|*}" "${entry#*|}"; done
fi

# ── 2. 工作副本 ──────────────────────────────────────────────────────────
bold "工作副本 worktrees"
WT_SAFE=()
while read -r path _ rest; do
  [ -z "$path" ] && continue
  [ "$path" = "$(pwd)" ] && continue
  case "$path" in
    */.claude/worktrees/*) ;;
    *) printf '   %-70s（唔喺 .claude/worktrees，唔郁）\n' "$path"; continue ;;
  esac
  br=$(echo "$rest" | tr -d '[]')
  ahead=$(git rev-list --count origin/main.."$br" 2>/dev/null || echo "?")
  sz=$(du -sh "$path" 2>/dev/null | cut -f1)
  if [ "$ahead" = "0" ]; then
    WT_SAFE+=("$path")
    green "   可刪 $sz  $path  [$br]"
  else
    yellow "   保留 $sz  $path  [$br → 仲有 $ahead 個未合併 commit]"
  fi
done < <(git worktree list)

# ── 3. 做定唔做 ──────────────────────────────────────────────────────────
if [ "$DO" != "1" ]; then
  bold "而家咩都冇郁"
  echo "確認上面冇嘢想留就跑：  ./整理.sh --做"
  exit 0
fi

bold "開始整理"
for b in "${SAFE[@]:-}"; do
  [ -z "$b" ] && continue
  git branch -d "$b" >/dev/null 2>&1 && echo "   刪咗分支 $b"
done
for p in "${WT_SAFE[@]:-}"; do
  [ -z "$p" ] && continue
  git worktree remove --force "$p" >/dev/null 2>&1 && echo "   刪咗工作副本 $p"
done
git worktree prune
green "搞掂"
