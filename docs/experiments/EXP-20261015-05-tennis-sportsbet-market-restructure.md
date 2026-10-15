# EXP-20261015-05 — Tennis：Sportsbet 2026-08-23 盤口重組（非 ace 家族）事故記錄 + 修正

- **日期**：2026-10-15
- **類型**：事故／數據管線正確性修正（唔係模型改動；冇改任何定價公式、權重或落注閘）
- **平台**：Tennis（tennis-wong-choi，player props）
- **Base**：origin/main `ca2c4bd6` + cherry-pick `d943ff62`（A–F，含 ace ladder 改名同 `family_health.py`）
- **Live DB**：`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`，全部唯讀（`mode=ro`）
- **相關**：EXP-20261015-01 finding E（ace 改名，d943ff62 已修）；memory「「無輸出」唔會報錯」、「Scrapers fail silently in one shape」

## 症狀

prop_tracker rows/day，08-22 前 → 後（caller 量）：player_game_handicap 48.0→1.3、
player_total_games 15.3→0.2、match_total_games 26.3→6.1、player_set_handicap 4.3→0.1、
player_first_set_match 10.2→0.2、player_first_set_game_handicap 3.0→0.1。
所有 run 報成功、test 全綠。

逐週 rows/day（prop_tracker，唯讀）：

| family | 08-10 | 08-17 | 08-24 | 08-31 | 09-21 | 10-05 | 10-12 |
|---|---|---|---|---|---|---|---|
| player_game_handicap | 48.0 | 40.0 | 2.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| player_total_games | 19.7 | 15.3 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 |
| match_total_games | 30.7 | 35.4 | 1.1 | 1.3 | 7.4 | 23.3 | 17.5 |
| player_set_handicap | 5.3 | 5.3 | 0.1 | 0 | 0 | 0 | 0 |
| player_first_set_match | 23.3 | 23.4 | 0.6 | 0 | 0 | 0 | 0 |
| player_first_set_game_handicap | 7.0 | 6.6 | 0.6 | 0 | 0 | 0 | 0 |

## 根因（三個，同日發生，各自靜默）

### 1. 頁面只 server-render「Top Markets」tab（抽取層，最大）

`market_odds_snapshots` 嘅 `raw_api_responses` 存咗 event 物件，入面有
`numMarkets`（頁面宣稱有幾多盤）同 `marketIds`（preloaded state 真係帶住嘅）。
page-has vs parsed（每 event 平均，按週）：

| 週 | numMarkets | 抽到 | 比率 |
|---|---|---|---|
| 08-10 | 21.0 | 12.9 | 62% |
| 08-17 | 12.8 | 9.3 | 73% |
| 08-24 | 10.8 | 3.1 | **29%** |
| 08-31 | 17.6 | 4.7 | 27% |
| 09-14 | 7.7 | 2.9 | 38% |
| 10-05 | 13.0 | 6.1 | 47% |

我哋「解析」嗰部分 100% 正確（marketIds = parsed），所以冇任何 parse drop 計數會響；
漏嘅係頁面根本冇 render 嘅 tab。2026-10-15 live 唯讀探測：WTA 1000 Wuhan 一場
`numMarkets` 52、頁面 4 個（Match Betting、Set 1/2/3 Winner）。其餘全部喺
`marketGroupings[*].httpLink`（`/apigw/sportsbook-sports/Sportsbook/Sports/Events/<id>/MarketGroupings/<gid>/Markets`），
包括 Game Handicap、Alternative Game Handicap、Set Handicap、Set 1 Game Handicap、
Match Total Games、`<Player> Total Games`、Total Aces、`<Player> Aces`、Set Betting。

### 2. 讓分 selection 冇咗括號

`Alexandra Eala (-0.5)` → `Alex de Minaur -3.5`。`_spread_odds` 只剝 `(…)`，
數字留喺名度，配唔到 player_a/b，整個 family 0 行。Game Handicap / Set Handicap /
Set 1 Game Handicap 三個 family 同一個原因。

### 3. 球員總局數個名冇咗 line

`Adam Walton Total Games 13.5` → `Alex de Minaur Total Games`（line 只喺 selection
`Over 12.5`）。`registry.family_for_market` 要求名後面有數字 → 跌入
`match_total_games`；`daily.py` 嘅 match totals 分支只排除 "set "，所以**佢哋被當成
全場總局數、喺 ~12.5 嘅 line 定價**。08-23..10-15：125 行（line < 16），119 行已結算，
stake 全部 0（match games 唔落注），但已經喺 match_total_games 嘅 scorecard /
`family_reliability` 入面。live DB 唯讀，冇改；建議另外決定要唔要剔走。

### 其他

- `To win/lose 1st set and win match` **Sportsbet 已撤**：08-23 後 0 行；2026-10-15
  三場單打所有 tab 都冇。冇替代（`Match & Both win a Set` 係另一個盤）。
- `Total Sets 2.5` O/U → `Total Sets` 「2 Sets / 3 Sets」—— 冇對應 family，唔處理。
- `to win at least one set` → `To Win At Least 1 Set`：registry 本身已兼容。
- `Total Match Games 22.5`（key `total_match_games_22_5`）→ `Match Total Games`
  （key `total_games`）：registry 已兼容；09-21 起 match_total_games 回升就係呢個。

## 舊 → 新對照

| Family | 08-22 前 feed（key / name / selection） | 08-23 後 | 結構 | 修正 |
|---|---|---|---|---|
| player_game_handicap | `game_handicap` / `Game Handicap 3.5`、`Alternative Game Handicap 1 -0.5` / `Name (-3.5)` | `game_handicap` / `Game Handicap`、`Alternative Game Handicap` / `Name -3.5`（Alternative 每條線兩個方向都有） | 兩路，line 由名搬去 selection | 去括號解析 + 每 \|line\| 揀一對（主盤優先，再揀最平衡）+ 抓 tab |
| player_set_handicap | `set_handicap` / `Set Handicap 1.5`、`Alternative Set Handicap -1.5` / `Name (-1.5)` | `set_handicap` / `Set Handicap` / `Name -1.5` | 兩路 | 同上 |
| player_first_set_game_handicap | `game_handicap` / `Set 1 Game Handicap 1.5` / `Name (-1.5)` | `game_handicap` / `Set 1 Game Handicap` / `Name -1.5` | 兩路 | 同上 |
| player_total_games | `total_games` / `<P> Total Games 12.5` / Over/Under | `total_games` / `<P> Total Games` / Over/Under 12.5 | 兩路 | registry 接受冇數字結尾 + 抓 tab |
| match_total_games | `total_match_games_22_5` / `Total Match Games 22.5`；`total_games` / `Alternative Total Games 22 5` | `total_games` / `Match Total Games`、`Alternative Total Games` | 兩路 | 已認得；volume 靠抓 tab；剔走誤入嘅 player totals |
| player_first_set_match | `to_win_1st_set_and_win_match` / `to_lose_1st_set_and_win_match` | **撤咗** | — | `WITHDRAWN_FAMILIES` |
| match_total_aces / player_aces | `total_aces_in_the_match`、`total_<p>_aces_N_5` | `total_aces`、`<p>_aces` N+ ladder | 單邊 ladder | d943ff62（model-only，`market_prob_fair` NULL，唔落注）；本次只係令 tab 抓得到 |

冇一個非 ace family 變成單邊 N+ ladder —— 全部仍然係兩路，用返原本嘅 proportional
去水同定價路徑。

## 修正（commit 見下）

1. `providers/sportsbet_scrape_provider.py`：`fetch_event_odds` 讀每個 tab 嘅
   `httpLink`（跳過 Top Markets、Match Betting、Set N Game Markets、Individual Point
   Markets），以 market id 去重，停牌（`statusCode != A`）唔當價。tab 失敗唔影響頁面
   盤口，記入 `market_coverage`（隨 raw response 存）。`TENNIS_SPORTSBET_MARKET_GROUPS=0` 可關。
2. `props/daily.py::_spread_odds`：有括號（舊）行為不變；冇括號（新）按 (盤名, A 讓分)
   配對，每個 |line| 一個 prop，主盤先、最平衡次之 —— 唔再係「最後讀到嗰行贏」。
3. `props/registry.py`：`<Player> Total Games` 冇數字結尾都係 player_total_games。
4. `props/family_health.py`：加 `prop_family_absent`（有歷史、28 日窗內 0 行 ——
   silent 檢查喺 family 死咗超過 baseline 之後會自己收聲）、`WITHDRAWN_FAMILIES`、
   `market_group_coverage`（儲存/宣稱 < 60% 或大部分 event 有 tab 失敗）。run-daily 兩樣都出。
   2026-10-14 對 live DB 跑：即刻報 player_game_handicap（silent）、player_total_games、
   player_set_handicap、player_first_set_game_handicap、player_aces、match_total_aces（absent）。

## 量度（唯讀）

### 重新定價 live DB 已存 snapshot（`earliest_odds=True`，`log=False`；priced props，唔係 rows）

| 日期 | game_hcp 前→後 | player_total_games | match_total_games | set_hcp | 1st-set game hcp |
|---|---|---|---|---|---|
| 08-15（改名前） | 6 → 6 | 8 → 8 | 0 → 0 | 0 → 0 | 2 → 2 |
| 09-03 | 0 → 12 | 0 → 1 | 9 → 7 | 0 → 2 | 0 → 2 |
| 10-04 | 0 → 1 | 0 → 0 | 1 → 1 | 0 | 0 |
| 10-10 | 0 → 13 | 0 → 20 | 33 → 13 | 0 | 0 |
| 10-13 | 0 → 14 | 0 → 0 | 14 → 14 | 0 | 0 |

08-15 全部 family 完全一樣 = 舊 key 行為冇變。10-10 match_total_games 33→13：少咗嗰 20 個
就係誤當全場嘅 player totals。歷史 snapshot 只有頁面 render 到嘅盤，所以舊日子補唔到
（set handicap、first-set handicap 嘅 tab 從來冇存過）。

### 抓 tab 之後（live 唯讀探測 2026-10-15，15 場單打，冇寫 DB）

儲存/宣稱：29–47% → **90%**（469 宣稱、頁面 138、tab 加 282、0 tab 失敗）。
每場盤數（page → page+tabs）：Game Handicap 類 9→19、Set Handicap 0→11、
Set 1 Game Handicap 0→11、Player Total Games 4→6、match/set total games 9→100、
Player Aces 4→14、Set Betting 9→14。按 ~50 場單打／日推算，rows/day 應回到 08-22 前
水平或以上；**呢個係推算，要等新 snapshot 先量到真數** —— 下一次 run-daily 嘅
`sportsbet_market_coverage` 同 `prop_family_absent` 就係驗收。

## 仲落唔到注 / 未解決

- **player_first_set_match**：Sportsbet 撤盤，冇嘢可以定價。
- **ace N+ ladder**（match / player）：model-only，`market_prob_fair` NULL，等有驗證過嘅
  單邊 ladder 去水方法（d943ff62）。
- **match_total_games**：`_games_bettable()` 本身就關（11 注 36.4%），冇變。
- **Best-of-5**：成個 prop 層寫死 `best_of=3`；Slam 男單嘅 Set Handicap ±2.5 用 BO3
  分佈定價係退化（cover = 0/1 夾到 0.01/0.99）。改名前已存在（17 行 player_set_handicap_2.5），
  抓 tab 之後 Slam 期間會多咗；應另開題處理。
- **match_total_games 嘅 119 行污染**：已結算、未清，見根因 3。
- 恢復嘅 family 會返到 08-22 前一樣經 per-family 證據閘決定可唔可以落注 —— 冇放寬任何閘。
- 新抓法每場多 ~6 個 GET（enrich 每 run ~50 場、preclose 每 30 分鐘近開賽場次）。

## 可重現

```bash
# 舊 key 行為不變 + 新格式：temp DB
cd tennis-wong-choi && PYTHONPATH=src python3 -m pytest -q tests/test_market_rename_families.py tests/test_ace_ladder_rename.py
# family health（唯讀）
python3 -c "import sqlite3,sys; sys.path.insert(0,'src'); from tennis_wc.props.family_health import silent_prop_families as s; c=sqlite3.connect('file:tennis_wc.db?mode=ro',uri=True); c.row_factory=sqlite3.Row; print(s(c,'2026-10-14'))"
```
