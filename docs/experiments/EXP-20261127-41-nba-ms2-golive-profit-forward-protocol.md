# EXP-20261127-41 協議：MS2 上線＋盈利 forward（上線後量「盈利有冇改善」）

- **日期**：2026-11-27（喺上線同任何 forward 數據之前 commit）
- **平台**：NBA
- **決定人**：Kelvin（2026-11-27：「上線 and track with forward」），背景係 EXP-20261127-40：MS2 嘅 log-loss PASS，但盈利未證實。
- **風險級別**：B（改發佈機率）。實作 Terra、Sol 覆核，Opus 收貨。

## 上線咩
1. **發佈機率 `p_final` 改做 MS2**：`logit p = a_stat + 0.6514·logit(clip(1/價)) + 0.3494·logit(clip(p_s2))`，clip 0.02–0.98，
   截距 PTS −0.2285、REB −0.1958、AST −0.1767、FG3M −0.0545（EXP-20261111-05 凍結係數，原封不動）。寫入 `config.json` 新段 `ms2_layer`。
2. **冇 `p_s2` 嘅腿**（今季 <5 場、基本時間 <15 分鐘、冇讓分）照用現行 MS；MS 都冇就 C（同而家一樣）。
3. `probability_model_id` 要變（包埋 `ms2_layer`），咁 ledger 分得開上線前後。
4. **舊發佈機率留做 shadow**：`p_legacy` = 舊規則（MS，冇就 C），寫入 sidecar 同 ledger `model_obs`。
5. **精選 card 跟 MS2**（Kelvin 落注嗰張），規則 `nba-featured-ou-v1` 其餘不變。同時用 `p_legacy` 揀一張 **shadow 精選**（`featured_legacy`，唔發、唔上板）。

## 現有 forward 測試點處理（樣本唔斷）
佢哋全部係按舊發佈機率預先登記嘅，所以一律改讀 **`p_legacy`**（上線前嘅行冇呢欄 → 用 `p_final`，兩者喺上線前定義上一樣）：
- EXP-20261109-04 M／T、EXP-20261110-03 FU_AVG／FU_EDGE、EXP-20261120-60 V2_250／V2_600、EXP-20261124-61 RC：讀 `p_legacy`。
- EXP-20261110-01 F250／F1000：上線日起數 **`featured_legacy`**（同一規則、同一機率 = 同一個 arm）；上線前照數 `featured_records`。
- 呢個只係換欄位名，唔改任何判決規則；實作時要用上線前數據證明每個 evaluator `status` 數字完全一樣。

## 盈利 forward（新）
- **母體**：上線後第一個 21:00 run 嘅 target_date 起；每晚 21:00 production 快照（odds＋sidecar），按 ledger 結算，void 唔計。
- **arm**：live = `p_final`（MS2）；shadow = `p_legacy`（舊 MS）。兩邊用同一張盤、同一個價。
- **主指標（ROI，平注 1u）**：大細盤**全部兩邊**、edge ≥ 5pp、價 ≤ 3.0（同精選一樣嘅去水同門檻，但唔限每場一注、唔限每日 10 注）；
  Δ = ROI(live) − ROI(shadow)，按日 cluster bootstrap 2,000 次，seed 20261127。
- **夠數**：≥28 個比賽日而且 live ≥ 600 注；用到夠數嗰日為止，判一次，結果凍結，Telegram primary 推一次。
- **判決**：
  - Δ 95% CI 下限 > 0 → **盈利改善成立**，MS2 留低。
  - Δ 95% CI 上限 < 0 → **MS2 令盈利變差**，建議退返舊 MS（Kelvin 決定）。
  - 跨零 → 盈利冇分別；MS2 因為 log-loss PASS 留低，唔再為盈利延長。
- **次要（只報告）**：精選 card（每場一注）live vs shadow ROI；兩個 arm 各自 ROI 同 95% CI（有冇一個真係賺錢）；
  log-loss MS2 − legacy（上線後重複驗證 EXP-20261111-05）；逐 stat。
- **功效（預先講明）**：EXP-20261127-40 事後重揀見到每日約 24 注（shadow）／16 注（live）→ 28 日約 450–650 注，ROI 差嘅 CI 半闊大約 ±6–8pp，
  即係只捉得到大差距；細過呢個嘅改善會判「冇分別」。

## 洩漏檢查
- 兩個 arm 用同一刻嘅價同同一批輸入；係數全部喺今日之前凍結；判決只用上線後數據。
- 事後分析（EXP-20261127-40 嘅 11-12…11-26）唔入母體。

## 唔准
- 唔准喺同一批數據改門檻、改窗、改係數再判；唔准提早停（optional stopping）。
- AGENTS「用戶睇到嘅改動」：dashboard 要顯示發佈機率模型已換（MS2）同 forward 進度；完成後 Telegram primary 講人話。
