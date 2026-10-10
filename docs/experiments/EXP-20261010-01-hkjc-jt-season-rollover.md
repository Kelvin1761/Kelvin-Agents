# EXP-20261010-01 — HKJC 騎練季節加權換季後失效

- **日期**：2026-10-10；平台：HKJC
- **狀態**：預先登記（結果見下）
- **Harness**：`hkjc_reflector/scripts/hkjc_eval_harness.py`（本次新增，見下）
- **Arm**：`docs/experiments/patches/hkjc_arm_jt_relative_season.py`
- **搜索過嘅舊記錄**：EXP-20261005-01（練馬師近況，live REJECT）、EXP-20260905-03
  （騎練場地拆分）、`live_priors.JT_RATING_PARAMS` 2026-07-08 A7 組合註釋

## 問題（可獨立證明）

`JT_RATING_PARAMS` 註釋寫明設計係「兩季 EB」：練馬師舊季 ×0.3「本季加權先反映到」，
騎師兩季都 ×1.0。但實作用**寫死嘅標籤** `"24_25"` 判斷舊季
（`live_priors._master_stats_paths`、`pit_backtest.build_ratings`）。

2026/27 季開始之後：

| 季度 | 設計原意 | 實際 |
|---|---|---|
| 26_27（本季） | ×1.0 | ×1.0 |
| 25_26（上季） | 練 ×0.3、騎 ×1.0 | **×1.0** |
| 24_25（兩季前） | 唔用 | 練 ×0.3、騎 ×1.0 |

本季得 9 個賽日，被兩個完整季度淹冇。

## 預先登記

- **Baseline**：origin/main `ab52dc35`，PIT priors（`inject_as_of`），production 計分路徑。
- **Candidate**：按季齡加權：本季 1.0；上季練 0.3／騎 1.0；兩季或以上 0。
  冇其他改動，冇調參；權重值照抄原設計。
- **影響範圍**：只有 2026/27 季賽日（25/26 季時，「上季」剛好就係 `24_25`，兩邊一樣；
  語料冇 24/25 季賽日）。所以有效樣本 ≈ 今季賽日，功效好細。
- **判決**：§7 正確性修正（實作違反自己寫明嘅設計）。要求：零顯著 primary 退步、
  leakage PASS。唔聲稱表現改善。
- **語料**：所有有賽果嘅 HKJC 賽日；剔走 `speed_score` 全場死嘅賽日（04-12 至 04-29）。

## Harness 忠實度驗證

`hkjc_eval_harness.py run --no-pit`（live priors）對 2026-10-07 跑馬地：同一份 code
喺 meeting 副本上真正跑 `hkjc_auto_orchestrator.py`，**9/9 場完整排名逐位一樣**。
舊 `rescore_backtest.rescore_logic` 漏咗 10-08 上線嘅 race_shape 全場封頂，
而且用顯示分排序，所以佢量緊嘅唔係 production。

## 結果

語料：origin/main `ab52dc35`，PIT priors，剔走 `speed_score` 全死賽日（04-12 至 04-29），
配對後 **272 場**（兩邊都失敗嘅場次剔走；兩邊共同失敗 16 場全部係 SCORE-004 初出馬封頂
bug，另 6 場係排位表退出馬）。37 場排名有改變，全部喺 2026/27 季。

| 指標 | dev Δ | terminal Δ | terminal 95% CI |
|---|---:|---:|---|
| Gold | 0.00 | 0.00 | — |
| Good（位置） | 0.00 | 0.00 | — |
| top3_capture@5 | −0.0030 | 0.0000 | [0, 0] |
| NDCG@5 | −0.0022 | +0.0091 | [−0.0001, +0.0220] |
| competitive_recall@5 | −0.0011 | 0.0000 | [0, 0] |
| 實際前三平均模型名次（低＝好） | +0.0060 | **−0.0278** | [−0.0556, −0.0069] |

賽日 Good SD：0.1570 → 0.1570（不變）。場地 cohort：Gold／Good 全部 0 差；冠軍
沙田草地 +0.67pp、跑馬地 −1.09pp（1 場）。

**Stage 4 v2**：`REJECT / ranking_evidence_too_weak`（冇一個 ranking metric dev 同
terminal 都正）。**唔係表現改善。**

**§7 判斷**：實作違反自己寫明嘅設計（如果績效數字相反，我仍然會修佢）；primary 兩個窗
都係零差；冇 terminal CI 全負嘅指標；leakage：只改歷史季度權重，PIT cutoff 不變 → PASS。
→ **CORRECTNESS PROMOTE**。

## 順帶發現

1. **VERDICT-002 潛伏 bug**：`ensure_verdict` 同分時用 raw 分排、validator 用顯示分排。
   `rank_score` 係兩位小數顯示分，兩匹馬顯示分一樣但 raw 唔同、而 raw 高嗰匹馬號較大時，
   validator 會**成場拒絕**。今次 2026-10-07 跑馬地 R5 喺候選觸發。另行修正。
2. **舊 replay 唔係 production**：見上面 harness 忠實度驗證。

## 重判（Stage 4 v3，全紀錄，main `c99f28b4`）

正確性修正 B 上線之後重跑，用 v3 `fixed_rule`（冇由數據學嘢）：286 場、39 場排名有變。

| 指標 | 全紀錄 Δ | 95% CI（賽日 bootstrap） |
|---|---:|---|
| Gold | 0.0000 | [0, 0]，6 個時間塊全部 0 |
| Good（位置） | 0.0000 | [0, 0]，6 個時間塊全部 0 |
| top3_capture@5 | −0.0023 | [−0.0060, +0.0000] |
| NDCG@5 | −0.0002 | [−0.0034, +0.0031] |
| competitive_recall@5 | −0.0009 | [−0.0027, +0.0000] |
| 實際前三平均模型名次 | −0.0000 | [−0.0080, +0.0074] |

v3：`REJECT / ranking_evidence_too_weak`（冇改善）。§7：primary 零差、冇指標 CI 全負、
leakage PASS → **CORRECTNESS PROMOTE**，唔聲稱表現改善。v2 terminal 嗰個「平均名次改善」
喺全紀錄消失，證實係細樣本噪音。
