#!/bin/bash
set -euo pipefail

# ==========================================
# 🚀 旺財 Dashboard 自動發佈腳本 (Cloudflare Pages)
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$SCRIPT_DIR/.cloudflare_dist"
HTML_OUT="$DIST_DIR/index.html"
JSON_OUT="$DIST_DIR/dashboard-data.json"
MANIFEST_OUT="$DIST_DIR/deploy-manifest.json"
BUILD_ONLY=0
KEEP_DIST=0
PAGES_PROJECT="${WC_CLOUDFLARE_PAGES_PROJECT:-wongchoi-dashboard}"
DEPLOY_CWD="${WC_CLOUDFLARE_DEPLOY_CWD:-${TMPDIR:-/private/tmp}}"

while [ $# -gt 0 ]; do
    case "$1" in
        --build-only)
            BUILD_ONLY=1
            ;;
        --keep-dist)
            KEEP_DIST=1
            ;;
        *)
            echo "❌ 未知參數: $1"
            echo "用法: ./deploy.sh [--build-only] [--keep-dist]"
            exit 1
            ;;
    esac
    shift
done

echo "🔄 第一步：產生最新版本嘅 Dashboard / Race Analysis Snapshot..."
cd "$SCRIPT_DIR"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "❌ 錯誤：搵唔到 python3 / python"
    exit 1
fi

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

"$PYTHON_BIN" generate_static.py \
    --output-html "$HTML_OUT" \
    --output-json "$JSON_OUT" \
    --output-manifest "$MANIFEST_OUT"

if [ ! -f "$HTML_OUT" ]; then
    echo "❌ 錯誤：找不到 $HTML_OUT，請確認生成是否成功！"
    exit 1
fi

if [ ! -f "$MANIFEST_OUT" ]; then
    echo "❌ 錯誤：找不到 $MANIFEST_OUT，請確認 snapshot manifest 是否成功生成！"
    exit 1
fi

# ==========================================
# 🛡️ 發佈前健康檢查：防止過期 checkout 把舊版 dashboard 推上線
# 背景：repo 同 .git 住喺 Google Drive，主 checkout 曾經被 stranded 喺舊 commit
# (019c595)，加上十幾個 worktree 狀態唔一，隨手喺舊 copy run deploy.sh 就會
# 令 dashboard 回退到舊版（無 評級矩陣 / 數據判讀，投注按鈕變返「匯出」）。
# 呢個 guard 會喺推送前 fail-fast，唔畀舊版靜靜雞上線。
# ==========================================
echo "🛡️ 健康檢查：驗證 build 內容 (防止舊版誤發)..."

# HTML 模板層必須帶新版區塊；缺任何一個 = 呢個 checkout 係舊版 → 中止
REQUIRED_HTML_MARKERS=(
    "評級矩陣"        # 7D 評級矩陣 renderer
    "數據判讀"        # data_readout 區塊 (commit 8ac53b8 之後先有)
    "匯入投注記錄"    # ROI 匯入按鈕（新版）；舊版係「匯出」
)
GUARD_FAIL=0
for marker in "${REQUIRED_HTML_MARKERS[@]}"; do
    if ! grep -q "$marker" "$HTML_OUT"; then
        echo "   ❌ build 缺少必要區塊：$marker"
        GUARD_FAIL=1
    fi
done

# 資料層：JSON 要真係帶到新欄位，唔淨係模板有 (報告要用新版 code 生成)
for field in "rating_matrix" "data_readout"; do
    if ! grep -q "\"$field\"" "$JSON_OUT" 2>/dev/null; then
        echo "   ⚠️ dashboard-data.json 未見 $field —— 報告可能係舊版 code 生成，請重新 re-score"
    fi
done

# 過期 checkout 提示（用本機已知嘅 origin/main ref，唔做 network fetch 以免喺 Drive 卡住）
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    BEHIND="$(git -C "$REPO_ROOT" rev-list --count HEAD..origin/main 2>/dev/null || echo 0)"
    if [ "${BEHIND:-0}" -gt 0 ]; then
        echo "   ⚠️ 呢個 checkout 落後 origin/main ${BEHIND} 個 commit —— 好可能係舊 copy，建議先 git pull"
    fi
fi

if [ "$GUARD_FAIL" -ne 0 ]; then
    echo ""
    echo "🛑 發佈中止：呢個 checkout 產生嘅係舊版 dashboard，唔會推上 Cloudflare。"
    echo "   成因：多數係喺過期嘅 Google Drive checkout / worktree 度 run deploy.sh。"
    echo "   正確做法：喺 off-Drive clone 度發佈 ——"
    echo "     cd ~/dev/Kelvin-Agents && git checkout main && git pull"
    echo "     WONGCHOI_DATA_ROOT=<Drive 資料路徑> ./Horse_Racing_Dashboard/deploy.sh"
    exit 1
fi
echo "   ✅ build 完整：評級矩陣 / 數據判讀 / 匯入投注記錄 齊全"

echo "📦 第二步：Cloudflare deploy bundle 已準備完成"
echo "   - HTML: $(basename "$HTML_OUT")"
echo "   - Data: $(basename "$JSON_OUT")"
echo "   - Manifest: $(basename "$MANIFEST_OUT")"
if [ -d "$SCRIPT_DIR/functions" ]; then
    echo "   - Pages Functions: functions/"
else
    echo "   ⚠️ 未發現 functions/，Cloudflare sync API 會缺席"
fi

if [ "$BUILD_ONLY" -eq 1 ]; then
    echo "🧪 已完成 build-only；未推送到 Cloudflare"
    echo "   輸出目錄：$DIST_DIR"
    exit 0
fi

# 加入這段碼確保讀取到 Node 環境 (nvm)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

if ! command -v npx >/dev/null 2>&1; then
    echo "❌ 錯誤：搵唔到 npx，未能執行 wrangler deploy"
    exit 1
fi

echo "☁️ 第三步：推送上 Cloudflare Pages..."
echo "   - Pages Project: $PAGES_PROJECT"
RESOLVED_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
if [ -z "$RESOLVED_ACCOUNT_ID" ]; then
    RESOLVED_ACCOUNT_ID="$("$PYTHON_BIN" -c 'import json, subprocess
try:
    raw = subprocess.check_output(["npx", "wrangler", "whoami", "--json"], text=True)
    data = json.loads(raw)
    accounts = data.get("accounts") or []
    if accounts:
        print(accounts[0].get("id", ""))
except Exception:
    pass
' 2>/dev/null)"
fi
if [ -n "$RESOLVED_ACCOUNT_ID" ]; then
    echo "   - Account ID: ${RESOLVED_ACCOUNT_ID}"
else
    echo "   ⚠️ 未能自動解析 CLOUDFLARE_ACCOUNT_ID；如 deploy 卡住，請明確設置"
fi

if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
    echo "   - Auth: CLOUDFLARE_API_TOKEN"
else
    echo "   ℹ️ 未設 CLOUDFLARE_API_TOKEN；將依賴本機 wrangler login session"
fi

COMMIT_HASH="manual"
COMMIT_MESSAGE="manual dashboard deploy"
COMMIT_DIRTY="true"
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    COMMIT_HASH="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || printf 'manual')"
    COMMIT_MESSAGE="$(git -C "$REPO_ROOT" log -1 --pretty=%s 2>/dev/null || printf 'manual dashboard deploy')"
fi

echo "   - Wrangler CWD: $SCRIPT_DIR (for wrangler.toml KV + functions/)"
echo "   - Commit Hash: $COMMIT_HASH"

# MUST run from SCRIPT_DIR so wrangler picks up wrangler.toml (KV binding
# WC_STATE) and functions/ — REQUIRED for the /api/sync bet-sync Function.
# Running from a tmp CWD silently drops Functions + KV → 匯入投注記錄 fails with
# "寫入 ROI 資料庫失敗". CF_PAGES_BRANCH=main + --branch main force a production
# deploy so wongchoi-dashboard.pages.dev updates.
(
    cd "$SCRIPT_DIR"
    env CI=1 CF_PAGES_BRANCH=main CLOUDFLARE_ACCOUNT_ID="$RESOLVED_ACCOUNT_ID" npx wrangler pages deploy "$DIST_DIR" \
        --project-name "$PAGES_PROJECT" \
        --branch main \
        --commit-hash "$COMMIT_HASH" \
        --commit-message "$COMMIT_MESSAGE" \
        --commit-dirty="$COMMIT_DIRTY"
)

if [ "$KEEP_DIST" -eq 0 ]; then
    rm -rf "$DIST_DIR"
fi

echo "🎉 發佈完成！Cloudflare 版本已更新 HKJC + AU race analysis snapshot。"
