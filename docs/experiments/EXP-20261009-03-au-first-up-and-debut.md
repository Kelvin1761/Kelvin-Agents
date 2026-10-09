# EXP-20261009-03 休後長休馬舊績打折 ／ 初出馬用試閘分（預先登記 → REJECT）

- **日期**：2026-10-09
- **平台**：AU
- **假設**：
  - **H1**：休後第一仗、休息 ≥180 日嘅馬，休息前嘅近績／表現質素／PF 對今場預測力弱，模型高估佢哋。
  - **H2**：初出馬冇往績 → 近績類 leaf 中性 60，模型排佢哋太後；試閘分係佢哋唯一嘅能力證據。
- **搜索過嘅舊記錄**：EXP-20261009-01（發現）、記憶 `au-layoff-signal-discarded`（休息日數連續懲罰失敗：
  Gold 33→25）、`au-trial-score-is-accurate-but-unheard`、`au-reallocating-dimension-shares-fails`
- **改到嘅檔案／組件**：冇（只係 scorer 層 leaf 改寫，喺 dump 上量）

## ⚠️ 數據紀律（寫喺量之前）

H1／H2 係喺 **2026-09-09 → 10-08** 嘅數據度諗出嚟。`au_eval.date_partitions` 嘅 terminal
（2026-09-19 → 10-08）**完全喺呢個窗口入面**，所以佢唔可以做判決用 holdout。

- **判決語料**：`date < 2026-09-09`（發現窗口之前），全部以 EXP-20261009-02 修正後引擎重評分。
- **切法**：判決語料按日期切 5 個連續 fold（每 fold 日期數相若）；另報 clean point-in-time 子集
  （2026-08-05 → 09-08）。
- **發現窗口**（09-09 → 10-08）只報告、**唔參與判決**。

## 臂（固定，唔再調）

| 臂 | 對象 | 改寫 |
|---|---|---|
| H1a | `prep_stage == first_up` 且 `days_since_last ≥ 180` | `form_score`、`performance_quality_score`、`pace_figure_score` → 60 + 0.5·(x − 60) |
| H1b | 同上 | 三個 leaf → 60（完全中性） |
| H2a | `prep_stage == debut` | `form_score` := `trial_score` |
| H2b | 同上 | `form_score`、`performance_quality_score` := `trial_score` |

## 判決規則（預先寫定）

一個臂要**全部**滿足先算「值得 forward shadow」：
1. 判決語料 Gold 同 Good位 配對差 ≥ 0，而且其中一個 95% CI 下限 > 0，**或者** Top5 AUC CI 下限 > 0
   同時 Gold／Good 冇負；
2. 5 個 fold 入面 Gold+Good 合計差 ≥ 0 嘅 fold ≥ 4；
3. 預先聲明 cohort（馬群 ×4、首選 SP ×5）冇一格 CI 全負。

唔滿足 = REJECT。就算過，都只係 forward shadow（因為冇乾淨 terminal），唔直接上線。

## 結果

語料：EXP-20261009-02 修正後引擎全語料重評分（`au_dump_engine_leaves.py`，加咗 `career_starts`／
`prep_stage`／`days_since_last` 三個分層欄）。配對 bootstrap 按場、2,000 次、seed 7。

### 判決語料（date < 2026-09-09，2,087 場）
| 臂 | 受影響場 | Gold | Good位 | Top5 AUC | fold ≥0 | 判 |
|---|---:|---|---|---|---|---|
| H1a | 617 | −0.19pp [−0.53, +0.14] | +0.05pp [−0.43, +0.48] | +0.00070 [−0.00056, +0.00203] | 4/5 | ❌ Gold < 0 |
| H1b | 617 | −0.24pp [−0.82, +0.29] | −0.14pp [−0.72, +0.43] | +0.00082 [−0.00129, +0.00305] | 3/5 | ❌ |
| H2a | 367 | −0.14pp [−0.72, +0.38] | **+0.58pp [+0.05, +1.10]** | −0.00076 [−0.00285, +0.00125] | 5/5 | ❌ Gold < 0 |
| H2b | 367 | −0.38pp [−1.10, +0.29] | +0.05pp [−0.72, +0.77] | −0.00268 [−0.00551, +0.00024] | 3/5 | ❌ |

### clean point-in-time 子集（08-05 → 09-08，1,285 場）
H1a Gold −0.23；H1b Gold −0.54；H2a Gold +0.16 / Good +0.31 / AUC5 −0.00176（2/5 fold）；
H2b AUC5 −0.00377 [−0.00750, −0.00038]（顯著差）。

### 發現窗口（09-09 → 10-08，1,177 場）—— **唔參與判決**
H1a Gold +0.42pp [+0.08, +0.85]、H1b Gold +0.68pp [+0.00, +1.44]、H2a Gold +0.68 / Good +0.42（CI 跨零）。

## 檢查
- **leakage-audit**：PASS —— `prep_stage`／`days_since_last`／`career_starts`／`trial_score` 全部由賽前賽績表計。
- **golden_scoring**：冇郁（冇改 code）
- **退步**：H2b clean PIT AUC5 顯著負

## 結論
四個臂全部 REJECT。**H1 係教科書式嘅發現窗口幻覺**：喺諗出佢嗰段數據 Gold +0.42pp（CI 唔跨零），
喺之前 2,087 場就係負。春季大量長休馬復出，個效應好可能係季節／馬群組成，唔係「舊績失效」嘅
穩定機制 —— 同 `au-layoff-signal-discarded` 嘅結論一致。

H2a 喺 Good 有顯著正（+0.58pp、5/5 fold），但 Gold 點估計負，照預先規則 REJECT，**唔救**。
如果要再試，只可以用 2026-10-09 之後嘅 forward 數據重新登記一個新實驗，唔可以喺今次數據改門檻。

**決定**：REJECT（四臂）
**commit**：只記錄，冇 model code

## 重跑
```bash
PYTHONDONTWRITEBYTECODE=1 python3 au_dump_engine_leaves.py --out fixed_leaves.json
python3 h12.py <scripts dir> fixed_leaves.json   # scorer 層 leaf 改寫，見本文「臂」
```
