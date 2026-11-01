# NBA：ESPN 轉正做唯一數據來源 —— 盤點同方案

- **日期**：2026-11-01
- **狀態**：盤點完成，未改模型。決定點：2026-11-14
- **背景**：stats.nba.com 由 2026-10-29 21:00 起拒絕本機嘅程式請求。ESPN 後備已經上線（EXP-20261030-01 賽績、EXP-20261031-01 聯盟數據表、6f2643bc 閘門）。
- **Kelvin 嘅方向**：如果 ESPN 長遠較好，就**成套轉，唔好拼湊**；防守者表由佢自然退出。

## 一、結論

1. **現役模型唔需要 nba.com。** 最終機率（C 層，`nba_prob_layer.py`）只用三樣嘢：盤口類別、Sportsbet 賠率、L10 命中率。選注（steady／B2）再加 CoV 同賠率。賽績已經由 ESPN 提供，同 nba_api 逐場 94.7% 一樣，其餘係捨入級差異。
2. **nba.com 獨有、ESPN 冇嘅，只有追蹤數據**：防守者表、對位防守（DvP），同埋研究用嘅 5 張追蹤表。現役模型一張都冇用。
3. **有一個真缺口要補**：球員個人 OFF/DEF_RATING 同在場 PACE。v3 ML 有用 `def_rtg` 做特徵。ESPN box score 計唔到，但 **play-by-play 有換人紀錄**，可以還原場上陣容去計，要做 parity 驗證。
4. **ESPN 有啲 nba.com 冇（或者我哋冇用）嘅料，2019 年起格式一樣**：場上陣容、投籃座標、正選標記、DNP 原因、傷停詳情（部位同預計復出日期）、depth chart、球證。部分只有「今日」版本，**要即刻開始每日快照**，否則將來冇乾淨嘅 point-in-time 歷史。
5. **轉正嘅前提係「一把尺」**：將來 refit 要用 ESPN 重新計晒成個訓練窗口嘅特徵，唔可以前半段 nba.com、後半段 ESPN。

## 二、現役 pipeline 每個 nba.com 依賴

| nba.com endpoint | 用途 | ESPN 替代 | 狀態 |
|---|---|---|---|
| `playergamelog` | L10 賽績（C 層主輸入） | `site.web…/athletes/{id}/gamelog?season=` | ✅ 已上線，逐場 94.7% 一樣（EXP-20261030-01） |
| `leaguedashteamstats`（Advanced） | 球隊 PACE／OFF／DEF rating／DEF_RANK | 由 ESPN box score 計 | ✅ 已上線；PACE 中位差 0.65、DEF 0.85、排名 1 位（EXP-20261031-01） |
| `leaguedashplayerstats`（Advanced） | USG／TS／eFG／AST% | 由 ESPN box score 計 | ✅ 已上線；TS/eFG 一樣、USG 0.6 |
| 同上：球員 OFF/DEF_RATING、在場 PACE、PIE | ML v3 `def_rtg`；10-Factor 文字 | **PBP 還原陣容後計** | ⚠️ 而家係 `null`，見第四節 |
| `playerdashboardbygeneralsplits` | 主客／休息日 splits | 由賽績計（亦有 `athletes/{id}/splits`） | ✅ 已上線；549 人中 518 人同 nba.com 一樣 |
| `leaguedashptdefend`／`leaguedashptteamdefend` | 防守者表、對位防守 | 冇 | ⛔ 自然退出；對機率零影響（13,376 腿 0 變） |
| `leaguedashptstats`（Passing／Rebounding／Possessions／CatchShoot／PullUpShot） | `nba_opportunities` 研究證據 | 部分可由 PBP 近似（接波即射／運球後射、助攻） | ⚠️ 只係研究用，冇入機率 |
| `commonteamroster` | 陣容 | `teams/{id}/roster`（傷停已經用緊） | ✅ |
| `scoreboardv2/v3`、`leaguegamelog` | 賽程、球隊賽績（S_v2 context） | `scoreboard?dates=` | ✅ 賽程已用 ESPN；team context 可由 box score 重建 |
| `boxscoretraditionalv3` | 賽後結算 | `summary?event=` | ✅ 已上線（5393930d） |
| `playbyplayv3` | 覆盤 | `summary.plays` | ✅ ESPN 有齊 |
| 官方傷停 PDF（`ak-static.cms.nba.com`） | 傷停嚴格來源 | — | ✅ 唔同主機，**冇被封**，照用 |

## 三、ML v3 27 個特徵逐個核對

v3 而家係未驗證 shadow（`.agents/scripts/nba_ml/README.md`），但將來 refit 會用返同一套特徵：

| 特徵 | 來源 | ESPN |
|---|---|---|
| `l10_avg` `l10_sd` `l10_cov` `l10_med` `l5_avg` `l3_avg` `min_avg` `hit_rate_l10/l5/l3` `amc` | 賽績 | ✅ |
| `line_value` | Sportsbet | ✅（同 ESPN 無關） |
| `pace_projected` `opp_pace` `opp_def_rating` `opp_def_rank` | 球隊進階 | ✅ ESPN 計（有 0.98 回合縮放） |
| `usg_pct` `ts_pct` `usg_bonus_pct` | 球員進階＋傷停 | ✅ |
| `def_rtg` | 球員個人 DEF_RATING | ⚠️ 要 PBP 陣容 |
| `defender_pm` | 防守者表 | ⛔ 退出 |
| `b2b_flag` `rest_days` `b2b_ppg_diff_pct` `is_home` `home_ppg` `away_ppg` | 賽程＋splits | ✅ |
| 分類：`team` `opponent` `position` `stat_category` | 陣容 | ✅（ESPN 位置只係 G/F/C 粗分，同 nba.com 唔同，refit 時要統一） |

## 四、要補嘅缺口：PBP 陣容

ESPN `summary.plays` 每場約 500 條，有 `Substitution`（一場 50–80 次，participants 有入場同離場球員）、分數、時間、投籃座標。2019-01、2022-01、2024-01、2026-10 抽查格式一樣。

做法：每節由正選開始，跟住換人紀錄推進，得出每個回合場上邊 10 個人，再計球員個人在場回合、OFF/DEF_RATING、在場 PACE、on/off。

已知難點：節與節之間嘅換人通常冇紀錄，要由該節第一個動作反推場上球員。呢點係業界常見做法，但一定要先做 parity：用我哋已存嘅 nba.com 球員進階快照（10-20..10-27 窗口）對比，數字貼近先上。

## 五、ESPN 額外資料（按價值排）

| 資料 | 位置 | 對 prop 嘅潛在價值 | point-in-time 風險 |
|---|---|---|---|
| **場上陣容、on/off** | `summary.plays` | 高：隊友缺陣時嘅用球率再分配（S_v3 方向）、真實上場時間結構 | 低：賽後資料，用 as-of 窗口就乾淨 |
| **正選標記、DNP 原因** | `boxscore.players[].starter/didNotPlay/reason` | 高：正選／後備身份變動係分鐘最強嘅預兆 | 低 |
| **傷停詳情**：部位、類型、預計復出日 | `/injuries`、`summary.injuries` | 中高：復出首戰限時、傷患類型 | ⚠️ `/injuries` 只有「今日」，**冇歷史**，要即刻每日快照 |
| **Depth chart** | `teams/{id}/depthcharts` | 中：輪換次序 | ⚠️ 只有今日，要每日快照 |
| **投籃座標＋投籃類型** | `plays[].coordinate`、`type.text` | 中：三分出手區、接波即射／運球後射近似（補返部分追蹤數據） | 低 |
| **讓分、大細分**（DraftKings） | `summary.pickcenter` | 中：大比分領先會令主力坐板凳、節奏預期 | ⛔ 歷史值係**收市價**，落注嗰刻未有 → 回測當洩漏。要用就只可以用我哋自己落注前嘅快照；而且係市場價，按 AGENTS.md 要明文寫入方法論先用得 |
| **球證** | `gameInfo.officials` | 低中：犯規率影響罰球同得分 | 低（賽前公佈） |
| 勝率曲線 | `winprobability` | 只用喺覆盤（垃圾時間解釋 miss），**唔可以做特徵** | 賽後資料 |
| 對手分項 splits、月份、正選 splits | `athletes/{id}/splits` | 低中 | 只有季度累計，要自己按日期切 |
| Rotowire 短評、新聞 | `athletes/{id}/overview` | 低 | 文字，只做顯示 |

歷史深度：summary（box score、PBP、換人、座標、正選、球證）2019 年 1 月已經有，格式一樣；`pickcenter` 2019、2022 有，2024 抽查嗰場冇。球員賽績按季（`gamelog?season=2020`）有。

## 六、轉正步驟

1. **即刻做（唔郁模型）**
   - 每日快照 ESPN `/injuries` 同 30 隊 `depthcharts`。佢哋冇歷史，遲一日就少一日乾淨數據。
   - 訓練觀察加總結欄 `stat_source`（`nbacom`／`espn`／`mixed`）；refit 遇到混合語料要拒絕，除非明確 opt-in，並印出來源比例。
2. **11-14 決定點**：睇 `健康.sh` 嘅 stats.nba.com 狀態紀錄。仲封緊（或者時好時壞）就轉正。
3. **轉正（當模型改動做）**
   - 實現 PBP 陣容 → 球員 OFF/DEF_RATING、在場 PACE；同 nba.com 已存值做 parity。
   - 用 ESPN 重新計晒訓練窗口（2019 起）全部特徵，**一把尺**。
   - 統一位置分類（ESPN G/F/C）。
   - 防守者、DvP 由特徵表移除；`statistics_current` 嘅防守者條件同時拎走。
   - 按 `docs/model-evaluation-contract.md` 跑 regression gate，記實驗。
   - nba.com 唔再用作主來源。之後就算解封，都唔好自動切返，避免同一個訓練窗口又混兩把尺。
4. **之後逐個試新資料**（每樣一個預先登記實驗，先做 leakage 檢查）：正選標記／DNP → 陣容 on/off 用球率再分配 → 傷停詳情 → 投籃類型。

## 七、風險

- ESPN 係**非官方 API**，冇 SLA，格式可能會變。抽取一定要「頁面有幾多 vs 解析到幾多」計數，唔可以靜靜變空（見 `data_contract` 嘅死欄位閘）。
- ESPN 位置分類同 nba.com 唔同；回合數有 0.98 縮放，樣本大咗要再驗。
- 「準確、覆蓋闊、正交」都唔保證落到排名（AU 嘅教訓），新資料一樣要過閘，唔可以因為「有料」就加。

## 重現探測

```bash
B=https://site.api.espn.com/apis/site/v2/sports/basketball/nba
W=https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba
curl -s "$B/scoreboard?dates=20190115"           # 揀 event id
curl -s "$B/summary?event=401071327"             # box、plays（換人）、officials、pickcenter
curl -s "$B/injuries"                            # 今日傷停（冇歷史）
curl -s "$B/teams/2/depthcharts"                 # 今日 depth chart（冇歷史）
curl -s "$W/athletes/3112335/gamelog?season=2020"
curl -s "$W/athletes/3112335/splits?season=2026"
```
