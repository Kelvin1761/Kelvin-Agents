# AU Wong Choi — Verified Signal Map (2026-08-09)

> 用途：日後升級/重建時知道邊啲嘢真係影響排名、邊啲純顯示、邊啲係死碼。
> 呢張地圖由 `tests/test_signal_map.py` 鎖定 — ability 方程有任何隱藏改動
> 都會令測試爆，逼令呢份文檔同步更新。

## 排名方程（唯一真相）

```
ability_score = Σ MATRIX_WEIGHTS[d] × mx[d]   (六個排名維度；form_line 只顯示)
              + wet_form_feature(今日場地, 地狀分拆線)
排序 = ability_score 降序；同分先按馬號穩定排序
```

## 特徵分類（分離度 = 2026-07-17 修復後審計）

### A. 直接影響矩陣排名（10 個 + 1 overlay）

| 維度（權重） | 輸入特徵（內部權重） | 分離度 |
|---|---|---|
| stability (0.32920) | form 0.60 / performance_quality 0.40 | 完整 margin＋prize＋starters 有數據先啟動；否則逐匹沿用 consistency |
| pace_perf (0.10559；顯示：速度考驗背景) | L600 benchmark/context 0.941744 / trial 0.058256 | Racenet 係逐駒 benchmark；Sportsbet 係 race-level context；sectional 已退出排名 |
| jockey_trainer (0.22957) | jockey 0.333333 / trainer 0.285714 / fit 0.380952 | 現役三葉 |
| race_shape (0.13485) | pace_map 1.0（檔位 bias＋收縮） | 現役單葉 |
| class_weight (0.12042) | rating 0.70；class／weight 只作 context | official rating 主軸 |
| track (0.08037) | track_score 1.0 | 現役單葉 |
| overlay | wet_form_feature（只喺濕地非零） | Heavy +4 g2 / Soft −3 gp |

`performance_quality` = 近四場可比較正式賽嘅 recency-weighted
`-min(20, beaten_margin) + 4 × log10(prize / 50000)`，再做場內 z-score。
最少兩場完整 run、全場最少三匹有完整數據先啟動；同日／未來 run 一律截斷。
詳細驗證見 `15_performance_quality_matrix_upgrade_20260809.md`。

### A2. 顯示尺度（2026-08-01）—— 每個 leaf 嘅 60 必須真係中性

排名只食**場內相對差異**，所以一個 leaf 嘅基準點放喺邊，數學上唔影響排名；
但報告用 `score_band()` 把 60 當中性、55 以下當 ❌ 去畫。基準點同顯示尺唔對齊
嘅 leaf，就會出現「分數睇落係噪音／永遠一樣」嘅假象。710 場實測校正兩個：

| leaf | 舊尺 | 問題 | 新尺 |
|---|---|---|---|
| `pace_map_score`（檔位形勢） | 46.3–**59.75** | 60 係天花板：14.4% 卡上限、**0.0%** 高過 60、32.3% 落 ❌ 帶 →「檔位著數」判語從來出唔到 | 50.6–64.05（base 60） |
| `sectional_score`（段速分） | **35.8**–88.9 | 純加分累加器，「冇 PI 數據」同「PI 顯示冇後勁」同樣停喺 base 35.8（38.1% 嘅馬）→ 讀成 ❌❌。但「冇數據」嗰 1,391 匹 top-3 率 30.1%，*高過*樣本平均 | 60–100（base 60，各項 ×0.7539） |

`pace_map` 係純常數平移 → 710 場 11 個指標、dev/holdout/5 folds **完全相同**。
`sectional` 係 affine 重標定 → gold 37→39、t3prec +0.14、mrr +0.11，無指標實質倒退。

守則：**新 leaf 一律以 60 = 「冇證據／中性」建構**；缺數據唔可以用低分表達，
缺數據由 `feature_evidence_state` + `data_coverage` 負責講（由
`test_signal_map.py::test_neutral_scored_missing_feature_is_still_reported_missing` 鎖住）。

### A2b. 維度顯示尺正規化（2026-08-01）—— 每個維度都要到得 100

Leaf 校準完之後，**維度層**仲有同一個病。七個維度嘅原生 spread 差幾倍，但報告用
同一套 band 畫（85 ✅✅ / 70 ✅ / 55 ➖ / 40 ❌）：

| 維度 | 正規化前 | 可到 band | 正規化後 |
|---|---|---|---|
| stability | 41.6–100.0 (SD 9.96) | 四個都到 | 42.1–99.0 (SD 9.71) |
| pace_perf | 15.8– 98.1 (SD 9.14) | 五個都到 | 14.7–99.0 (SD 9.37) |
| **race_shape** | 50.6– 64.0 (SD 2.67) | **只有 ➖ 同 ❌** | 21.2–76.7 (SD 11.00) |
| **jockey_trainer** | 41.2– 75.6 (SD 3.96) | ➖ 98%／✅ 2% | 13.0–99.0 (SD 9.88) |
| **class_weight** | 50.9– 69.5 (SD 4.00) | **✅ 到唔到** | 35.0–86.0 (SD 11.00) |
| track | 42.9– 85.7 (SD 5.88) | ✅✅ 幾乎到唔到 | 34.1–99.0 (SD 8.93) |

即係六個計分維度有三個，隻馬幾好都**永遠出唔到正面 band**。

`mx' = clip(60 + (mx − 60) × gain)`，gain = min(11.0 / 實測SD, 令實測極值留喺 1..99
之內嘅最大值)。headroom 那一半好緊要 —— 實測正規化後 **0 / 52,710** 個維度值撞
clip（撞 clip 會製造假平手）。

**三樣嘢必須一齊改，唔可以只改一樣：**

1. `MATRIX_DISPLAY_GAINS`（matrix_mapper）
2. `MATRIX_WEIGHTS`（scoring）＝ 舊權重 ÷ gain，歸一化到 Σ = 1
3. `WET_FORM_FEATURE_SCALE` / `WET_FORM_MAX_ABS` ×k —— 濕地 overlay 直接加落
   ability 分，唔經矩陣，唔跟住放大就會靜靜雞縮水

因為排名只食 `weight × gain × deviation`，(1)+(2) 令每個維度嘅有效影響力比率都係
**同一個常數 k = 1.4225**（逐個一模一樣，唔係「差唔多」）→ 排名不變。實測（710 場，
同一 engine state 只 toggle 正規化）：

- 只做 (1)+(2)：71 場排名有變，**其中 70 場係濕地** ← overlay 縮水
- 加上 (3)：**704/710 逐匹一致，9 個指標全部 delta 0.00**（剩低 6 場係
  `matrix_scores` 2dp 四捨五入被 gain 放大，唔影響任何指標）

由 `test_neutral_display_scale.py::TestDimensionScaleAndWeightsStayInLockstep` 鎖住。

順帶：正規化之後七個維度 spread 拉平，所以 `MATRIX_WEIGHTS` **第一次真正等於影響力
佔比**。舊組唔係 —— 實測 `race_shape` 名義佔 15.1% 權重但只出 4.9% 影響力
（ratio 0.32），`jockey_horse_fit` 0.54，`trainer` 0.67；而 `stability` 名義 29.9%
實際出 48%。報告嘅「權重」欄以前係報大數。

敘事門檻亦同步統一（`MATRIX_ADVANTAGE_CUTOFF` 72 / `MATRIX_DISADVANTAGE_CUTOFF` 48），
唔再逐維度磨 magic number —— 舊 `jockey_trainer >= 72`（舊上限 73.8）同
`class_weight >= 68`（舊上限 69.5）實際上幾乎永遠 fire 唔到。

⚠️ gain 係由 archive 分佈推出嚟嘅常數，所以**任何改動 leaf 分佈嘅改動都要重新推導**
（已經因為 jockey/trainer leaf 改動而重推過一次）。

### A2c. 矩陣重 fit（2026-08-01 做完，未 ship）

正規化令 `MATRIX_WEIGHTS` 變成真影響力之後，就可以老實地問「影響力應該點分」。
離線重 fit（ability 對 leaf 分數係線性，所以一次 scoring 就可以評估任意權重；
`refit.py verify` 證實 replica 同 engine 逐匹一致，max|Δ| 0.004）：

- 3,000 個隨機權重向量，dev 575 場選、5 folds 閘、terminal holdout 135 場唔碰
- 1,450 個贏 dev，777 個同時過 4/5 folds
- **唔取 argmax**（777 個裡面揀最高 = 教科書式 overfit），取所有過閘候選嘅
  **逐維度中位數**做 consensus —— 一個冇睇過 holdout 就定咗嘅配置

consensus = stability .3387 / pace_perf .2185 / race_shape .0981 /
jockey_trainer .1647 / class_weight .0500 / track .1300（配 PF backfill ON）

| | dev (575) | holdout (135) |
|---|---|---|
| gold | +3 | +1 |
| good_positional | +1.04 | +0.74 |
| pass_any1 | +2.09 | +0.74 |
| champion | +1.39 | +0.74 |
| winner_in_top3 | +2.78 | +1.48 |
| top3_precision | +1.22 | +0.74 |
| mrr | +1.58 | +0.91 |
| competitive_recall@5 | +1.40 | +0.70 |
| ndcg@5 | +2.42 | +2.02 |

folds 5/5，**holdout 冇一個指標倒退**。對比 argmax 候選（cand2–8）—— 全部喺 holdout
輸 `pass_any1` 3–5pp，gold 平或負。中位數穩定過 argmax，正如預期。

**為何未 ship：** 呢個 fit 最大嘅動作係 `jockey_trainer` 影響力升 ~3×，而
`jockey_score` / `trainer_score` 兩個 leaf 喺同一日被另一份 in-flight 改動
（「統一上名率」，仍未 commit）改到 mean 63.1→59.0 / 64.7→57.8、SD 6.5→8.4 /
5.2→8.4。喺一個正在被人重寫嘅 leaf 上面 fit 一個 3× 加權，就係用壞數據 fit。
等 jockey/trainer 定案 → 重推 gain → 重跑 `refit.py refit` → 再決定。

### A3. PF 覆蓋（2026-08-01 量化，未解鎖）

`AU_PF_Historical_Backfill_Cache_2026-07-13.json`（82 場會期 / 728 場 / 7,738 匹 /
23,830 段紀錄，pre-race-only、leakage 0）本來**冇任何程式讀過**。現已接通
（`engine_core.backfill_pf_metrics`）但**預設 OFF**，用 `WC_PF_BACKFILL=1` 開。

開之後 PF 覆蓋 32.8% → 94.3%，而回填數據本身係有預測力（2026-05 前會期
within-race AUC 0.572，vs 現場 Formguide 會期 0.599 —— 兩者都高過除
近績/穩定以外任何 leaf）。但**現行權重下開咗反而變差**：
gold 37→34、champ −1.55、t3prec −0.94、mrr −0.93、ndcg −0.83。
pace_perf 矩陣權重掃描（0.06/0.09/0.12/0.15/0.24/0.30 vs 現行 0.18831）救唔返，
最好嗰檔 0.15 都係 gold −1；連「段速表現只用 PF」都唔得（gold =、good_pos −1.27）。

判讀：0.18831 係喺呢個 leaf 有 2/3 runner 係啞嘅情況下擬合出嚟嘅。要解鎖呢個
覆蓋，需要**喺全覆蓋條件下重新 fit 成個矩陣**，唔係揀個 coverage flag 就算。

`class_score` 仍會生成，亦保留作 class/form、class/JT context mismatch
interaction 同報告解釋；但 2026-07-29 用 710 場嚴格對齊 archive 做單項
neutral ablation 後，停止再直接放入 `class_weight` 矩陣。結果：

- development 575 場：competitive recall@5 +0.19pp、NDCG@5 +0.20pp、
  winner top-5 +0.35pp、zero-hit −0.17pp
- 5/5 連續時間窗 NDCG 非負，winner top-5 無一窗倒退
- terminal holdout 135 場：competitive recall@5 +0.19pp，其餘主閘持平
- SP≥31 outsider top-3 capture@5 持平

矩陣計法係 `60 + Σ(weight × (leaf − 60))`；當內部權重總和為 1 時同舊
weighted average 代數完全相同，亦容許退役 leaf 回到真正中性而唔移動分數尺度。

`weight_score`（負磅分）2026-08-01 同樣退出排名。710 場實測：**84.9% 嘅馬恰好
60 分**、41.5% 嘅場次全場零分散（即完全冇 gradient）、within-race AUC **0.480**
（低過隨機 0.5）、top-3 gap −0.14。2026-07-24 已經正確判定「負磅嘅能力訊號早已
由 rating 承擔」而將佢中性化，但當時保留咗 0.141 權重 —— 即保留咗一個純噪音項
嘅投票權。移除後 11 個指標全部 = 或 ±0.14（＝1 場，噪音級），PF off / PF on
兩個 footing 各驗一次皆然。負磅仍然係報告內容（頂磅標記、爛地孭重磅、降班配
輕磅），只係唔再入排名。

**但負磅唔係冇用 —— 係用錯地方。** 27.4% 嘅 runner 冇官方讓磅分（處女／未評分
賽事），`_rating_score` 原本純用級數分做代理。喺呢個子集，負磅同 rating 完全
唔重複（rating 根本唔存在），而讓磅賽由能力定磅 → 場內負磅 z-score 就係讓磅官
自己嘅能力排名。2,230 對 within-race pair 實測：

| fallback 代理 | AUC |
|---|---|
| 級數分單獨（舊） | 0.5787 |
| 場內負磅單獨 | 0.5769 |
| **兩者 50/50 混合** | **0.6078** |

α 0.3–0.7 全部 ≈0.607（闊平台，唔係尖峰）→ 採用 0.5。實現見
`_handicap_weight_proxy`：只喺讓磅賽生效（WFA／定磅賽負磅由年齡性別決定，
冇能力訊號，直接拒用），場內負磅標準差 < 0.3kg 亦拒用（讓磅官根本冇分開過）。

### A4. Career identity 同 research population（2026-08-09）

Sportsbet Racecard 嘅 career 格式係 `Career: 45 : 5-7-7`。Facts parser 曾經只截到
`45`，而 Logic parser 又要求數字後面即刻有冒號，令 947 runners 被錯標 DEBUT；
945 匹其實已有正式賽績。現時 Racecard 會保留完整 record，而 Facts／builder／
runtime 都接受完整同 integer-only legacy 格式。呢個 correctness fix 對 805 場
Gold／Good／Pass 等場數指標全部 0.00pp；唔列作 performance gain。

所有 Sportsbet research tools 必須經 `sb_backfill_archive.scored_meeting_index()`
讀 scored meetings；直接 `root / meeting_name` 會漏晒 `Archive/`。Mutable career
overview（J/H、WinRange、Ave $、1st/2nd/3rd-up outcome record）唔可以用 post-race
archive 驗證預測力；候選能力訊號只准由 target date 之前嘅 run rows 重建。

### B. 純顯示層（改咗唔影響排名 — 剪嘅時候要保留報告內容）

- `health_score`（分離度 0.10）、`confidence_score`（0.22）、`distance_score`（0.60）
- `formline_score` + form_line 維度（權重 0.0 — 計出嚟乘零）
- 各種敘事 notes / detail lines / grades 文字

### C. 已知死碼／凍結

- `_pace_bias_adjustment`：預設 OFF（WC_PACE_BIAS=1 先開），A/B 證實 wash
- form_line 維度喺 ability 內係乘零 — 未來 rebuild 可以直接攞走
  （連鎖：MATRIX_KEYS、cache schema、報告七維顯示要一齊改，屬專項 SIP）

## 剪裁守則（2026-07-17 訂）

1. B 類可以簡化實現，但報告輸出要 byte-diff 驗證
2. A 類任何改動行標準晉升閘（+1.5pp / 非倒退 / 4/5 folds）
3. 剪 C 類要有 rank-identity 證明（全庫 A/B max diff < 0.01）
4. 每次剪完更新呢份地圖 + `test_signal_map.py`
