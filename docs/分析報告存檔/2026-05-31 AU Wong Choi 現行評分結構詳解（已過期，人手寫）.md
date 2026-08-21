# AU Wong Choi 現行評分結構詳解（港式中文）

最後更新：`2026-05-31`  
對照 live code：

- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/scoring.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/matrix_mapper.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/rank_adjustments.py`

## 1. 先講結論

你問「6D rating matrix」，但 live engine 其實已經係 **7D matrix**，唔再係舊 6D：

1. `stability`
2. `sectional`
3. `race_shape`
4. `jockey_trainer`
5. `class_weight`
6. `track`
7. `form_line`

即係：

- 舊式「級數」同「負磅」而家合併成 `class_weight`
- `form_line` 而家係獨立第七維，唔再只係附屬參考

另外，feature layer 共有 `16` 個 key，但真正有獨立 scorer 嘅只有 `15` 個；`health_score` 目前 **冇獨立 scoring function**，會自動落返中性 `60` 分。

---

## 2. 現行評分流水線

現行 AU Wong Choi Auto 流程可以理解為 6 層：

1. **Feature scores**
   - 逐項計 `form_score`、`trial_score`、`sectional_score` 等
2. **Feature-level mild corrections**
   - 一啲細幅收回 / interaction，未入 matrix 前先改 feature
3. **7D matrix mapping**
   - 用固定配方將 feature 合成 7 個 matrix 分
4. **Dynamic matrix weighting**
   - 按場地 / field size / race class 改 matrix 權重，計出 `ability_score`
5. **Ability-level adjustments**
   - balanced horse bonus
   - venue barrier bias
6. **Rank-level adjustments**
   - `place_tightening_bonus`
   - `_micro_rank_bonus()`
   - sample-size cap
   - overrated shield
   - market-free adjustment
   - spell / first-up / trial heuristic

對應 live code：

- feature scoring 主入口：`engine_core.py:321-345`
- pre-matrix corrections：`engine_core.py:352-410`
- ability score：`engine_core.py:412-434`
- place tightening：`engine_core.py:467-478`
- micro rank bonus：`engine_core.py:3360-3418`

---

## 3. Feature Layer：目前有咩分，點樣計

## 3.1 Feature key 清單

`scoring.py:6`

```python
FEATURE_KEYS = (
  "form_score","trial_score","sectional_score","pace_map_score",
  "jockey_score","trainer_score","jockey_horse_fit_score",
  "class_score","rating_score","weight_score","distance_score",
  "track_score","formline_score","consistency_score",
  "health_score","confidence_score"
)
```

## 3.2 每項 feature 現行計法

| Feature | 作用 | 現行主要計法 | 重要數值 / 門檻 |
|---|---|---|---|
| `form_score` | 近績實戰表現 | 最近 4 仗名次分，乘時間 decay，再乘班次對照 multiplier | 頭馬 `100`、亞 `85`、季 `75`、四五 `60`、其餘 `40`；decay `1.0/0.8/0.6/0.4`；班次 multiplier `1.2/1.1/1.0/0.85/0.7` |
| `trial_score` | 試閘質量 | 前三次 trial placing + 初出 / maiden / 試閘速度 / 試閘影片訊號 | base `56`；每次前三 `+9`；初出 `+4`；maiden 初出再 `+2` |
| `sectional_score` | 段速 / L400 PI / L600 peak | base + PI 累積 + L600 相對 track-distance 標準 + 趨勢 + realization / forgiveness | base `35.8`；PI extreme `+28.1`；PI excellent `+20`；L600 extreme `+15.07` |
| `pace_map_score` | 檔位 / draw bias | 唔係真正 pace model，主要係 barrier bucket + empirical draw bias matrix | base `55.7`；modifier cap `+4.05 / -9.43` |
| `jockey_score` | 騎師質素 | 大場 (`field>=13`) 用 named ratings；否則 name-token fallback | elite bonus `+9.0`；solid bonus `+5.77` |
| `trainer_score` | 馬房質素 | 大場用 named ratings；否則 name-token fallback + 場館 track stats | elite bonus `+10.59`；Waller debut `+5.52` |
| `jockey_horse_fit_score` | 人馬配搭 / 騎練場館組合 / 換騎訊號 | 係整條 AU engine 入面最複雜嘅一條，綜合正式合作、trial continuity、best jockey、combo stats、stage stats | base `60`；高密度 combo bonus `+7.27`；latest downgrade `-4.11` |
| `class_score` | 級數承受力 | 生涯場數、處女馬老積、升降班、metro/provincial 轉級、latest RT | `career15_maiden_pen -6.79`；`metro_prov_pen -5.48`；`rt_high_bonus +3.58` |
| `rating_score` | 官方 rating 相對場內 | 同場平均 / stdev / top3 cutoff 相對比較 | z-score * `6.0`，cap `±12`；top3 cutoff `+1.5 / -1.0` |
| `weight_score` | 負磅壓力 | 定磅賽 neutral；handicap 睇輕磅 / 重磅 / 爛地重磅 / 升降班配磅 | base `62`；<=`54.5kg` → `68`；>=`60kg` → `56` |
| `distance_score` | 今場路程適配 | `engine_line`、`target_distance_line`、同程 / 近程上名、L400 趨勢 | 已證明今場射程 `78`；半投射 `55`；未證明 `50` |
| `track_score` | 場館 / going 適性 | 同場、同 going、wet verification、血統濕地訊號 | base `62.9`；same-track place bonus、wet penalties |
| `formline_score` | 對手質量 / 後續賽績 | 先判 signal，再加 future wins / stronger opp / higher class follow-up | elite base `82.5`；strong `66.4`；unknown `64.8` |
| `consistency_score` | 跑法穩定 / 近績穩定 | recent places/poor、forgiveness、run_style repeat、PI 穩定、repeatability | base `64.6`；recent place bonus `+7.86`；poor pen `-2.7` |
| `confidence_score` | 資料覆蓋 / 錨點密度 | 數 14 個 anchors，再加 style/source/jockey history/warnings 校正 | 起點 `30 + anchors*4`；唔係「贏面信心」 |
| `health_score` | 健康 / 狀態完整度 | **目前無 scorer，預設 60** | 只係中性 placeholder |

### 3.2.1 `form_score`

來源：`engine_core.py:498-568`

- 最近 4 仗逐場計分
- 先按 placing 給 raw points
- 再按 recency 做 decay
- 再按今日班次 vs 該仗班次做 multiplier
- 如果係 maiden，會用 trial density 補少量分

即係 `form_score` 其實唔係「最近名次平均」，而係：

`placing quality × 時間衰減 × 今日班次對照`

### 3.2.2 `trial_score`

來源：`engine_core.py:571-636`

重點：

- 前三次 trial 入前三會逐次加分
- 初出、maiden 會額外放大
- 會食 `timing_trial_600m_avg_speed`
- 亦會食 `trial_video_signals`

所以 `trial_score` 其實唔只係 placing，而係：

`placing + speed + trial comments + debut context`

### 3.2.3 `sectional_score`

來源：`engine_core.py:638-768`

呢條線係偏「硬能力」：

- 平均 PI
- 最佳 L600 相對 track-distance 標準
- trend up / trend down
- PI 有冇轉化為前列成績
- 如果有高 PI 但遇阻，可以吃 forgiveness bonus

最重要基礎常數喺 `scoring.py:39-54`：

- base `35.8`
- `pi_extreme_bonus = 28.1`
- `pi_excellent_bonus = 20.0`
- `l600_extreme_bonus = 15.07`
- `realization_bonus = 6.64`
- `forgiveness_bonus = 9.89`

### 3.2.4 `pace_map_score`

來源：`engine_core.py:769-840`

呢條線名叫 pace map，但現時實質上：

- 主體係 **檔位 bucket**
- 再疊 **場地 / 路程 / field-size draw bias matrix**
- 唔係直接食 `predicted_pace / pace_confidence`

所以如果你問「live AU Wong Choi 係咪已經將 pace prediction 當主 scoring」，答案係：

- **未係**
- 依家仍然主要係 `barrier + draw bias`

### 3.2.5 `jockey_score` / `trainer_score`

來源：

- `engine_core.py:873-900`
- `engine_core.py:902-940`
- `rank_adjustments.py:6-9`

重點：

- 只係 **大場 (`field>=13`)** 才會用 named jockey/trainer ratings database
- 中小場通常仍然係 token/fallback heuristics

即係 live system 並唔係所有場都 fully 使用 AU_Jockey_Ratings / AU_Trainer_Ratings。

### 3.2.6 `jockey_horse_fit_score`

來源：`engine_core.py:942-1078`

呢條線包含：

- current formal rides / places / wins
- current trial rides / top3
- best historical jockey
- latest official jockey 比較
- current venue combo stats
- trainer track stats
- jockey change signal
- fresh / second-up / third-up stage stats
- apprentice relief

呢條線係 `jockey_trainer` matrix 最重要成份，因為 matrix 入面佔比最高係：

- `jockey_horse_fit_score × 0.52`

### 3.2.7 `class_score`

來源：`engine_core.py:2930-2994`

呢條線主要睇：

- career start density
- 處女馬跑到老仍未贏
- 升降班
- provincial → metro 轉級
- latest RT

注意：

- `class_up_pen` 常數而家係 `0.0`
- 即係「升班」有 note，但呢個 micro constant 本身 **冇實際扣分**

### 3.2.8 `rating_score`

來源：`engine_core.py:2996-3050`

本質係 **relative score**：

- 同場有幾多 rating 樣本
- 高唔高過場均
- 高幾多個標準差
- 有冇過 top3 cutoff

BM / maiden 會再 temper。

### 3.2.9 `weight_score`

來源：`engine_core.py:3056-3093`

負磅唔係線性計：

- WFA / SW 直接唔當 handicap 壓力
- 輕磅有優勢
- 爛地下重磅會再扣
- 升降班同負磅有 interaction

### 3.2.10 `distance_score`

來源：`engine_core.py:3095-3144`

呢條線偏 deterministic：

- `今場 ✅` / `← 今場 ❌`
- 同程上名
- ±100m 近程上名
- L400 趨勢支唔支持增程

### 3.2.11 `track_score`

來源：`engine_core.py:3146-3204`

主體：

- same-track
- same-going
- heavy / wet verified
- 濕地血統 proxy

注意：

- `track` matrix 會再食 `health_score`
- 但 `health_score` 本身而家冇 scorer，所以實際上 `track` matrix 裏面有 `18%` 係固定中性值 `60`

### 3.2.12 `formline_score`

來源：`engine_core.py:3235-3276`

先按 signal 定 base：

- `elite`
- `strong`
- `medium_strong`
- `medium`
- `medium_weak`
- `weak`
- `neutral`
- `unknown`

再加：

- future winners
- strong opponents
- higher/same/lower class follow-up
- headwinner

### 3.2.13 `consistency_score`

來源：`engine_core.py:3278-3314`

主要唔係名次平均，而係：

- 最近 6 仗有幾多前三
- 有幾多場大敗
- 大敗有冇寬恕理由
- 近期 run style 係咪一致
- PI trend 是否穩定
- repeatability 有冇形成

### 3.2.14 `confidence_score`

來源：`engine_core.py:3316-3358`

呢條線好重要，因為佢好容易被誤會。

佢實際上係：

- 數 `14` 個 anchors
- 基礎 `30 + anchors * 4`
- 再按
  - career starts
  - style confidence
  - speed map source
  - formline rows
  - jockey history
  - latest L600 brief
  - warnings
  - unresolved forgiveness
  做微調

所以 `confidence_score` 本質係：

- **資料覆蓋 / 可解釋性分**
- **唔係贏面分**

### 3.2.15 `health_score`

現況：

- `FEATURE_KEYS` 有呢個欄
- 但 `analyze_horse()` 冇調用 `_health_score()`
- codebase 亦冇對應 scorer

所以 live engine 目前係：

- `health_score = 60`
- `provenance = "missing_neutral"`

來源：`engine_core.py:325-350`

---

## 4. Matrix 前：已經有幾個 feature-level 修正

來源：`engine_core.py:352-410`

## 4.1 Mild context mismatch penalties

1. 如果 `form_score >= 72`，但 `class_score < 60`
   - `form_score -4`
2. 如果 `consistency_score >= 72`，但 `track_score < 60`
   - `consistency_score -4`
3. 如果 `jockey_horse_fit_score >= 72`，但 `class_score < 58`
   - `jockey_horse_fit_score -3`

呢三個都係「soft signal 過熱，要收一收」。

## 4.2 Class move × formline interaction

同一段 code 仲會對 `formline_score` 做互動修正：

- `大幅降班 + 強 formline`：`+4`
- `大幅降班 + 中等 formline`：`+3`
- `大幅降班 + 弱 formline`：`+1`
- `降班 + 強 formline`：`+3`
- `降班 + 中等 formline`：`+1`
- `持續升班 + 弱 formline`：`-2`
- `升班 + 弱 formline`：`-2`

即係 `formline_score` 喺入 matrix 前，已經食咗一輪「級數背景再詮釋」。

---

## 5. 現行 7D Matrix：每一格點樣合成

來源：`matrix_mapper.py:6-38`

| Matrix 維度 | 組成 | 內部權重 |
|---|---|---:|
| `stability` | `form_score` | `0.60` |
|  | `consistency_score` | `0.40` |
| `sectional` | `sectional_score` | `0.62` |
|  | `distance_score` | `0.23` |
|  | `trial_score` | `0.15` |
| `race_shape` | `pace_map_score` | `0.70` |
|  | `track_score` | `0.30` |
| `jockey_trainer` | `jockey_score` | `0.28` |
|  | `trainer_score` | `0.20` |
|  | `jockey_horse_fit_score` | `0.52` |
| `class_weight` | `class_score` | `0.45` |
|  | `rating_score` | `0.15` |
|  | `weight_score` | `0.40` |
| `track` | `track_score` | `0.82` |
|  | `health_score` | `0.18` |
| `form_line` | `formline_score` | `0.78` |
|  | `form_score` | `0.22` |

### 幾個值得注意嘅結構特徵

1. `jockey_trainer` 其實唔係純騎師 + 純練馬師
   - 最重係 `jockey_horse_fit_score (52%)`
2. `race_shape` 依家七成係 `pace_map_score`
   - 但 `pace_map_score` 本身仲偏 draw bias
3. `track` matrix 有 `18%` 係 `health_score`
   - 但 `health_score` 目前固定 `60`
4. `form_line` 唔係純 formline
   - 仲會用 `form_score` 做 `22%` 補底

---

## 6. Matrix 權重：Ability Score 係點樣出

## 6.1 基礎 7D 權重

來源：`scoring.py:8-10`

| Matrix 維度 | 基礎權重 |
|---|---:|
| `stability` | `0.280` |
| `sectional` | `0.130` |
| `race_shape` | `0.210` |
| `jockey_trainer` | `0.170` |
| `class_weight` | `0.030` |
| `track` | `0.120` |
| `form_line` | `0.060` |

即係 baseline 下：

- 第一大權重係 `stability`
- 第二係 `race_shape`
- 第三係 `jockey_trainer`
- `class_weight` 只佔 `3%`

## 6.2 Dynamic weights：會按咩改

來源：`scoring.py:144-178`

### A. Field size

- `field >= 13`
  - `race_shape -0.02`
  - `sectional -0.01`
  - `stability +0.02`
  - `form_line +0.01`
- `field 9-12`
  - `race_shape -0.01`
  - `sectional -0.005`
  - `stability +0.01`
  - `form_line +0.005`
- `field <= 8`
  - `race_shape +0.04`
  - `sectional +0.03`
  - `stability -0.02`
  - `form_line -0.02`

### B. Going

- `Soft/Heavy`
  - `race_shape -0.005`
  - `track +0.01`
  - `stability -0.005`
- `Good/Firm`
  - code 寫咗：
    - `weights["speed_performance"] += 0.03`
    - `sectional +0.02`
    - `track -0.02`

### C. Race class

- `BM58/BM64/BM68/BM70`
  - `stability +0.03`
  - `jockey_trainer +0.02`
  - `class_weight -0.02`
- 其他 BM（如 BM72+）
  - `class_weight +0.005`

### D. Floor / Ceiling

- `stability` floor：`0.10`
- `class_weight` ceiling：`0.15`
- `track` ceiling：`0.17`

## 6.3 幾個實際 scenario 權重例子

我直接用 live `get_dynamic_matrix_weights()` 跑咗幾個 case：

| 情景 | stability | sectional | race_shape | jockey_trainer | class_weight | track | form_line |
|---|---:|---:|---:|---:|---:|---:|---:|
| `field 10 / 無特別條件` | 0.2900 | 0.1250 | 0.2000 | 0.1700 | 0.0300 | 0.1200 | 0.0650 |
| `field <=8` | 0.2524 | 0.1553 | 0.2427 | 0.1650 | 0.0291 | 0.1165 | 0.0388 |
| `field 13+` | 0.3000 | 0.1200 | 0.1900 | 0.1700 | 0.0300 | 0.1200 | 0.0700 |
| `Soft 5 / field 10 / BM70` | 0.3058 | 0.1214 | 0.1893 | 0.1845 | 0.0097 | 0.1262 | 0.0631 |
| `Soft 7 / field 14 / BM70` | 0.3155 | 0.1165 | 0.1796 | 0.1845 | 0.0097 | 0.1262 | 0.0680 |

### 解讀

- 小場會加重 `race_shape + sectional`
- 大場會加重 `stability + form_line`
- 濕地 BM70 類型會進一步：
  - 壓低 `class_weight`
  - 提高 `stability`
  - 提高 `jockey_trainer`
  - 少量提高 `track`

---

## 7. Ability Score：7D 合成後仲會加咩

來源：`engine_core.py:420-434`

## 7.1 Ability 計法

```text
ability_score
= Σ(matrix_score × dynamic_weight)
+ balanced horse bonus
+ barrier bias
```

## 7.2 Balanced horse bonus

- 如果 7D 入面最差嗰格都 `>= 56`
  - `ability_score +2.0`

呢個設計偏向獎勵「冇明顯短板」。

## 7.3 Venue barrier bias

來源：

- `engine_core.py:2558-2573`
- `engine_core.py:4594-4614`

目前只內置兩個 venue：

- `Flemington`
- `Randwick`

而且：

- `field >= 13` 會將 bias `×1.5`

### 現行內置 barrier bias（節錄）

#### Flemington

- `B4 +2.5`
- `B5 +2.0`
- `B6 +3.0`
- `B8 -1.5`
- `B17 -2.0`

#### Randwick

- `B3 +3.0`
- `B4 +3.0`
- `B10 -2.5`
- `B12 -3.0`
- `B14-16 -3.5`

---

## 8. Grade：Ability Score 去邊個 grade

來源：`scoring.py:182-194`

| Ability Score | Grade |
|---|---|
| `96+` | `S+` |
| `92-95.99` | `S` |
| `88-91.99` | `S-` |
| `84-87.99` | `A+` |
| `80-83.99` | `A` |
| `76-79.99` | `A-` |
| `72-75.99` | `B+` |
| `68-71.99` | `B` |
| `64-67.99` | `B-` |
| `60-63.99` | `C+` |
| `56-59.99` | `C` |
| `52-55.99` | `C-` |
| `48-51.99` | `D` |
| `<48` | `E` |

---

## 9. Rank Score：Ability 之後仲有兩大層

`rank_score = ability_score + place_tightening_bonus + micro_rank_bonus`

來源：`engine_core.py:432-434`

## 9.1 Place tightening bonus

來源：

- `scoring.py:180-182`
- `engine_core.py:467-478`

公式：

```text
bonus
= 0.103 × (form_score - 60)
+ 0.179 × (trial_score - 60)
+ 0.204 × (trainer_score - 60)
+ 0.170 × (jockey_horse_fit_score - 60)
+ 0.143 × (consistency_score - 60)
- 0.033 × (distance_score - 60)
+ 0.027 × (confidence_score - 60)
- 0.141 × (weight_score - 60)
+ 0.050 × (sectional_score - 60)

之後再 × 1.4
最後 cap 於 ±4.0
```

### 解讀

呢層最偏向：

- `trainer_score`
- `jockey_horse_fit_score`
- `trial_score`
- `consistency_score`

而唔係偏向：

- `distance_score`
- `weight_score`

因為後兩者係負系數。

## 9.2 Micro rank bonus

來源：`engine_core.py:3360-3418`

先做一層細 bonus / penalty：

- 內檔 `<=4`：`+0.35`
- 外檔 `>=12`：`-0.35`
- 內中檔配前置 / 跟前：`+0.20`
- 外檔配後上：`-0.20`
- `jockey_trainer >=75` 且 `jockey_horse_fit >=72`：`+0.25`
- forgiveness count `>=2` 且 stability `>=66`：`+0.20`
- 濕地已驗證：`+0.15`
- formline 有 higher follow-up：`+0.20`
- confidence `<=50`：`-0.20`

但真正影響更大嘅其實係下面幾個子模組。

---

## 10. Rank-level 子模組

## 10.1 JT sample-size rank cap

來源：`rank_adjustments.py:12-43`

如果 `jockey_trainer >= 70`，但樣本好薄：

- current formal rides = 0
- current trial rides = 0
- combo runs < 5
- trainer runs < 10
- best rides = 0 且 latest official rides = 0

會按 weak_count 扣：

- `-3.2`
- `-2.0`
- `-1.0`

即係防止人馬配合分數太好睇，但其實證據極薄。

## 10.2 Narrow overrated shield

來源：`rank_adjustments.py:46-76`

只會喺：

- 非濕地
- field `>=8`

才啟動。

如果：

- `stability` 高
- `form_line` 高
- 但 `race_shape / track / class_weight` 低
- `sectional` 又唔夠硬

會扣：

- `-1.4`
- 或 `-0.8`
- 極端情況再多 `-0.4`

目的就係擋住「紙面好靚，但硬 context 好弱」。

## 10.3 Market-free rank adjustment

來源：`rank_adjustments.py:79-185`

呢層係一個 centered linear model：

- 先將每個 matrix score 轉做 `(score - 60) / 10`
- 再按 field/going/class 做 interaction
- 最後出一個 delta，cap `±3.5`

主係數如下：

| 變數 | 系數 |
|---|---:|
| `stability` | `-0.35` |
| `sectional` | `-0.33` |
| `race_shape` | `-0.19` |
| `jockey_trainer` | `+0.31` |
| `class_weight` | `+0.06` |
| `track` | `-0.64` |
| `form_line` | `-0.77` |
| `field13_sectional` | `+0.48` |
| `field13_form_line` | `+1.01` |
| `field912_stability` | `-0.74` |
| `bm_class_weight` | `-0.97` |
| `wet_track` | `-1.12` |
| `empty_form_trap` | `+0.54` |
| `class_exposed` | `+0.49` |

### 解讀

呢個模型唔係直覺型。

例如：

- `form_line` 原值越高，呢層反而傾向 **扣**
- `track` 高分，呢層亦傾向 **扣**
- 大場 (`Field 13+`) 時，`form_line` 同 `sectional` 又會加返

所以呢層比較似「historical anti-overfit / rank-shaping」而唔係常識式加減。

## 10.4 Spell / trial heuristic

來源：`engine_core.py:3395-3418`

- `spell 14-28`：`+0.4`
- `spell 29-45`：`+0.2`
- `spell > 90`
  - strong trial margin：`+0.4`
  - weak trial margin：`-0.6`
  - 冇 trial：`-0.4`

呢層偏向 fresh / fitness cycle 微調。

---

## 11. 如果你想用舊 6D 思路去理解，點對應

如果你腦內仍然用舊 6D，可以咁對照：

| 你心中舊 6D | 現行 live 對應 |
|---|---|
| 近況 / 穩定 | `stability` |
| 段速 / 引擎 | `sectional` |
| 檔位 / 形勢 | `race_shape` |
| 騎師 / 練馬師 | `jockey_trainer` |
| 級數 / 負磅 | `class_weight` |
| 場地適性 | `track` |
| 額外新增 | `form_line` |

所以最主要變化係：

- **由 6D 變 7D**
- `form_line` 被拉高成獨立主維度

---

## 12. 我認為你而家最值得特別留意嘅幾個 live 結構點

## 12.1 `confidence_score` 其實唔係贏面，而係 coverage

呢個你之前直覺已經捉得啱。

依家 code 睇落，`confidence_score` 根本係：

- 資料齊唔齊
- 錨點夠唔夠
- style/source/history 有冇

所以如果佢被 downstream 當成「可靠熱門」訊號太重，就容易出現高估。

## 12.2 `pace_map_score` 仲未真食 pace model

matrix 名叫 `race_shape`，但主成份 `pace_map_score` 實質仍偏：

- barrier
- draw bias

唔係真正：

- `predicted_pace`
- `pace_confidence`
- horse style fit

## 12.3 `class_weight` 只得 3%

即使 matrix 入面有 `class_score + rating_score + weight_score`，但 baseline 只佔 `3%`。

所以如果你覺得 model 有時對 class / distance / weight 唔夠敏感，呢個結構本身已經係其中一個原因。

## 12.4 `track` matrix 有 18% 係固定中性值

因為 `health_score` 冇 scorer：

- `track = 0.82 * track_score + 0.18 * 60`

即係 `track` matrix 有一截其實係固定 padding。

---

## 13. 目前值得你直接警惕嘅 live 實作風險

呢部分唔係我主觀建議，而係我直接對住 live code 見到嘅現況。

## 13.1 Good/Firm dynamic weight 分支有實作 bug

來源：`scoring.py:157-160`

當 `going` 係 `Good/Firm` 時，程式會做：

```python
weights["speed_performance"] += 0.03
```

但目前根本冇 `speed_performance` 呢個 matrix key。

我直接用 live function 驗過：

- `Soft 5` 可正常返回
- `Good 4` 會 `KeyError: 'speed_performance'`

即係呢段係一個真 bug。

## 13.2 `health_score` 係 placeholder

呢個唔係 crash bug，但係架構空洞：

- matrix 仍然食佢
- 但佢其實固定 `60`

## 13.3 `class_up_pen = 0.0`

來源：`scoring.py:12-25`

`class_score` 寫咗升班分支，但 live constant 係：

- `class_up_pen: 0.0`

即係升班 note 會出，但實質常數冇扣。

## 13.4 `heavy_place_bonus = -2.88`

來源：`scoring.py:56-73`

code 註解語意係：

- 重地有 place record，應該係正面

但 live constant 係負數：

- `heavy_place_bonus = -2.88`

即係現行可能出現：

- note 話「具備重地作戰能力」
- 但分數實際係被扣

## 13.5 `best_formal_mult = -0.06`

來源：`scoring.py:115-142`

喺 `jockey_horse_fit_score` 裏面，如果今場沿用歷來最佳正式配搭，會乘呢個值。

但 live constant 係負：

- `best_formal_mult = -0.06`

即係理論上「沿用最佳正式配搭」未必真係加分，甚至可能輕微倒扣。

---

## 14. 最後總結：而家 live engine 真正偏重啲乜

如果要一句話總結現行 AU Wong Choi：

- **Feature 層最複雜**：`sectional`、`jockey_horse_fit`、`track`、`formline`
- **Matrix 層最重**：`stability`、`race_shape`、`jockey_trainer`
- **Class/Weight 結構性偏輕**：baseline 只 `3%`
- **Rank 層暗盤最大**：
  - `place_tightening`
  - `market_free_rank_adjustment`
  - sample-size cap
  - narrow overrated shield

如果你用 model behavior 去反推 code，最值得記住係：

1. `confidence_score` 係 coverage，不係 win confidence
2. `pace_map_score` 依家仲偏 draw bias，不係真 pace fit
3. `jockey_trainer` 其實最重係 `jockey_horse_fit`
4. `class_weight` 喺總分入面比你直覺更輕
5. `rank_score` 唔係單純 `ability_score`，後面仲有幾層 shape / anti-overfit 微調
