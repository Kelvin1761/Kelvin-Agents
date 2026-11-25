# 換機／壞機還原 Wong Choi

> 2026-11-25（Kelvin：「if i changed computer … or if it breaks down i got something to copy and paste and start running again」）。
> 一句講晒：**code 喺 GitHub，其他全部加密備份喺 Google Drive**；新機跟下面做，`./還原.sh` 會自動做大部分。

## 備份咗乜、喺邊

| 嘢 | 喺邊 | 點還原 |
|---|---|---|
| Code（成個 repo、git 歷史） | GitHub `Kelvin1761/Kelvin-Agents` | `git clone` |
| 資料 `~/WongChoiData`（賽前快照、賽果、ROI 板、控制狀態、NBA 帳） | Google Drive `WongChoiBackup/`（加密） | `offsite_backup.py restore` |
| 外置碟獨有：Betfair 記錄、舊預測快照、hkjc-history、tennis、舊 Drive 匯出 | 同上 | 同上 |
| 網球 DB（`tennis_wc.db`，含精選帳） | 同上（sqlite 一致快照） | 同上 |
| 設定同密碼：`~/.wongchoi_*`（Betfair、Telegram）、Cloudflare 登入、rclone 設定 | 同上（**加密**） | `offsite_backup.py place` |
| 排程：34 個 launchd plist（連暫停咗嗰個） | 同上 | `place`＋`launchctl bootstrap` |
| 排程狀態：`state/`、`work/*.json`、網球 runtime | 同上 | `place` |
| Claude 嘅記憶筆記 | 同上 | `place` |
| **加密鑰匙** `~/.wongchoi_offsite.key` | **唔喺 Drive**：Apple「密碼」app 嘅 `wongchoi-offsite`（經 iCloud 同步） | 還原時貼返 |

唔備份（會重砌）：`.venv`、`node_modules`、`.sportsbet_cache`、`work/progressive`、worktree、scratch 輸出。
另一份：Kelvin Hardisk 1（`./備份.sh`，屋企入面嘅第二份）。

## 每日點運作
- `central-wong-choi.offsite-backup`（launchd，每朝 04:00）：冇變嘅組重用、變咗嘅先加密上傳；保留 7 代；星期日自動做還原演練。
- `健康.sh` 會報「異地加密備份」新唔新鮮、上次演練有冇過；失敗推 Telegram。

## 新機步驟（大約 1–2 個鐘，大部分係等下載）

1. **裝基本工具**（Terminal）：
   ```bash
   xcode-select --install
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install gh rclone zstd node
   ```
2. **登入 GitHub**：`gh auth login`（揀 GitHub.com → HTTPS → 用瀏覽器登入）。
3. **授權 Google Drive**：`rclone config create gdrive drive`（會開瀏覽器，用你個 Google 帳戶登入、撳允許）。
4. **拎 code 同還原腳本**：
   ```bash
   git clone https://github.com/Kelvin1761/Kelvin-Agents.git ~/Antigravity-repo
   cd ~/Antigravity-repo && ./還原.sh --check
   ```
5. **跑還原**：`./還原.sh`。佢會叫你貼鑰匙（Apple「密碼」app → `wongchoi-offsite` → 複製）。
6. **人手做嘅兩樣**：
   - 系統設定 → 私隱與安全性 → **完整磁碟取用**：加 `/bin/zsh` 同 `/usr/bin/python3`（launchd 先讀得到外置碟）。
   - Cloudflare：`cd ~/Antigravity-repo/Horse_Racing_Dashboard && npx wrangler login`（dashboard 發佈用；備份入面嘅登入通常仍然有效，呢步係後備）。
7. **確認**：`cd ~/wongchoi-scheduler && ./健康.sh` —— 全綠或者只有已知 ⚠️ 就得。

## 第一次設定（舊機做一次）
```bash
brew install rclone
rclone config create gdrive drive                       # 瀏覽器授權
python3 .agents/scripts/offsite_backup.py init --backend rclone:gdrive:WongChoiBackup
pbcopy < ~/.wongchoi_offsite.key                         # 再貼入 Apple「密碼」app，名 wongchoi-offsite
python3 .agents/scripts/offsite_backup.py run            # 第一次全量（幾個鐘）
python3 .agents/scripts/offsite_backup.py drill --groups 3
./.agents/skills/central_wong_choi/install_offsite_backup.sh
```

## 已知要跟進：rclone 共用 client_id（2026 年內退役）
2026-11-25 設定時 rclone 提示：佢內置嘅 Google Drive client_id 會喺 2026 年內停用。停用之後上傳會失敗 ——
`健康.sh`「異地加密備份」會變 ❌、排程失敗會推 Telegram，唔會靜靜壞。修法（免費、唔使信用卡）：
Google Cloud Console 開一個 project → 啟用 Drive API → 建 OAuth client（Desktop app）→
`rclone config update gdrive client_id <id> client_secret <secret>` 再重新授權。https://rclone.org/drive/#making-your-own-client-id

## 點解唔將工作資料直接放雲端
排程每晚讀寫幾萬個細檔、回測讀成個語料；經網絡會由幾分鐘變幾個鐘，斷網或者 API 限速就停排程（2026-08 Drive 讀檔無聲卡死過）。
所以：**本機做工作、Google Drive 做異地備份、外置碟做第二份**。本機資料越舊越少用，之後可以加「舊資料上 Drive 之後清本機」。
