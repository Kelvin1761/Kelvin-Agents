# EXP-20261101-37 預先登記：準咗嘅速度分（G）嘅兩個濕地問題 —— 地況配對權重（GW）、唔同 wet overlay 重複計（GWX）

> 量度之前寫。結果另寫 `EXP-20261101-37-au-speed-wet-fixes-results.md`。

- **日期**：2026-11-01；**平台**：AU；**baseline**：production（`dump_shipped.json`，`1c7e1794` 引擎，近期加權已上線）。
- **用戶指示**：「let's fix the 濕地往績過度加分 and 濕地日同 wet overlay 重複計 issue first」。
- **前因**：EXP-20261101-36（in-sample 診斷）：G 推入頭 2 嘅馬 60% 往績喺濕地（被擠走 34%），G 地況修正後速度分 +15.7；
  濕地日冇 wet overlay 時 G 頭 2 換馬 +5.5pp，有 wet overlay −2.1pp。
- ⚠️ **兩個問題只喺用 G 時出現**。現行 production 標準冇地況修正，濕地往績反而被當慢。所以「修正」= 喺 G 上面加配套，
  再同 production 比。
- ⚠️ **方向係喺同一個窗搵出嚟**：全紀錄判決會偏樂觀。任何上線都要加 forward 確認。

## 候選（都建基於 EXP-33 嘅 G 標準，`walk_forward_oos`）

- **GW**：G + 往績聚合時，往績地況同今仗地況唔同（`full_time_speed.condition_key` 類別：firm／good／soft／heavy／synthetic，
  兩邊都已知先比）→ 權重 × 0.5。同 live `full_time_speed.aggregate` 一樣嘅規則同數值，唔係新揀嘅數。
  其餘照現行（近期加權 0.8^k、own = delta + margin × 0.17、場內 z）。
- **GWX**：GW + wet overlay 關掉（`wet_form_feature` = 0）。答「G 已經按地況處理濕地往績之後，wet overlay 仲有冇需要」。

## 判決（同 EXP-31／33）

v3 `walk_forward_oos` 全紀錄（2026-08-05 起）+ §8 四 arm（refit 程序 `f92c8377…`）；Holm：GW、GWX × v3／§8 refit。
上線規則：過閘 → 上；兩個都過 → primary 合計大嗰個；冇過閘 → 交 Kelvin（佢 AU 取捨：Good 點估計 ≥ 0、Gold 跌喺雜訊內）。
另報：乾地日／濕地日分層，頭 2／頭 5 換馬上名率（同 EXP-36 一樣計法）。

## 唔准做

改 0.5、地況類別、加 arm；睇完結果改 wet overlay 幅度（只係開或者關）。
