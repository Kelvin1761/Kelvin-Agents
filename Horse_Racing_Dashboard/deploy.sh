#!/bin/bash

# ==========================================
# 🚀 旺財 Dashboard 自動發佈腳本 (Cloudflare Pages)
# ==========================================

echo "🔄 第一步：產生最新版本的 Dashboard 網頁..."
cd "$(dirname "$0")"

# 1. 執行 Python 腳本生成最新的 HTML
python3 generate_static.py

if [ ! -f "Open Dashboard.html" ]; then
    echo "❌ 錯誤：找不到 Open Dashboard.html, 請確認生成是否成功！"
    exit 1
fi

# 加入這段碼確保讀取到 Node 環境 (nvm)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# 2. 準備發佈專用的資料夾 (Cloudflare 建議使用標準的 index.html)
mkdir -p .cloudflare_dist
cp "Open Dashboard.html" .cloudflare_dist/index.html

# 確保 functions (API) 目錄也被複製進去
if [ -d "functions" ]; then
    cp -r functions .cloudflare_dist/
fi

echo "☁️ 第二步：推送上 Cloudflare Pages..."

# 3. 使用 Wrangler (Cloudflare 官方開發工具) 發佈
npx wrangler pages deploy .cloudflare_dist --project-name wongchoi-dashboard

# 清理暫存
rm -rf .cloudflare_dist

echo "🎉 發佈完成！你而家可以用手機打開專屬網址睇到最新數據啦！"
