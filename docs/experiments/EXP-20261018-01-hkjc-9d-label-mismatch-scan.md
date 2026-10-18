# EXP-20261018-01 — HKJC 全 9D 標籤錯配掃描 ＋ 舊存檔 venue 補值（§7）

- **日期**：2026-10-18；平台：HKJC；**審計 + §7 正確性修正**
- **觸發**：Kelvin —— 段速審查（EXP-20261016-14）搵到「改善中 vs 進步」由 2026-06-19 起靜靜令 +5 從未觸發；
  要全 9D 掃同一類缺陷，再深入騎練訊號。
- **工具**：`docs/experiments/patches/hkjc_label_mismatch_scan.py <repo> out.json`

## 方法

1. AST 掃 `hkjc_racing_engine/`（含 features、renderer）每個 `"關鍵字" in X` 同 `any(k in X for k in (...))`，
   將 X 追返去讀嘅 Logic 欄位（`_text`／`_value`／`_clean`／`.get`，一層局部變數）。共 **222 個檢查**。
2. 對全部存檔 Logic（4,788 匹）逐欄位數每個關鍵字命中幾多匹，列出每欄真實標籤詞彙。
3. 讀唔到欄位嗰 72 個（引擎自己產生嘅字串）：查關鍵字喺引擎／Facts 生成器有冇第二處出現（即有冇人產生佢）。
4. 巢狀結構（海外賽績、賽績線行、晨操紀錄）同 `race_analysis` 另外人手核對。

## 結果

| # | 位置 | 檢查 | 實際 | 影響 | 處理 |
|---|---|---|---|---|---|
| 1 | `engine_core._apply_finish_time_trend` | 「進步」 | Facts 寫「📈改善中」，0 命中 | +5 從未觸發（單邊 −5） | **已剷**（EXP-20261016-16） |
| 2 | `features/draw.py`、`_is_sha_tin_context` 等 12 處 | `race_context["venue"]` | 2026-04-12 → 05-09 九個賽日 81 場**冇 venue**／10 場 'Unknown' | DrawScorer 當全部係跑馬地，沙田配方唔生效。live 冇事；**回放語料入面 04-19 → 05-09 七個賽日（70 場）**每個 A/B 都計錯（harness 而家只剔 04-12、04-15 兩日） | **§7 修**：score_race 由資料夾名補 venue |
| 3 | `speed.py` 步速修正等級 | 「持續快於標準」「略快於標準」 | `finish_time_adj_level` 只有 4 級（仍具競爭力／接近平均／仍偏慢／明顯落後），0 命中 | 死分支，冇計分影響（Facts 嘅「完成時間水平」先有呢兩級，但引擎讀緊另一個欄） | 記錄；段速已審 |
| 4 | `_health_readout`（顯示） | 長休 > 60 日：「快操」「試閘」= 操練充足 | 每份晨操摘要都有「近#日快操#課、試閘#課」模板字 | 長休馬幾乎一律印「復出前操練量充足」（897 匹只有 1 匹快操同試閘都係 0） | 純顯示；留俾晨操審查 |
| 5 | `_candidate_health_risk_score` | 體重走勢分支 | 「持續增磅」「持續減磅」（144 匹）唔入任何分支 | 呢批 0 分，而「微增／微減」有加分 —— 可能係設計，未驗證 | 留俾馬匹健康審查 |

**冇問題（掃描初步標紅但核對後正常）**：
- 「急增／急減／大增／大減」：同一個 tuple 入面真實標籤（急劇變化／顯著轉輕／顯著轉重）照中，舊別名死咗冇影響。
- 海外賽績 G1／G2／G3：`class_level` 係「3yo G2」之類，有 128 行命中，加分有觸發。
- 「連勝」：由 `_margin_trend_display()` 即時產生，唔係讀存檔欄。
- 引擎內部字串 72 個：只有 `Indeterminable` 冇人產生（同一行另一個別名照中）。

## §7 修正：舊存檔 venue

- 錯處獨立證明：`race_analysis` 冇 `venue` 時 `draw.py` 落 `else "跑馬地"`；05-03／05-09 資料夾明明係沙田。
- 改動：`hkjc_auto_orchestrator._meeting_venue_for_logic`；`score_race` 喺 venue 空白或 'Unknown' 時由資料夾名補。
  live Logic 一律有 venue → **live 排名零改變**。
- 測試：`tests/test_meeting_venue.py`。
- 回放影響：見下面「回放結果」。

> 呢個係正確性修正，冇通過表現閘，唔係一個已證實嘅改善。

## 回放結果（harness 全語料，main `f852b3d5` vs 修正）

- 365 場入面 71 場排名有郁，**全部喺嗰九個冇 venue 嘅賽日**（沙田六日 63 場、跑馬地三日 8 場；
  跑馬地都郁係因為 `_is_happy_valley_context` 而家先返 True）。其他賽日 0 場改變 → live 零影響得到確認。
- Stage 4 v3 `fixed_rule`（剔 04 月死日後 345 場，57 場有郁）：Gold +0.58pp [0.00, +1.75]、Good 0.00 [−1.17, +1.14]、
  NDCG@5 −0.0008、competitive_recall +0.29pp [0.00, +0.66]；判決 `ranking_evidence_too_weak`（§7 唔要求）。
- 受影響、仍喺語料嘅七日（70 場）：Gold 12 → 14、Good 20 → 20（逐日：04-26 Gold +2／Good +1、05-03 Good +1、05-06 Good −1、05-09 Good −1，其餘不變）。
- 分層：冇 CI 全負。首選 SP 2.6–4 Good −2.94 [−6.30, 0.00] 上界貼 0，記低。
- **之後所有 HKJC 回放 A/B 嘅 baseline 都會郁呢 57 場** —— 舊數字同新數字唔可以直接比。
