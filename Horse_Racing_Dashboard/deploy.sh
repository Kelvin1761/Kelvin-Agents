#!/bin/bash
set -euo pipefail

# ==========================================
# 🚀 旺財 Dashboard 自動發佈腳本 (Cloudflare Pages)
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/.cloudflare_dist"
HTML_OUT="$DIST_DIR/index.html"
JSON_OUT="$DIST_DIR/dashboard-data.json"
MANIFEST_OUT="$DIST_DIR/deploy-manifest.json"
BUILD_ONLY=0
KEEP_DIST=0
PAGES_PROJECT="${WC_CLOUDFLARE_PAGES_PROJECT:-wongchoi-dashboard}"

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
if [ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
    echo "   - Account ID: ${CLOUDFLARE_ACCOUNT_ID}"
else
    echo "   ⚠️ 未設 CLOUDFLARE_ACCOUNT_ID；如使用 token auth，建議明確設置"
fi

if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
    echo "   - Auth: CLOUDFLARE_API_TOKEN"
else
    echo "   ℹ️ 未設 CLOUDFLARE_API_TOKEN；將依賴本機 wrangler login session"
fi

# Deploy to the PRODUCTION branch (main). Run from SCRIPT_DIR so wrangler finds
# wrangler.toml (KV binding WC_STATE) and functions/ — REQUIRED for the /api/sync
# bet-sync Function. CF_PAGES_BRANCH=main + --branch main force a production deploy
# even though the local git branch differs (otherwise it becomes a preview deploy
# and wongchoi-dashboard.pages.dev would not update).
( cd "$SCRIPT_DIR" && env CI=1 CF_PAGES_BRANCH=main \
    npx wrangler pages deploy "$DIST_DIR" \
        --project-name "$PAGES_PROJECT" \
        --branch main \
        --commit-dirty=true )

if [ "$KEEP_DIST" -eq 0 ]; then
    rm -rf "$DIST_DIR"
fi

echo "🎉 發佈完成！Cloudflare 版本已更新 HKJC + AU race analysis snapshot。"
