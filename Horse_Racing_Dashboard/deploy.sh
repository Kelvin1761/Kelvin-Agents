#!/bin/bash
set -euo pipefail

# ==========================================
# 🚀 旺財 Dashboard 自動發佈腳本 (Cloudflare Pages)
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ⚠️ 成個 deploy bundle（dist + wrangler.toml + functions/）一定要住喺本地
# /tmp，wrangler 亦要喺本地 CWD 行。個 repo 喺 Google Drive 上面：Drive 同步
# 高峰時，喺 Drive 路徑讀寫會 hang 到 40 分鐘以上；搬晒去本地係 5 秒內完成
# （2026-07-08 實測）。Codex / Claude / 人手行都一樣受惠。
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/wongchoi_deploy.XXXXXX")"
DIST_DIR="$STAGING_DIR/dist"
HTML_OUT="$DIST_DIR/index.html"
JSON_OUT="$DIST_DIR/dashboard-data.json"
MANIFEST_OUT="$DIST_DIR/deploy-manifest.json"
BUILD_ONLY=0
KEEP_DIST=0
PAGES_PROJECT="${WC_CLOUDFLARE_PAGES_PROJECT:-wongchoi-dashboard}"

cleanup_staging() {
    if [ "$KEEP_DIST" -eq 0 ]; then
        rm -rf "$STAGING_DIR"
    else
        echo "🗂  已保留 deploy bundle：$STAGING_DIR"
    fi
}
trap cleanup_staging EXIT

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

echo "📦 第二步：Cloudflare deploy bundle 已準備完成（本地 staging：$STAGING_DIR）"
echo "   - HTML: $(basename "$HTML_OUT")"
echo "   - Data: $(basename "$JSON_OUT")"
echo "   - Manifest: $(basename "$MANIFEST_OUT")"
# wrangler 要喺 CWD 搵到 wrangler.toml（KV binding WC_STATE）同 functions/
# （/api/sync bet-sync Function）——照樣搬入本地 staging，唔留喺 Drive。
cp "$SCRIPT_DIR/wrangler.toml" "$STAGING_DIR/wrangler.toml"
if [ -d "$SCRIPT_DIR/functions" ]; then
    cp -R "$SCRIPT_DIR/functions" "$STAGING_DIR/functions"
    echo "   - Pages Functions: functions/（已複製到本地 staging）"
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
SNAPSHOT_TAG="$(date -u +%Y%m%d%H%M%S)"
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    COMMIT_MESSAGE="$(git -C "$REPO_ROOT" log -1 --pretty=%s 2>/dev/null || printf 'manual dashboard deploy')"
fi
COMMIT_HASH="manual-${SNAPSHOT_TAG}"
COMMIT_MESSAGE="${COMMIT_MESSAGE} [snapshot ${SNAPSHOT_TAG}]"

echo "   - Wrangler CWD: $STAGING_DIR (本地 staging，內有 wrangler.toml KV + functions/)"
echo "   - Commit Hash: $COMMIT_HASH"

# MUST run from a CWD that contains wrangler.toml (KV binding WC_STATE) and
# functions/ — REQUIRED for the /api/sync bet-sync Function; missing them
# silently drops Functions + KV → 匯入投注記錄 fails with "寫入 ROI 資料庫失敗".
# 我哋已將兩者複製到本地 $STAGING_DIR，喺嗰度行——千祈唔好改返去 Drive 上面嘅
# $SCRIPT_DIR 行（Drive 同步時 wrangler 會 hang 40 分鐘以上）。
# CF_PAGES_BRANCH=main + --branch main force a production deploy so
# wongchoi-dashboard.pages.dev updates.
(
    cd "$STAGING_DIR"
    env CI=1 CF_PAGES_BRANCH=main CLOUDFLARE_ACCOUNT_ID="$RESOLVED_ACCOUNT_ID" npx wrangler pages deploy "$DIST_DIR" \
        --project-name "$PAGES_PROJECT" \
        --branch main \
        --commit-hash "$COMMIT_HASH" \
        --commit-message "$COMMIT_MESSAGE" \
        --commit-dirty="$COMMIT_DIRTY"
)

echo "🎉 發佈完成！Cloudflare 版本已更新 HKJC + AU race analysis snapshot。"
