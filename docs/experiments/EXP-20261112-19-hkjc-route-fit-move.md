# EXP-20261112-19 HKJC「路程配合」±1.5：剷走／搬去同程表現

- **日期**：2026-11-12 ｜ **平台**：HKJC ｜ **觸發**：標籤審計第 6 項；Kelvin「路程配合應唔應該喺同程表現」
- **改到嘅檔案／組件**：`features/speed.py`（唔再加落段速分，記低 `route_fit`）、`engine_core.py`（加落同程表現 leaf）

## 訊號
有往績 97% 一律 +1.5，相對模型 +0.02pp；「未跑過」−1.5 分支語料 0 匹；組件審計 AUC 0.520 → 近乎常數。

## A/B（389 場）
| arm | 郁 | Gold | Good | capture@5 | 頭二選有中 | 判決 |
|---|---|---|---|---|---|---|
| A 剷走 | 41 | 0.00 | −0.26 [−0.78, 0] | −0.17 | +0.26 | REJECT / primary_regression |
| B 搬去同程表現（同樣 leaf 分） | 38 | 0.00 | −0.26 [−0.78, 0] | −0.17 | +0.26 | REJECT / primary_regression |

Good 差 1 場（沙田草地）。

## 決定
Kelvin 2026-11-12：「i prefer 搬, it is cleaner to move to 同程表現」→ **上線 B**（Kelvin 決定；閘門判 REJECT，差 1 場）。
同程表現 leaf = 60 ＋ 調整 ÷ 權重，所以加 1.5 分 = raw 調整 ＋ 1.5 × 同程權重（0.02）。顯示名「今程跑過」。

## 上線版本（連 EXP-18 體重剷走一齊）
production code 回放 389 場同 main 74d8c248 比：55 場郁；Gold 0.00、Good −0.26 [−0.78, 0]、capture@5 −0.17、頭二選有中 +0.26 → 同 arm B 一樣（REJECT / primary_regression，差 1 場）。
