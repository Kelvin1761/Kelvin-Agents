# EXP-20261113-21 預先登記：AU 噪音訊號＋重複計分（睇任何 arm 結果之前寫）

觸發：Kelvin 2026-11-13 睇完標籤審計（`docs/audits/au-label-audit-20261113/`）：
「訊號噪音睇下要改善、修定剷；重複計分嫌疑如果留就歸返去應該屬於嘅位。」

## 語料同判決器

- 語料：`scratch/au_noise_dump_20261113.py`（= `au_dump_engine_leaves.py` ＋ 研究欄 `track_going_adj`），現行引擎重評全 archive。
  BASE = origin/main `d59f67e6`；FLFIX = 同一 code ＋ 賽績線延續行 parser 修正（只影響唔入分嘅 `formline_score`）。
  檔案：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/`。
- 判決窗：2026-08-05 起（乾淨 point-in-time）。判決器 v3 `evaluate_full_record`，`fixed_rule`（冇一個 arm 由數據 fit 數值），
  ranking metric = `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`，賽日 bootstrap 2000 次。
- arm 全部喺 BASE dump 上離線重算綜合分：`ability = compose(matrix(features')) + overlays'`；
  先做 A/A（arm = BASE）確認重算同 dump 嘅 `ability` 一致（最大差 < 1e-3），唔一致就停。

## Arm（一個 family，Holm 調整）

| arm | 改動 | 問題 |
|---|---|---|
| **D1 GO** | 濕地日 `track_score` 減走 `track_going_adj`（場地維度只剩同場往績；地況證據全部交俾濕地 overlay） | 重複計分：留邊一份 |
| **D2 WO** | 剷濕地 overlay（地況證據只留喺場地維度） | 同上，反方向 |
| N1 | `trial_speed_score` → 60（試閘備戰只剩試閘密度） | 90.5% 中性，係咪噪音 |
| N2 | 試閘備戰成個維度 → 60 | 剔中性 AUC 0.525 |
| N3 | `class_score` → 60（官方評分對位只剩 Rating） | 場內只 ~4 個值 |
| N4 | `track_score` → 60（成個場地維度） | AUC 0.546 |

唔測：大場次檔位（用戶接受嘅實驗性上線，forward 1,000 場監察緊，唔可以喺中途用另一個測試推翻）；
近績質素、L600、騎師、練馬師、人馬配搭、Rating（審計量度全部健康）；逐駒全程速度（AUC 0.624，幅度細但方向啱）。

## 判決規則（預先鎖定）

剷走／搬走類 arm 係簡化，唔係求改善，所以用 EXP-20261102-10 同一條「冇代價簡化」準則：

1. Gold、Good 位置全紀錄點估計 **≥ 0**，而且 6 個時間塊入面 ≥ 4 塊 ≥ 0；
2. 冇 ranking metric CI 上界 < 0；
3. 預先聲明分層（馬群大細、今場地況、首選 SP、路程）冇一格 Gold／Good CI 全負。

三條全過 → **可以剷／搬**（簡化）。另外如果 v3 判 PRIMARY_WIN／RANKING_WIN，要 Holm 調整後 p < 0.05 先可以報「改善」。
D1、D2 互斥：兩個都過就揀 Gold＋Good 合計點估計較高嗰個；兩個都唔過 → **兩份都留**，
顯示上將濕地往績調整歸入「場地與地況適性」嗰格（合併顯示「場地維度 ＋ 濕地調整」），純顯示、排名零變化。

## 顯示 leaf（唔入分）

資料覆蓋分、出賽間隔分、負磅分、檔位分、路程分、賽績線分（用 FLFIX 重量）：
場內 AUC（剔中性）95% CI **包含 0.50** → 報告唔再印呢個數字做「分」（文字理由保留）；CI 全部 > 0.50 → 照留。
呢個係顯示決定，唔改排名。

## 記錄

結果寫 `EXP-20261113-21-au-noise-and-double-count-results.md`；判決 JSON 放 `EXP-20261113-21-evidence/`。
失敗 arm 照記。冇過嘅 arm 唔會 commit 任何 model code。
