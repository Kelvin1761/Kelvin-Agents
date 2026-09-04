# EXP-20260904-03 HKJC 顯示尺封頂 + 級數優勢反轉 —— 顯示層上線，評分層全 REJECT

- **日期**：2026-09-04
- **平台**：HKJC
- **提出人**：Kelvin —— 「嘉應高昇（歷史馬王）只得 75.1？就算排第一，個分都唔太
  make sense。如果一匹馬最高分係 75，即係話冇馬可以好過嘉應高昇，呢個都唔太合理。」
- **假設**：兩條
  1. 個分讀落唔對，係因為**加權平均嘅上限**，唔係因為模型唔識呢匹馬。
  2. `class_advantage`（級數優勢）反轉 —— 官方評分刻意唔入分，但讓磅（負磅）入分
     兩次，所以「讓磅官話呢匹好」被讀成負面。
- **搜索過嘅舊記錄**：`EXP-20260902-03`（七維 refit REJECT，回放前視）、
  `EXP-20260902-08`、`EXP-20260902-10`。memory `au-dimension-scale-weight-lockstep`、
  `au-neutral-display-scale-fix`、`au-display-gains-no-longer-normalise`、
  `au-handicapper-undercompensates`、`au-cohort-gap-is-not-a-gain`、
  `au-gate-cannot-judge-11-of-14-leaves`、`hkjc-race-shape-weight-lost-in-merge`。
- **Baseline**：`pit_backtest.py`，26 個場次 / **193 場**（corpus_paths 枚舉，09-06 冇賽果所以剔除）
  `gold 6.74 good 24.87 min 45.08 single 81.87 champion 25.91 top3_champ 56.48`
  ⚠️ `EXP-20260902-03` 已記錄呢個 harness 有回放前視。下面所有數字只當**同一把尺嘅
  A/B 參考**，唔當絕對準確度。

---

## 一：個天花板係算得出嘅（假設 1 成立）

`ability_score` 係七個維度嘅**加權平均**，所以永遠困喺各維度自己嘅範圍之內。
實測 3,438 個 runner / 274 場（27 個場次）：

```
min 49.99 | p10 57.39 | 中位 63.16 | p90 68.85 | p99 73.44 | max 76.59 | SD 4.393
27 個場次     >=76(A-): 4 匹     >=80(A): 0 匹
```

`GRADE_THRESHOLDS` 由 A(80) 一路到 S+(96) **六級數學上到唔到**。原因唔係「冇好馬」：

| 維度 | 權重 | 觀測範圍 | 上限貢獻 / 潛在 |
|---|---:|---|---|
| race_shape | 27.4% | 48.8 – **73.8** | 20.21 / 27.37 |
| trainer_signal | 23.6% | 53.1 – 76.7 | 18.13 / 23.62 |
| class_advantage | 14.3% | 52.8 – **65.0** | 9.28 / 14.28 |
| sectional | 12.9% | 33.6 – 85.5 | 10.98 / 12.85 |
| stability | 9.8% | 39.5 – 85.6 | 8.42 / 9.83 |
| form_line | 8.0% | 60.0 – 96.0 | 7.69 / 8.01 |
| horse_health | 4.0% | 58.9 – 73.7 | 2.98 / 4.04 |

一隻同時攞齊七個維度當日最高值嘅（唔存在嘅）馬 = **77.68 分**。兩個最重維度
（合共 41.7% 權重）自己封頂喺 74 同 65，永久由每匹馬扣走約 12 分。

## 二：級數優勢真係反轉（假設 2 成立）

2026-09-06 沙田第 3 場，嘉應高昇官方評分 **142**、全場次高 109、最低 86，
近 6 仗 1-1-1-1-1-1 全部一／二級賽。佢個 `class_advantage` = **60.0，全場 6 匹排第 6**；
86 分嘅魔術控制攞 64.0。純算術：`0.75 × class_score + 0.25 × weight_score`，而
`class_score` 全日 120 匹嘅範圍只有 52.5–62.0（**嘉應高昇已經攞咗全日最高嗰個 62**），
所以場內唯一有變化嘅輸入係負磅 —— 而佢係倒扣。

全日十場，最高評分嗰匹有 **8 場喺自己場次嘅級數優勢排下半，3 場排最後**
（R1 14/14、R2 11/11、R3 6/6、R5 11/14、R7 7/9、R8 12/14、R9 10/11、R10 8/13）。

場內相關（186 場全覆蓋）：

```
ρ(官方評分, weight_score)  = -0.868   ← weight leaf 幾乎係評分嘅完美倒數
ρ(官方評分, jockey_score)  = +0.174
ρ(官方評分, form_score)    = +0.160
ρ(官方評分, class_score)   = -0.014   ← 「班次分」同班次無關
ρ(官方評分, ability_score) = +0.136
```

負磅方向本身量得清楚（results DB，18,828 runner / 1,527 場，**同場比較**）：

| 場內負磅偏離 | n | 上名率 | 勝率 | 平均名次 |
|---|---:|---:|---:|---:|
| ≤ −8 lb | 1,204 | 21.8% | 7.3% | 7.27 |
| −8 ~ −4 | 3,367 | 22.5% | 7.1% | 7.06 |
| −4 ~ −1.5 | 2,984 | 21.6% | 6.9% | 7.28 |
| −1.5 ~ +1.5 | 4,115 | 22.3% | 7.2% | 7.09 |
| +1.5 ~ +4 | 2,666 | 26.5% | 9.1% | 6.73 |
| +4 ~ +8 | 3,062 | 28.6% | 10.0% | 6.51 |
| ≥ +8 lb | 1,430 | **29.5%** | **10.5%** | 6.51 |

單調。場內 Spearman ρ(負磅, 名次) = **−0.0852，CI [−0.1010, −0.0693]**，
不跨零，方向係「負得越重跑得越好」。而引擎畀最輕 70 分、最重 54 分，
再喺 `class_advantage`(25%) 同 `horse_health`(38.9%) 各扣一次
= 全分 **5.14% 全部針對最好嗰匹馬**。

## 三：判決 —— 評分層 12 個候選全部 REJECT

負磅／班次族（193 場，同一 harness、同一先驗）：

| arm | gold | good | min | single | champ | top3_champ |
|---|---:|---:|---:|---:|---:|---:|
| W0 baseline | **6.74** | **24.87** | 45.08 | 81.87 | 25.91 | 56.48 |
| W1 剔走 class_advantage 嘅負磅（去 double-count） | 5.18 | 22.80 | 45.60 | 82.38 | 25.91 | 57.51 |
| W2 負磅中性化 | 5.18 | 21.76 | 48.19 | 82.90 | 25.91 | 58.03 |
| W3 負磅方向調轉 | 6.22 | 26.42 | 46.63 | 81.87 | 26.42 | 56.99 |
| W4 = W1 + W3 | 4.66 | 22.80 | 47.67 | 82.38 | 26.42 | 57.51 |

級數族（`current_rating` 場內相對值混入 `class_score`，覆蓋 **92.8%**）：

| arm | gold | good |
|---|---:|---:|
| R1 rating 25%（百分位） | 5.70 | 21.24 |
| R2 rating 50%（百分位） | 6.22 | 21.24 |
| R3 rating 100%（百分位） | 5.70 | 19.17 |
| R4 rating 50%（線性 k=1.0） | 6.22 | 20.21 |
| R5 rating 50%（線性 k=0.6） | 6.74 | 20.21 |
| R6 = R2 + 去 double-count | 6.22 | 21.24 |
| R7 = R2 + 負磅調轉 | 5.18 | 22.28 |
| R8 = R3 + 去 double-count | 3.63 | 18.65 |

**九個級數 arm 冇一個 `good` 贏過 baseline**（最好 22.28 vs 24.87）。

W3 係唯一 `good` 升嘅候選（+1.55pp）。用場內 AUC + **逐場配對 bootstrap**
（4,000 次；193 場 binary 指標一個 1.55pp = 三場，冇 power）：

```
W0 baseline        場內 AUC = 0.6991
W2 負磅中性化       ΔAUC +0.0003  CI [-0.0038, +0.0046]  (73/193 場有變)
W3 負磅方向調轉     ΔAUC +0.0027  CI [-0.0030, +0.0088]  (97/193 場有變)
```

兩個都跨零。**判 REJECT（W1/W2/W4/R1–R8）同 NEEDS MORE TESTING（W3）。**

理由同 `au-cohort-gap-is-not-a-gain` 一樣：cohort 梯度真、方向企得住，但
**模型已經由另一條路捉到班次**（jockey +0.174、form +0.160 都同評分正相關），
再加一次就係重複計。W1 特別值得記 —— 「去 double-count」呢個聽落最乾淨嘅修法
`gold` `good` 兩個 primary 都跌，因為剔走負磅之後 `class_advantage` 場內
再冇任何變化（class_score 全場範圍 9.5 分），14.3% 權重直接變死。

**所以評分層一行都冇改。** 呢個係第 6 次「重配／加訊號落矩陣」喺 HKJC/AU 過唔到閘。

### 重測條件

193 場係硬上限（只有 26 個場次有 Logic + 賽果）。W3 要判得到，需要
**≥400 場**（估計 MDE 約 ±0.006 AUC）。到 2026-11 左右夠料就重跑
`ab_auc.py` 個配對 bootstrap。唔准喺 193 場上面反覆試唔同 k 去救佢。

---

## 四：上線咗嘅嘢（全部係正確性 + 顯示層）

### 4.1 `days_since_last` 錯咗一整格（正確性）

`inject_hkjc_fact_anchors.compute_stats` 寫 `races[0]['days_since']` 落 Facts
「休後復出」，但賽績檔嗰個 `日數:` 係**該仗同上一仗之間**嘅間隔
（`[1] 26/04/2026 | 日數: 20` = 06/04→26/04 隔 20 日），唔係距今日數。
`health_readout` 同兩行印住「上次出賽：2026年4月26日 / 距今：20日」。

實測 3,438 個 runner **66.5% 個值係錯**。賽季中間錯得細（中位 +3 日，因為連續
出賽嘅馬「上仗前間隔」≈「距今」），季初／休賽後錯得大：2026-09-06 一日中位
**+41 日**，觸發 `days_gt_75_pen` 由 **2 匹變 28 匹**（117 匹之中）。
嘉應高昇 20 → **133**（排位表真值）。

修兩處：生成器改用 `--race-date`（本來已經傳落嚟，只係冇用）；引擎加
`_days_since_last()` 由 `race_analysis.race_date − recent_6_detail 第1仗日期`
自己重算，所以 264 份帶住舊值嘅歷史 Logic 亦自動修正。
順手修埋 `compute_stats` 個季度界線用 `datetime.now()` —— 今日重跑四月嘅場次會
令每匹馬季內成績變零。

`min 45.08 → 45.60`（+1 場），其餘五個指標不變。

### 4.2 `parse_record` 將第四個數當「出賽次數」（正確性）

HKJC 個四元組係 **(冠-亞-季-其餘)**（`compute_stats` 用 `pos = min(finish, 4)`），
所以 `starts` 係四項總和。舊 code 讀成 `(wins, seconds, thirds, starts)`：
一隻同程六戰六勝嘅馬讀 `同程 (6-0-0-0)` → `starts=0`，所以每一個
「呢匹馬同程有冇樣本？」嘅判斷，**恰好喺同程全勝嘅馬身上失敗**。

同時 `_distance_score` 攞 `parse_record(best_distance + season_stats + course_record)`
掃第一個四元組 —— 而 `season_stats` 係「季內 (…) | 同程 (…) | 同場同程 (…)」，
第一個係**季內**。即係路程分一路用緊季內成績做同程證據。

修完：`distance_score` 14.3% 個 runner 有變（374 個跨過 `<58` 個風險閘），
`same_distance_signal_score` 67.6% 有變。嘉應高昇 66（「樣本有限」）→ **72**。
排名指標**零變化**（兩個 leaf 都唔喺 `MATRIX_FORMULAS`，唯一路徑係
`risk_score` × 2.5% 權重）—— wiring 已逐個 leaf 核實過，唔係靜靜 no-op。

### 4.3 「頭馬距離趨勢」符號反轉（報告層）

HKJC 個「頭馬距離」欄對贏馬印**贏出距離**，對敗馬印落後距離。抽取層一律當落後
距離，所以贏得越大越似輸得多：嘉應高昇六戰六勝
（4-1/4→4-1/4→3-1/2→1-1/4→3-3/4→2-3/4）讀成 **📉擴大中 48 分**，
而同場真連敗嘅合夥奔馳（8/3/9/6/14/6）讀 **76 分**。

`scrape_hkjc_horse_profile.compute_margin_trend` 改成帶符號（贏 = 負），新增
`📈連勝中`。但**已經存喺 Logic 嘅字串補唔返**，所以引擎加
`_margin_trend_display()` 由 `recent_6_detail`（有名次又有距離）自己重算、
蓋過舊字串。而家印：`勝4-1/4 → … → 勝2-3/4 → 📈連勝中`。

`margin_trend_score` 2026-07-08 已剔出 7D 計分，所以**唔影響排名**。

### 4.4 顯示尺（顯示層，排名 bit-identical）

`scoring.DISPLAY_SCALE` + `to_display_scale()`：

```
顯示分 = 64.0 + 2.27635 × (原始分 − 63.16)
         anchor = B-「中游」        centre = 實測中位
         target_sd 10.0 / observed_sd 4.393
```

`ability_score` = 顯示分；原始加權和保留喺 `ability_score_raw`。

**排名不變嘅證明**：
- 274 場 / 3,438 匹逐場對排序，display vs raw **0 個唔同**。
- `pit_backtest` 193 場六個指標同 §4.1/§4.2 之後**完全一樣**
  （`gold 13 good 48 min 87 single 158 champ 50 top3 109`）。
- 金樣本 120 匹：**維度加權和 0 匹變**，只有顯示尺變 → 純顯示簽名。

三個一改就會令「純顯示」變成偷改排名嘅位，全部堵咗：
1. **SIP-C 原本 trigger `grade == "B-"`** —— `GRADE_THRESHOLDS` 一改就會觸發
   另一批馬。改用原始尺個窗 `64 ≤ raw < 68`，boost 亦加落原始尺。
   （實測 210 個觸發，6.11% 個 runner。）
2. **排序原本讀 `ability_score`** —— 兩個尺各自 round 2dp 之後，原始差 0.004 嘅
   兩匹馬會撞成同分、跌落馬號 tiebreak（274 場實測有 2 場中招）。排序改讀
   `ability_score_raw`。
3. **金樣本自己重寫咗 ability 公式**（`golden_scoring.score_one`），所以改
   `DISPLAY_SCALE` 佢會照報「全部一致」。已接上 `to_display_scale`，並分開報
   `維度加權和` 同 `綜合戰力分（顯示尺）`。

新增 `validation.py` `SCORE-007`（顯示尺一定要由原始尺換算得返）、
run contract 加 `display_scale`（`SCHEMA-014`）、
`tests/test_display_scale.py` 14 個測試。

### 4.5 結果

2026-09-06 沙田第 3 場：

| 馬 | 舊分 | 舊級 | 新分 | 新級 |
|---|---:|---|---:|---|
| 嘉應高昇 | 75.12 | B+ | **90.93** | **S-** |
| 錶之星河 | 71.45 | B | 82.64 | A |
| 幸運有您 | 69.08 | B | 77.43 | A- |
| 魔術控制 | 66.60 | B- | 71.72 | B |
| 合夥奔馳 | 66.61 | B- | 71.58 | B |
| 好友心得 | 64.54 | B- | 66.87 | B- |

全日 120 匹：`max 90.93 / min 34.38 / SD 4.52 → 10.29`，用到 11 個等級（原本 7 個，
`B+` 只有 1 匹）。嘉應高昇係全季唯一一隻 S-。

**唯一一個排名變動**：合夥奔馳同魔術控制掉位。原本差 **0.01 分**（66.61 vs 66.60），
§4.1／§4.2 嘅正確性修正令佢變 71.58 vs 71.72。呢個係修數據嘅正常後果，唔係顯示尺。

---

## 五：冇修嘅嘢（要記住）

- **`race_shape` 27.4% 仍然係最重維度而 AUC 七維第二弱。** `EXP-20260902-03`
  三個獨立方法都話應該係 0.17–0.23，三次都過唔到閘。嗰份文自己講咗真瓶頸：
  `fit_score` AUC 0.5089、`trip_score` 0.4887，佔沙田組合 45%。**唔好再 refit**，
  要修嘅係嗰兩塊死 leaf。
- **`class_advantage` 呢個名同佢實際量嘅嘢唔符。** 佢主要係「負磅倒數」。
  §3 話咗改唔到（改到嘅全部輸），但個名同 `matrix_reasoning` 個敘述應該老實講
  返佢係讓磅情境，唔好扮班次優勢。**未做。**
- **`class_score` 全日範圍只有 52.5–62.0**，而 `season_place_0_pen` 喺季初對全場
  一齊扣 4 分（場內抵銷）。個 leaf 事實上係「經驗計量表」唔係班次。
- **`pit_backtest` 回放前視未修**（`EXP-20260902-03` 記錄）。本文所有 193 場數字
  受同一個限制。
- **`golden_scoring` / `engine_core` / `au_eval` / `au_matrix_refit` 仍然各自有一份
  ability 公式複本。** 今次就係呢個令金樣本睇唔到顯示尺。

## 六：可重現

```bash
export PYTHONDONTWRITEBYTECODE=1     # macOS .pyc 陷阱，見 AGENTS.md
# baseline / A/B（26 個場次，193 場）
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/pit_backtest.py --json "<meeting dirs>"
# 候選 A/B 同配對 bootstrap（in-process patching，唔改 production 檔）
scratch/hkjc_class_weight_ab_20260904.py
scratch/hkjc_weight_sign_auc_20260904.py
# 上線之後
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform hkjc --record
python3 .agents/skills/shared_racing/scripts/data_contract.py  --platform hkjc --calibrate
./Wong\ Choi\ 模型說明/更新模型說明.sh
```

改到嘅檔案：`hkjc_racing_engine/{scoring,engine_core,renderer,validation}.py`、
`hkjc_auto_orchestrator.py`、`.agents/scripts/{inject_hkjc_fact_anchors,scrape_hkjc_horse_profile}.py`、
`shared_racing/scripts/{golden_scoring,explain_model}.py`、
`tests/{test_display_scale,test_pipeline_integrity}.py`。
