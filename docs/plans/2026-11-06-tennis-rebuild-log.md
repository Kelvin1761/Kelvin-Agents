# Tennis Wong Choi 全面重建：執行紀錄（階段三）

計劃：`docs/plans/2026-11-05-tennis-strategy-and-rebuild-plan.md` 階段三。
Worktree：`/Users/imac/wt/claude-tennis-rebuild-20261106`，分支 `claude-tennis-rebuild-20261106`。

## 重播對比（兩層之一：模型／定價層）

- 凍結 DB：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-rebuild-20261105/baseline.db`
  （live DB `.backup`，2026-11-06 00:48；main = `c6e0e092`）。
- 工具：`docs/experiments/patches/tennis_rebuild/replay.py`。DB 以 `immutable=1` 開；`utc_now` 釘喺每日 00:00 UTC。
- 合約 = 每一行會寫入 `prop_tracker` 嘅值（包括寫入嗰刻凍結嘅 `pricing_evidence_json`），容差 1e-9。
  舊引擎經 `record_prop` 攔截；新引擎經 `tennis_wc.engine_api.price_props`。
- 窗口：2026-10-28 至 2026-11-05（9 日）。

## 已定嘅設計決定

| 決定 | 原因 |
|---|---|
| 只為 7 個 family 定價：球員總局數、贏一盤、首盤勝方、首盤＋全場、首盤讓局、讓局、讓盤 | Kelvin 11-05 暫停 Aces／雙誤／盤數波膽；全場總局數 `_games_bettable()` 永遠 False，從未出過 value |
| 舊 ace／雙誤 evidence profile 喺對比時剔走 | 上面嘅直接結果，唯一預期差異 |
| 剷 `earliest_odds` 路徑 | 只有研究腳本用；live 一律讀現行盤 |
| 剷所有 `model_weight is None` 分支（temper／0.35 shrink） | live 每次都傳 family 權重，呢啲分支永遠唔行 |
| 定價直接出「寫入行」，唔再經 6 種 dataclass＋6 個 `_log_*` | 合約本身就係行；中間層只係搬字 |
| 帳本 = `prop_tracker` + `featured_picks` | 計劃「一本帳」。`clv_tracker`／`combo_tracker`／`market_predictions` 唔再寫；舊行留喺 DB 做歷史 |
| 賽事勝負模型仍然行（props 要用佢嘅機率），但唔再出「match winner／market leg」紙上注 | 兩者歷史紙上注都負（-20.38u／-4.94u），而且令 dashboard 兩本帳 |

## 進度（2026-11-06 完成）

| 層 | 狀態 |
|---|---|
| model/、pricing/、store/、settle/、select/、publish/、run.py、monitor.py | 已寫；定價 9 日 978 行、結算 11,712 行重播 0 差異 |
| 排程 | 一個 `tennis_daily_schedule.py`（`--night`／`--refresh-today`／18:00），night 入口併入 |
| 剷走 | 81 個死 module、33 個研究腳本、40 個 CLI 命令、組合／CLV／match 紙上注 |
| 抓數層 | 只剷死 code、統一 as-of helper；冇原始 HTML，冇做逐行重寫（照實記低） |
| 測試 | 104 → 60 檔，551 全過；`./檢查.sh` 全綠 |
| 結果記錄 | `docs/experiments/EXP-20261106-01-tennis-rebuild.md` |
