# EXP-20261110-03 協議：NBA 大細盤 under 兩個紙上 arm —— forward 預先登記

- **日期**：2026-11-10（喺任何 forward 數據存在之前 commit）
- **平台**：NBA
- **決定人**：Kelvin（2026-11-10：「補賽果＋登記測試」）
- **凍結**：判決腳本 `docs/experiments/patches/nba_under/evaluate.py`（同本文件同一個 commit）。
- **永遠唔會自動落注，唔改 p_final／B2／SGM／精選規則（`nba-featured-ou-v1`）。** 純紙上，冇 card、冇 dashboard。

## 點解（探索性觀察，唔係證據）
2026-11-10 全面掃描（ledger 10-21…11-09，16 個比賽日，5,535 條已結算大細盤線，收市價平注）：
- 全部 over −10.6% [−14.2, −7.0]；全部 under −2.3% [−5.8, +1.1]。去水後 over 應中 48.8%，實際 46.6%。
- milestone 盤同大細盤同一條線嘅價一致（19,777 次配對，比例中位 1.00，零套利）。
- 開盤對收市冇分別（under −1.7% 對 −2.3%）。
- 兩個切出嚟嘅 under 子集（**切咗好多刀先見到，樣本細，時間切分後半先顯著**）：
  - 線高過 L10 平均 >5%：前半 +4.7% [−8.2, +16.0]（227 注）、後半 +13.4% [+1.0, +26.9]（276 注）。
  - 模型 under edge ≥8pp：前半 +4.2% [−16.8, +15.2]（309 注）、後半 +14.9% [+7.7, +23.3]（149 注）；5–8pp 嗰段 −3.0%。
- 警告：(1) 同一批數據試過十幾個切法；(2) 得 12–16 個比賽日、全部季初（L10 仲混住上季）；(3) 探索用收市價同
  任何 role 嘅最新 model_obs，同下面凍結嘅口徑唔完全一樣；(4) 引擎 11-04 換過。所以一定要 forward。

## 規則（全部凍結）
- **母體**：target_date ≥ 2026-11-11；Sportsbet 球員大細盤每條 .5 線（PTS／REB／AST／3PM），只買 **under**，平注 1 單位。
- **模型行**：該腿（同球員同 stat，milestone 線 = ceil(O/U 線)）開波前最新一條 `snapshot_role = production` 嘅 `model_obs`。冇就唔計。
- **價**：`captured_at` ≤ 嗰條模型行 `odds_captured_at` 嘅最新一條開波前 `ou_two_way` 價。冇就唔計。
- **去水**：fair_over = (1/over) ÷ (1/over + 1/under)。
- **FU_AVG**：模型行記錄嘅 `l10_values` ≥ 5 場，而且 (平均 − O/U 線) ÷ max(O/U 線, 1) < −0.05。
- **FU_EDGE**：fair_over − p_final ≥ 0.08。
- 一條線可以同時入兩個 arm；兩個 arm 分開判。冇價錢上限、冇每場／每日上限。
- **結算**：ledger settlement 嘅 `actual` < O/U 線 = 中；`void`（冇上場）唔計注。

## 判決
- **FU_AVG**：頭 1,200 注已結算；**FU_EDGE**：頭 300 注已結算。各判一次，結果凍結，冇中期檢查。
- PASS：平注 ROI 嘅 **97.5%** CI 下限 > 0（兩個 arm，Bonferroni）。按日 cluster bootstrap，2,000 次，seed 20261111。
- 夠數由 `nba_forward_tracker`（postgame）自動判一次，Telegram primary 推一次。

## 功效（預先講明）
- 11-07…11-09 按凍結口徑數注數（冇睇結果）：FU_AVG 每日約 25–39 注、FU_EDGE 每日約 2–5 注。
  即係 FU_AVG 約 5–7 個星期、FU_EDGE 約 2–3 個月夠數。
- FU_AVG 1,200 注 CI 大約 ±7pp；FU_EDGE 300 注大約 ±13pp。真 edge 細過呢個幅度大概判「未過」—— 寧願漏，唔好信錯。
- FU_EDGE 揀 300 而唔係更大，係因為今季剩低嘅比賽日唔夠；代價係只有好大嘅 edge 先判得出。

## 洩漏檢查
- L10、p_final、價全部係開波前寫入 ledger 嘅觀察（`post_tip = false`），賽果只用嚟結算。
- `l10_values` 由 extractor 按 `history_date_to` 截到賽前一日。

## 唔通過
記低點樣失敗。唔准喺同一批數據改門檻（5%／8pp）、改 side、改 stat 再判；要再試就開新實驗編號。
PASS 亦唔會自動改精選規則 —— 要另外登記新 `RULE` 同新協議，由 Kelvin 決定。

## 重跑
```bash
python3 docs/experiments/patches/nba_under/evaluate.py status     # 只顯示已結算注數
python3 docs/experiments/patches/nba_under/evaluate.py evaluate   # 未夠數會拒絕；已凍結就讀返
```
