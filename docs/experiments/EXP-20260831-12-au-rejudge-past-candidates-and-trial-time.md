# EXP-20260831-12 用 Stage 4 v2 重判過往候選；試閘時間 vs 名次；ML／refit 重驗

**狀態：全部 REJECT（零 code 改動）**
- **日期**：2026-08-31 ・ **平台**：AU ・ **語料**：1,780 場（有齊賽果嘅）
- **起因**：Kelvin 問（a）新尺會唔會令舊 REJECT 翻案（b）試閘分應唔應該用時間
  而唔係名次（c）新尺之下要唔要 refit／ML

## 一、22 個過往候選重判 —— 冇一個翻案

### 九個未入排名嘅 leaf（`ability + k·z(leaf)`）

| leaf | k=0.6 | k=1.5 |
|---|---|---|
| 段速 | REJECT | REJECT（gold terminal **−2.00pp** CI [−3.79, −0.20]）|
| 班次 | REJECT | REJECT |
| 負重 | REJECT | REJECT |
| 路程 | REJECT | REJECT（gold terminal **−2.00pp** CI [−3.99, −0.20]）|
| 穩定性 | REJECT | REJECT |
| 健康 | REJECT | REJECT |
| 信心 | REJECT | REJECT |
| 檔位形勢 | REJECT | REJECT（gold terminal **−2.79pp** CI [−4.99, −0.80]）|
| 賽績線 | REJECT | REJECT |

### 退役維度復活（加返落矩陣）

| | 權重 0.05 | 權重 0.10 |
|---|---|---|
| `form_line` | REJECT | REJECT（gold terminal **−2.40pp** CI [−4.39, −0.40]）|
| `race_shape` | REJECT | REJECT |

**22/22 REJECT。** 新尺同舊尺結論一致，而且有四個喺新尺之下**更清楚地有害**
（舊尺 CI 跨零，新尺 `gold` terminal CI 全負）。

## 二、ML／refit 喺新尺之下重驗 —— 都係 REJECT

### GBM（`HistGradientBoostingClassifier`，18 個 leaf 場內 z ＋ 馬匹數）

時間切分：訓練只用 dev 日期（< 2026-08-17），terminal 完全唔碰。
訓練樣本 13,063，正例率 29.4%。

| | `gold` dev | `gold` terminal |
|---|---:|---:|
| 純 GBM 排名 | **+10.48pp** | **−2.59pp** |
| 混合 w=0.2 | +2.97pp | −1.20pp |
| 混合 w=0.4 | +4.69pp | −1.60pp |

**教科書級過擬合** —— dev 升 10pp 而 out-of-sample 跌。三個都 `REJECT`
（`primary_regression`）。喺新尺之下確認 `au-feature-set-is-saturated`。

### 矩陣重配權（第四次量）

共識想 `pace_perf` 0.18825 → 0.25762（+37%）。
`gold` dev +0.23pp 但 **terminal −1.00pp** → `REJECT`。

## 三、試閘時間 vs 試閘名次（Kelvin 提）—— 名次贏

`_trial_score` 只食 `_trial_places()`（名次 1/2/3），完全冇用時間。假設合理：
試閘馬群細而且質素隨機，贏三隻慢馬 ≠ 贏八隻好馬。

**數據可用性**（718 條試閘 vs 1,990 條正式）：

| 欄位 | 試閘 | 正式 |
|---|---:|---:|
| 名次／馬匹數 | 100% | 100% |
| 冠軍時間 | **81.9%** | 100% |
| 負距 | 50.7% | 100% |
| L600 | 25.8% | 94.2% |
| 走位（800m/400m）| ~1% | ~97% |

由 cache 建（1,508 場 / 36,197 條試閘往績 / 297 個 (場地,距離) 標準格）：

| | 場內 AUC | 馬匹層覆蓋 |
|---|---:|---:|
| **現行 `trial_score`（名次）** | **0.5571** | 100% |
| A 試閘冠軍時間（場級 z）| 0.5197 | 59.2% |
| B 加本駒負距（個體化 z）| 0.5496 | 43.6% |

Stage 4 v2：四個配置（A/B × k=0.6/1.5）全部 `REJECT`。

**結論：名次贏時間。** 兩個原因 ——
1. **試閘唔會盡全力跑**，時間反映騎師催得幾狼多過馬嘅能力
2. 現行 `trial_score` 唔止係名次：仲有初出馬備戰、新馬賽加碼、最近一課勝出
   等 context，所以佢帶嘅資訊多過「第幾名」

⚠️ 呢個同 `pace_figure` 嘅情況**唔同**。`pace_figure` 個問題係「食一個場級量
去代表個體」；試閘時間本身**就係**一個唔可靠嘅量（唔盡全力），所以個體化
唔會救佢。**唔係所有「用時間代替名次」都係進步。**

## 檢查
- **leakage-audit**：PASS —— 試閘時間嚟自**過往**試閘，抽取層已丟走賽日當日或之後
- **golden / data_contract**：冇郁（零 code 改動）
