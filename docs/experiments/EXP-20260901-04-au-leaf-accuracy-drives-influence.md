# EXP-20260901-04 改正：矩陣內 leaf 越準越有影響力（ρ +0.61）；失敗嘅係加 leaf 同郁權重

**狀態：診斷（零 code 改動）—— 一個結論撤回、一條改善路線確立**
- **日期**：2026-09-01 ・ **平台**：AU ・ **語料**：1,804 場 / 18,062 匹
- **起因**：Kelvin 質疑「令一個 leaf 量得更準唔會變成排名收益」講唔通，
  尤其係如果**多個** leaf 一齊變準。佢係對嘅。

## 一、我撤回嗰個結論，同點解佢係錯嘅

我由五次實驗歸納出「改善 leaf ≠ 排名收益」。**方法有缺陷**：五次都用
`ability + k·z(leaf)`，而五個都係**零權重** leaf（`pace_map` / `sectional` /
`distance`）。對零權重 leaf 嚟講，改善佢**唔會流入 `ability`**，所以唯一測法就係
加落去 —— 咁樣測嘅係「硬夾一個 leaf 上去」，唔係「用得更好」。

而且我自己同一日就有反證：**`pace_figure` 個體化**（一個**矩陣內**嘅 leaf 量得更準）
係 **PRIMARY_WIN，gold holdout +3.39pp**（見 [[EXP-20260831-13]] 之前嗰輪）。
兩件事我混咗。

## 二、正確測試：9 個計分 leaf 逐個設中性 60

用 repo 標準 swap-leaf 消融（leaf → 60），**零內權重外插**：

| leaf | 維度 | 有效權重 | 場內 SD | 單獨 AUC | 消融跌幅 | terminal |
|---|---|---:|---:|---:|---:|---:|
| performance_quality | stability | 14.1% | 13.20 | **0.6225** | +1.27pp | +2.10pp |
| **form_score** | stability | **21.1%** | 9.45 | 0.6053 | **+0.39pp** | +0.57pp |
| pace_figure | pace_perf | 17.7% | 20.00 | 0.5948 | +1.27pp | +1.71pp |
| jockey | jockey_trainer | 8.2% | 8.04 | 0.5879 | +1.44pp | **+3.24pp** |
| **trainer** | jockey_trainer | **7.0%** | 7.64 | 0.5854 | **+2.11pp** | **+4.00pp** |
| rating | class_weight | 9.0% | 5.70 | 0.5793 | +0.78pp | +1.52pp |
| trial | pace_perf | 1.1% | 8.25 | 0.5576 | −0.06pp | +0.00pp |
| jockey_horse_fit | jockey_trainer | 9.4% | 3.32 | 0.5467 | +0.55pp | +2.10pp |
| track | track | 8.6% | 4.62 | **0.5434** | **−0.67pp** | +0.57pp |

| 相關 | ρ |
|---|---:|
| **單獨 AUC ↔ 消融跌幅** | **+0.6109** |
| 場內 SD ↔ 消融跌幅 | +0.3864 |
| 權重×場內SD ↔ 消融跌幅 | +0.2913 |
| **有效權重 ↔ 消融跌幅** | **+0.1451** |

**準確度比權重更能預測影響力。Kelvin 講得對。**

⚠️ 方法註：第一版用「剷走 leaf + 內權重重新歸一化」，剷 `pace_figure` 會令
`trial` 內權重 ×17.2（離譜外插），令 `pace_figure` 睇落係 −0.28pp。改用設中性 60
之後變 +1.27pp。**測 leaf 價值一定要用 swap-to-neutral。**

## 三、但兩樣嘢仍然失敗，而且原因唔同

### (a) 硬加零權重 leaf —— 用**正確方法**重測都 REJECT

放入矩陣、其他 5 個維度按比例縮細（總權重保持 1）、新維度 display gain 按同一條
規則 `11/raw SD` 計。Harness 驗證：重建基準同存檔 `ability` 嘅 gold **100.00% 一致**。

| 新維度 | raw SD | gain | 最好結果 |
|---|---:|---:|---|
| `race_shape`（檔位修正 + 表 ×3.5 深）| 2.33 | 4.73 | @0.04 gold term **+0.0019**、good **+0.0038**（CI 跨零）|
| `sectional`（PI 覆蓋 47.5%→61.5%）| 10.22 | 1.08 | 全部負 |
| `distance`（中性點 60→48）| 6.44 | 1.71 | 全部負，@0.08 CI [−0.0324,−0.0057] |
| 三個一齊 | | | 全部負 |

`race_shape @ 0.04` 係第一個**兩個 primary 都非負**嘅零權重 leaf，但 CI 跨零 → REJECT。
留意佢 raw SD 只 **2.33** —— `pace_map_score` 本身幾乎冇離散度
（[[au-pace-map-is-a-four-step-ladder]]）。

### (b) 重配權重 —— 第五次失敗，而且係乾淨嘅過擬合簽名

按 **dev** 量到嘅維度消融影響力比例移動（權重只由 dev 導出，terminal 只做確認）：

| dev 消融跌幅 | |
|---|---:|
| jockey_trainer | +3.13pp |
| pace_perf | +1.09pp |
| class_weight | +0.47pp |
| stability | +0.23pp |
| track | **−1.17pp** |

| α（移向 dev 比例嘅幅度）| gold dev | gold terminal |
|---:|---:|---:|
| 0.15 | +0.0047 | −0.0038 |
| 0.30 | −0.0008 | −0.0095 |
| 0.50 | +0.0008 | −0.0210 |
| 1.00 | −0.0164 | **−0.0400** |

**terminal 單調變差** —— 移得越多越差。即係 dev 嘅消融影響力係噪音估計，
**消融影響力 ≠ 最優權重**（相關特徵集入面，邊際貢獻同最優權重係兩件事）。

## 四、改正之後嘅改善路線

**改善模型嘅路 = 令 9 個矩陣內 leaf 更準。** 唔係加 leaf，唔係郁權重。
而上表直接指出邊個最值得做（最唔準而又有實質權重）：

| 目標 | 權重 | AUC | 備註 |
|---|---:|---:|---|
| `track_score` | 8.6% | **0.5434** | 消融跌幅**負**（all −0.67pp）而 terminal 正 —— 方向矛盾，最可疑 |
| `jockey_horse_fit_score` | 9.4% | 0.5467 | 場內 SD 只 3.32；[[au-jockey-trainer-wasted-weight]] 早已指出佢最弱 |
| `rating_score` | 9.0% | 0.5793 | [[au-handicapper-undercompensates]]：raw rating 有料 0.6002 |
| `trial_score` | 1.1% | 0.5576 | 消融 ≈0 —— 幾乎免費，改善空間細 |

⚠️ [[au-feature-set-is-saturated]] **仍然成立**，但要收窄講法：**同一批 leaf 之下，
夾法（權重／新增／組合）已經到頂**。而 leaf 本身嘅**準確度**唔係到頂 ——
`pace_figure` 今日就係一個 +3.39pp 嘅反例。

## 檢查
- **leakage-audit**：重配權重嘅權重**只由 dev 導出**，terminal 只做確認。消融同
  相關分析係描述性，冇候選入模型
- **harness 驗證**：重建 `ability` 誤差最大 7.66e-03（只係 2 位小數捨入），
  重建基準同存檔 ability gold **100.00% 一致**
