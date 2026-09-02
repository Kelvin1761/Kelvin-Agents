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
LIVE_SNAPSHOT_URL="${WC_DASHBOARD_LIVE_SNAPSHOT_URL:-https://wongchoi-dashboard.pages.dev/dashboard-data.json}"

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

# ⚠️ 排程已經砌好一份 snapshot（剪走已歸檔場次、瘦身、驗證過），會經
# WC_DASHBOARD_BASE_SNAPSHOT 傳入。以前呢個變數**由頭到尾冇人用**，於是 deploy
# 掉咗嗰份唔要、自己由零重掃一次 —— 兩個後果：
#   1. 排程嘅剪走／體積保護只係部分生效，因為最終發佈嗰份唔係佢砌嗰份；
#   2. 全量重掃要 iterdir Google Drive 上嘅 HK_Racing，而 launchd 冇 CloudStorage
#      權限。2026-08-09 晚更就係死喺呢度：四個 08-10 場次分析齊、剪走、合併、
#      驗證全過，最後 `PermissionError: … /HK_Racing` 發佈唔到，成日賽事冇上線。
# 有得用就直接用，唔好再掃一次。
if [ -n "${WC_DASHBOARD_BASE_SNAPSHOT:-}" ] && [ -f "${WC_DASHBOARD_BASE_SNAPSHOT}" ]; then
    echo "   📦 用排程砌好嘅 snapshot：${WC_DASHBOARD_BASE_SNAPSHOT}"
    "$PYTHON_BIN" generate_static.py \
        --from-snapshot "$WC_DASHBOARD_BASE_SNAPSHOT" \
        --output-html "$HTML_OUT" \
        --output-json "$JSON_OUT" \
        --output-manifest "$MANIFEST_OUT"
elif [ "${WC_ALLOW_DASHBOARD_FULL_RESCAN:-0}" = "1" ]; then
    echo "   ⚠️ 已明確允許 full corpus rescan；只應用於首次建站／人工重建"
    "$PYTHON_BIN" generate_static.py \
        --output-html "$HTML_OUT" \
        --output-json "$JSON_OUT" \
        --output-manifest "$MANIFEST_OUT"
else
    # Code/release deploy must preserve the currently published race snapshot.
    # A bare full scan follows HOT/WARM corpus roots and can accidentally inline
    # hundreds of archived meetings.  2026-08-30 Central activation produced a
    # 226 MiB HTML file this way and correctly tripped the 25 MiB Pages gate.
    # Download + validate the live projection first; failure is safer than an
    # empty, stale or oversized replacement.
    LIVE_SNAPSHOT="$DIST_DIR/live-dashboard-data.json"
    echo "   🌐 冇指定 scheduler snapshot；保留現時 live dashboard projection"
    "$PYTHON_BIN" scripts/fetch_live_snapshot.py \
        --url "$LIVE_SNAPSHOT_URL" \
        --output "$LIVE_SNAPSHOT"
    "$PYTHON_BIN" generate_static.py \
        --from-snapshot "$LIVE_SNAPSHOT" \
        --output-html "$HTML_OUT" \
        --output-json "$JSON_OUT" \
        --output-manifest "$MANIFEST_OUT"
fi

if [ ! -f "$HTML_OUT" ]; then
    echo "❌ 錯誤：找不到 ${HTML_OUT}，請確認生成是否成功！"
    exit 1
fi

if [ ! -f "$MANIFEST_OUT" ]; then
    echo "❌ 錯誤：找不到 ${MANIFEST_OUT}，請確認 snapshot manifest 是否成功生成！"
    exit 1
fi

# ⚠️ PWA 靜態資源（manifest / app icons / service worker）。
# static_template.html 用相對路徑引用呢三樣（`manifest.webmanifest`、
# `icon-180.png`、`sw.js`），所以佢哋一定要同 index.html 一齊喺 dist 根目錄。
# 呢段係 37c8ab8c 加，之後 deploy.sh 被改寫三次就冇咗，冇人發現咗三個星期 ——
# Cloudflare Pages 對唔存在嘅路徑派 fallback index.html（200 + text/html），
# 所以三樣嘢**全部睇落 200**，只有 content-type 同 9MB 檔案大細出賣佢：
#   /sw.js → 拎到 HTML → MIME 錯 → register() reject → 個 .catch 靜靜 console.warn
#   /icon-180.png → iOS 攞唔到 icon，主畫面圖示變網頁截圖
#   /manifest.webmanifest → 冇 manifest，PWA 只靠 apple-mobile-web-app-capable meta
# 因為 fail 得無聲無息，下面個 guard 會**硬性**驗返 dist 有冇呢幾個檔。
if [ -d "$SCRIPT_DIR/pwa" ]; then
    # `pwa/.` 而唔係 `pwa/*` —— 空目錄個 glob 唔會展開，`set -e` 就會為咗一個
    # app icon 而炸掉成個 deploy。
    cp -R "$SCRIPT_DIR/pwa/." "$DIST_DIR/"
    PWA_COUNT=$(ls -1 "$SCRIPT_DIR/pwa" | wc -l | tr -d ' ')
    echo "   📱 PWA assets: pwa/ → dist 根目錄（${PWA_COUNT} 個檔案）"
else
    echo "   ⚠️ 未發現 pwa/，Dashboard 裝唔到做 iPhone app"
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

# PWA 層：index.html 引用嘅相對路徑必須真係喺 dist 度存在。呢個係硬 fail ——
# 缺咗唔會有任何 runtime 錯誤浮上水面（見上面 cp 段嘅說明），所以只可以喺呢度捉。
REQUIRED_PWA_FILES=(
    "manifest.webmanifest"   # <link rel="manifest">
    "sw.js"                  # navigator.serviceWorker.register('sw.js')
    "icon-180.png"           # <link rel="apple-touch-icon"> —— iOS 主畫面圖示
    "icon-192.png"           # manifest icon
    "icon-512.png"           # manifest icon / splash
)
for pwa_file in "${REQUIRED_PWA_FILES[@]}"; do
    if [ ! -f "$DIST_DIR/$pwa_file" ]; then
        echo "   ❌ dist 缺少 PWA 資源：$pwa_file —— iPhone 主畫面 app 會壞"
        GUARD_FAIL=1
    fi
done

# 完整分析 bundles：raw_text 由 2026-09-02 起唔再 inline（HTML 9.97 → 3.18 MiB），
# 改為 analysis/<meeting-slug>.json 喺撳開嗰陣先抓。呢個同 PWA 資源一樣係「靜靜
# 壞」嘅形狀 —— 檔案唔見咗，頁面照樣載入、排名照樣顯示，只係每張卡撳開都話
# 「載入唔到」，而 log 一個錯都冇。所以一定要喺推之前喺呢度捉。
if grep -q "data-analysis-lazy" "$HTML_OUT"; then
    ANALYSIS_COUNT=$(find "$DIST_DIR/analysis" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
    if [ "${ANALYSIS_COUNT:-0}" -eq 0 ]; then
        echo "   ❌ HTML 用緊延遲載入完整分析，但 dist 冇 analysis/*.json —— 每張卡都會話載入唔到"
        GUARD_FAIL=1
    else
        echo "   ✅ 完整分析 bundles：${ANALYSIS_COUNT} 個場次"
    fi
fi

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
    echo "🛑 發佈中止：build 唔完整，唔會推上 Cloudflare。睇返上面 ❌ 嗰行。"
    echo "   缺 PWA 資源 → pwa/ 唔齊，跑 scripts/generate_pwa_icons.py 重新生成。"
    echo "   缺 HTML 區塊 → 多數係喺過期嘅 Google Drive checkout / worktree 度 run deploy.sh。"
    echo "   正確做法：喺 off-Drive clone 度發佈 ——"
    echo "     cd ~/dev/Kelvin-Agents && git checkout main && git pull"
    echo "     WONGCHOI_DATA_ROOT=<Drive 資料路徑> ./Horse_Racing_Dashboard/deploy.sh"
    exit 1
fi
echo "   ✅ build 完整：評級矩陣 / 數據判讀 / 匯入投注記錄 / PWA 資源 齊全"

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

# ⚠️ wrangler 一定要釘版本。`npx wrangler` 冇釘就每次去 registry 攞當日最新，
# 而 2026-08-12 最新嗰個（4.122.0）依賴一個上游冇發佈嘅 miniflare@5.20260811.0-alpha，
# npm 直接 ETARGET，發佈死咗。package.json 一直寫住呢個 pin 同埋警告呢件事，
# 但 deploy.sh 冇套落去 —— 個 pin 喺文件度，唔喺執行路徑度。
# 由 package.json 讀，令兩邊唔會各自漂移。
WRANGLER_VERSION="$("$PYTHON_BIN" - <<'PYPIN'
import json, pathlib, sys
try:
    d = json.loads(pathlib.Path("package.json").read_text(encoding="utf-8"))
    v = (d.get("devDependencies") or {}).get("wrangler") or ""
    print(v.lstrip("^~"))
except Exception:
    print("")
PYPIN
)"
if [ -z "$WRANGLER_VERSION" ]; then
    echo "❌ 錯誤：package.json 讀唔到 devDependencies.wrangler —— 唔會用未釘版本嘅 wrangler 發佈"
    exit 1
fi
# ⚠️ 一定要 export —— 下面 whoami 嗰段內嵌 python 係另一個 process，
# 讀唔到未 export 嘅 shell 變數，就會變成 `wrangler@` 空版本。
export WRANGLER_VERSION
echo "   - Wrangler: 釘 ${WRANGLER_VERSION}（由 package.json 讀）"

if ! command -v npx >/dev/null 2>&1; then
    echo "❌ 錯誤：搵唔到 npx，未能執行 wrangler deploy"
    exit 1
fi

echo "☁️ 第三步：推送上 Cloudflare Pages..."
echo "   - Pages Project: $PAGES_PROJECT"
RESOLVED_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
if [ -z "$RESOLVED_ACCOUNT_ID" ]; then
    # ⚠️ 用 heredoc，唔用 -c '...'。原本係單引號包住嘅一行 python，一旦裏面要用
    # 引號（例如讀 env）就會提早結束個 shell 字串，整段靜靜咁壞掉、回空，
    # 於是 account ID 變空，wrangler 打 `/accounts//pages/...` 然後 APIError。
    RESOLVED_ACCOUNT_ID="$("$PYTHON_BIN" <<'PYACC' 2>/dev/null
import json, os, subprocess
ver = os.environ.get("WRANGLER_VERSION", "")
pkg = f"wrangler@{ver}" if ver else "wrangler"
try:
    raw = subprocess.check_output(["npx", pkg, "whoami", "--json"], text=True)
    accounts = json.loads(raw).get("accounts") or []
    if accounts:
        print(accounts[0].get("id", ""))
except Exception:
    pass
PYACC
)"
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
    env CI=1 CF_PAGES_BRANCH=main WRANGLER_VERSION="$WRANGLER_VERSION" CLOUDFLARE_ACCOUNT_ID="$RESOLVED_ACCOUNT_ID" npx "wrangler@${WRANGLER_VERSION}" pages deploy "$DIST_DIR" \
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
