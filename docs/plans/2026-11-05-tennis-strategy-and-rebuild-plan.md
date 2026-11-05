# Tennis Wong Choi：盈利策略 + 精選 + 夜晚落注 + 重建 —— 總計劃

- 建立：2026-11-05（Claude Code，同 Kelvin 對話整理）
- 狀態：**計劃，未實作**。Codex 已停手，tennis 由呢份計劃接手。
- 原則：跟 `AGENTS.md`「改模型嘅規矩」同 `docs/model-evaluation-contract.md`；統一研究計劃
  （`tennis-research-execution-plan-20261028.md`）嘅 15 個 REJECT_DEV 唔重開。

---

## A. 已量到嘅事實（2026-11-05，live DB 唯讀）

### A1. 真實成績（只計賽前可核實，`is_point_in_time=1`）

| 範圍 | 注／場 | ROI | 95% CI |
|---|---:|---:|---|
| 全部 value prop 注（08-11 起） | 1,357 注 | −10.7% | [−15.7, −5.7] |
| 回填批（時間未知，05–08 月） | 1,495 注 | +11.2% | 唔算數 |
| Match-winner 參考單 | 273 注 | −13.8% | [−27.3, −0.8] |
| 正式推薦子集（10-28 起，Telegram「+2.2%」） | 188 注／**77 場** | +2.2% | 按場 [−16.1, +21.1] |

- 每個 family 都係負或者 CI 跨零。dashboard 見到「ROI 唔差」係回填批撐起。
- 模型自報 edge 唔排得到結果（edge 20%+ 一樣 −10.1%）。
- 模型 Brier 0.2098 輸市場 0.1902。
- 逐月改善：08 −21.6% → 09 −12.2% → 10 −6.7% → 11 −2.4%。
- 實盤（`prop_live_bets`）0 注。

### A2. 同場疊注（Kelvin 觀察到「一個人 3–4 注」）

- 10-28 起一場最多 10 注、同一球員最多 8 注（讓 1.5／2.5／3.5 局同時買）。
- 264 場多注賽事：每場 edge 最高嗰注減同場其餘平均 **+15.1pp [+4.2, +25.9]**（歷史探索，要前向驗）。
- 一場一注（edge 最高）全期 636 注 −6.5% [−14.8, +1.5]；逐月 08 −20.9% → 09 −10.2% → 10 −2.7% → 11 +15.5%（31 注）。
- 每日揀頭 10 注（按 edge／EV／機率）冇改善；按機率（「最有信心」）最差 −16.4%。

### A3. 落注時間

- 而家 card 09:00 悉尼出；精選注開賽中位數 4.7 個鐘後，一成 1 個鐘內開。
- 開賽集中 09:00–18:00 悉尼（美洲朝早、亞洲下晝）；18:00 後歐洲場好少入 card。
- 88% 注由出 card 到開賽賠率冇郁；收市／card 平均 0.998 → 早落冇損失。
- 18:00 嗰輪抓明日盤：排程註解寫 listing 未開。
- **2026-11-05 22:36 單次試抓**：明日 36 場已列出，部分已有讓局／總局數／讓盤／贏一盤（一場最多 40 盤），部分仲淨係獨贏。→ 夜晚落注有機會。

### A4. 發現嘅問題

1. **card 已經三星期冇出過正式推薦（已確認）**：10-28 至 11-06 每日都係「⚠️ 資料未就緒」；
   10-14 至 10-27 大部分係「❌ 今日無清晰好注」。封鎖理由係**累計歷史**數字（119 場 disputed、
   08-27 起 23% props 冇賽前時間），唔係今日 slate，所以永遠過唔到。
   Kelvin 實際睇緊嘅係 dashboard 全部紙上 value 注。
2. `clv_tracker` 同 `prop_tracker` 同一注結算唔同：8 月 55 注球員總局數判錯，冇重新結算。兩本帳。
3. `combo_tracker` 08-16 後冇新行（排程冇叫 `sync-combo-tracker`）；7 月試驗組合 −92.5%。
4. `recommendation_gate` 每日對 8 個 family 重複測，正 ROI + P(蝕)≤10% 就自動開正式注 → 遲早靠運氣過閘。

### A5. Codex 交接狀態

- 所有 tennis 分支已 push，worktree 冇未保存改動。
- 今日四條：三條已入 main；`codex-tennis-espn-bo5-20261105` 已被 main `7b840d11` 取代。
- `codex-tennis-book-tour-ingest-20261104`：Central 已拒絕。
- 未合併研究：`codex-tennis-source-owner-guard-20261104`（22 commit，身份／Elo generation）、
  `codex-tennis-identity-clock-20261102`、`codex-tennis-point-input-delivery-20261101`、
  `codex-tennis-unified-research-20261028`（15 REJECT 證據）。只作參考。

---

## B. 已拍板嘅策略（Kelvin 2026-11-05）

1. 前向測試取代自動閘：閘只可以「停」，唔可以自動開正式注。
2. 停組合注（card、Telegram、dashboard、tracking 全部拎走）。
3. 暫停靠技術統計結算嘅 family：`player_aces`、`player_double_faults`、`match_total_aces`，同 `player_exact_set_score`。
   保留靠比分結算嘅 6 個：讓局、首盤勝方、贏一盤、首盤讓局、讓盤、總局數。
4. 前向測試未過，唔落真錢。
5. 加「精選」：最多 10 注，可以係 0。
6. 想好似 NBA 咁 **21:00–00:00 落晒**，要先量到做唔做到。

---

## C. 精選嘅定義（預先登記，鎖定之後唔准睇結果再改）

一注要入精選，全部條件都要過：

1. `is_value=1`，而且過 `strategy.meets_formal_profile`（同正式推薦同一個判斷）。
2. family 屬 B3 嘅 6 個比分結算 family。
3. 賽事唔係 `DISPUTED`／mock；定價時間早過開賽（point-in-time）。
4. **一場一注**：同場揀 edge 最高；打和揀 EV 高；再打和揀賠率高。
5. **每日最多 10 注**：按 edge 由高到低；唔夠 10 注就照出，0 注就寫「今日無精選」。
6. 平注 1u。

凍結規則：

- 精選喺**出 card 嗰刻寫低**（新表 `featured_picks`：prop_id、match_id、card_run、rank、odds、edge、featured_at），之後唔改。
- 同日之後再 refresh：只可以**加**未入選、未開賽嘅場次（仍然受每日 10 注上限），唔可以剔走已出嘅注。
- 結算直接讀 `prop_tracker` 結果，唔另計一份帳。

**「要賺錢」嘅誠實講法**：精選只係減少損失（A2）。要賺錢要靠 F 部分嘅研究（更好價錢、更準模型）。
精選嘅任何再收窄（例如加 edge 門檻）都要另外預先登記，唔可以用 A 嘅歷史數據揀。

---

## D. 前向測試（預先登記）

| Arm | 定義 | 起點 | 判決點 |
|---|---|---|---|
| A 正式全部 | 現行正式推薦（formal profile） | 2026-10-28（凍結定價證據開始） | 250 場 |
| B 精選 | C 部分 | 上線日起；10-28 之後可以重播，但只係描述，唔計入判決 | 250 場（≈ 250 注） |

- 指標：ROI，**按場 cluster bootstrap** 4,000 次，seed 20260826，95% CI。
- 判決：CI 下限 > 0 → `ELIGIBLE_FOR_RELEASE_REVIEW`（Kelvin 決定落唔落真錢）；CI 上限 < 0 → `REJECT`；
  其他 → 繼續到 600 場再判一次，之後唔再延長。
- 功效：每注 SD ≈ 1.0；250 注 CI 約 ±12.8%，只捉到 +13% 以上；600 注約 ±8%。照實寫入記錄。
- 夠數**第一次**就推 Telegram（跟 AGENTS.md forward 規則）：新增 tennis forward tracker，
  仿 AU／HKJC `FORWARD_TESTS`；`AGENTS.md` 加 tennis 一行。
- 永遠唔會自動改模型或者自動開真錢。

---

## E. 執行步驟（逐步做，每步都要 `./檢查.sh` 同 `./保存.sh`）

### 第 0 步：夜晚試抓（今晚起，一星期）

- 新 launchd job：每晚 **21:00 同 23:30** 悉尼，唯讀抓**明日**全部賽事 + props。
- 寫去獨立檔（`<資料根>/Tennis_Night_Probe/<日期>/<時間>.jsonl.gz`），**唔寫** `prop_tracker`／`market_odds_snapshots`，唔影響現役 card。
- 每朝 09:00 card 出完，對比報告：
  1. 精選注入面，幾多注前一晚 21:00／23:30 已經有盤；
  2. 嗰陣嘅價同 09:00 一唔一樣；
  3. 幾多精選賽事喺 00:00–09:00 開（而家 card 完全捉唔到，夜晚 card 會多咗呢批）。
- **預先定好嘅判斷**（一星期後）：
  - ≥80% 精選注 21:00 已有盤，而且 ≥90% 價錢同 09:00 一樣 → card 改去 **21:00 出、21:00–00:00 落**（似 NBA），09:00 只補漏；
  - 23:30 先達標 → card 改 23:30；
  - 都唔達標 → 維持 09:00 card，09:00–09:30 落，先落最早開賽嘅。
- 結果推 Telegram。

### 第 1 步：card 解封同誠實化

1. 修 A4-1：「資料未就緒」改成只判斷**今日 slate** 嘅資料（今日場次 disputed、今日定價時間），歷史問題放「數據狀態」區顯示，唔再封鎖 card。
2. card 頂部改成「🎯 今日精選（N／10）」；其餘紙上 value 注降做參考區。

### 第 2 步：精選上線

1. `featured_picks` 表 + 選注函數（純函數，有單元測試：一場一注、上限 10、0 注、打和規則、只加唔減）。
2. card、Telegram（`daily_bet_message` 只推精選）、dashboard（`tennis_tracking.py` 加精選紀錄同獨立 ROI）。
3. Telegram 每日績效加：精選前向進度（x／250 場、ROI、CI）。

### 第 3 步：策略清理

1. 停組合注：card、Telegram、dashboard 拎走；`combo_tracker` 保留歷史唯讀。
2. 暫停 4 個技術統計 family 嘅推薦（研究記分卡可以照記）。
3. `recommendation_gate`：拎走自動開正式注嘅路，只留停損（drawdown／近期轉負就停）。

### 第 4 步：登記同記錄

1. `docs/experiments/EXP-20261105-xx-tennis-featured-forward.md`：A 部分量度 + C／D 定義 + 指令 + commit hash。
2. tennis forward tracker + `AGENTS.md`。
3. 舊 `clv_tracker` 8 月總局數錯結算：寫入記錄，留待重建時合併帳本，唔即刻改歷史。

### 第 5 步：重建（第 0–4 步上線後先開始）

- 範圍：模型、選注、報告、帳本。**唔掂**抽取同身份層（第 6 步先處理）。
- 方法同 NBA（EXP-20261103-15）：新引擎逐場 replay，對比舊引擎結果一樣先換。
- 同時做：一本帳（合併 `clv_tracker`／`prop_tracker`／`combo_tracker`）；剷走組合、4 個暫停 family、
  回填期嘅相容 code、自動閘；`daily_report.py`（5,200 行）拆細。
- 統一計分 kernel（研究計劃 C08／C09，令所有 props 互相一致）會改輸出 → 當獨立候選，過
  `model-regression-gate` 先用。
- 15 個 REJECT_DEV 唔重開。

### 第 6 步：接手 Codex 數據線

- 按研究計劃「下一步」：來源身份、as-of Elo generation、缺特徵來源。
- 先讀 `codex-tennis-source-owner-guard-20261104` 嘅記錄再決定接邊幾段；喺重建後嘅新底上做。

### 第 7 步：令精選真係賺錢嘅研究（每項都要預先登記）

1. **更好價錢**：Sportsbet 以外有冇其他莊家／exchange 開同類 props；同一注賠率高 3% = ROI 加 3 個百分點，唔使模型變準。
2. **模型準過市場**：等第 6 步數據修好之後先再試；Brier 要先贏市場。
3. 精選再收窄（例如 edge 門檻、賠率範圍）：只可以作為新 arm，前向驗。

---

## F. 時間表（估計）

| 時間 | 事項 |
|---|---|
| 11-05 晚 | 第 0 步試抓上線 |
| 11-06 – 11-08 | 第 1–4 步（card 解封、精選、清理、登記） |
| 11-12 左右 | 試抓一星期判斷：夜晚 card 定朝早 card |
| 11-09 起 | 第 5 步重建 |
| 約 12 月中 | 精選 250 場第一次判決（每日約 10 注） |

## G. 要 Kelvin 決定嘅嘢

1. 前向判決點 250 場（約 6 星期）定直接 600 場（約 2 個月）？
2. 精選打和規則（edge → EV → 賠率）OK？
3. 夜晚 card 判斷門檻（80% 有盤、90% 同價）OK？
4. 紙上 value 注（非精選）仲要唔要喺 dashboard 顯示？建議保留但標明「參考，唔係建議」。
