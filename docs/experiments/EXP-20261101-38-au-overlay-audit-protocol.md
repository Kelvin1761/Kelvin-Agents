# EXP-20261101-38 預先登記：AU 隱藏 overlay／後置調整逐個消融

> 量度之前寫。結果另寫 `EXP-20261101-38-au-overlay-audit-results.md`。

- **日期**：2026-11-01；**平台**：AU；**baseline**：production（`dump_shipped.json`，`1c7e1794` 引擎）。
- **用戶指示**：「list every overlays and hidden scores that is not displayed on the dashboard and test them one by one to see if
  they are helping the analysis performance, and if we should keep them. If we are keeping them, best they can be displayed on
  dashboard, so ideally if these overlay can be turned into a part of scoring would be great」

## 清單（會改排名、唔喺 dashboard 七維入面顯示）

代碼位置：`engine_core.analyze_horse`（綜合分 = 七維矩陣 + 三個 overlay）、`renderer.ensure_verdict`（後置排名調整）。

| # | 項目 | 做法 | dashboard |
|---|---|---|---|
| O1 | 濕地 overlay `wet_form_feature` | 黏／大爛地日按濕地往績加減分（乾地 0） | 冇 |
| O2 | 班次證明 overlay `proven_class_feature` | 場內 z × `PROVEN_CLASS_Z_WEIGHT`（EXP-20260825-03） | 冇 |
| O3 | 逐駒全程速度 `full_time_speed_feature` | gain 1.5 × z × 可靠度（2026-10-16 起，只有 RQ 數據） | 部分 |
| O4 | 距離轉變罰分 | 近績質素分：今仗同上仗差 ≥400m → −5（2,452／31,246 匹） | 冇（leaf 內） |
| O5 | 證據厚度安全欄 | 首選有 ≥2 個計分 leaf 停喺 60 → 同第 2 對調 | 冇 |

唔入清單：信心級數、`top_pick_tied`、第 4–6 名觀察名單（純顯示，唔改排名）；`class_score_live_delta`（影子數，唔入分）；
各 leaf 內部嘅細規則（之前另有審計，例如 EXP-20261028-13 班次規則）。

## 消融（`fixed_rule`，冇 fit 任何數）

每個 arm 只拎走一樣，其餘照 production：

- X1：綜合分 − O1；X2：綜合分 − O2；X3：綜合分 − O3（只有 2026-10-16 起有值，約 760 場，功效低，照報）；
- X4：O4 罰分改 0，用 `au_fq_weight_class_eval_20261028.fq_scores` 重算近績質素分（replica 已核：31,246 匹 0 匹差），再重算綜合分；
- X5：語料嘅排名本身**冇**安全欄（安全欄喺 `ensure_verdict`），所以反過嚟：arm = 加上安全欄。佢只對調頭 1／2，
  Gold、Good 結構上唔變，改報首選上名率、首選頭馬率（賽日配對 bootstrap 2000）。

## 判決

v3 `evaluate_full_record`（2026-08-05 起乾淨窗）。X1–X4 為一個 family，Holm。

- 拎走之後 **WIN**（primary CI 下界 > 0 而 Holm 後仍顯著）→ 建議剷走（交 Kelvin）。
- 拎走之後 Gold、Good 點估計**都負** → 判為「有幫助」，保留。
- 其他 → 「量唔到」，按現狀保留（§6：細改動喺呢個樣本量通常分唔出）。
- X5：首選上名率差異 CI 判斷。

## 保留之後點顯示

保留嘅項目喺 dashboard 同報告逐匹顯示貢獻（綜合分 = 七維 + 各 overlay），令總分可以由畫面加返出嚟。
「變成評分一部分」只做**逐位元等價**嘅重組（排名唔變），唔借機改數；任何改數都要另開實驗。
