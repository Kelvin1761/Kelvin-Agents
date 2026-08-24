# EXP-20260824-04 AU 頭馬勝距／輸距語義修正及 refit

- **日期**：2026-08-24
- **平台**：AU
- **起因**：Randwick R9 將 Sheza Alibi 一仗勝 5.75L 當成輸 5.75L，壓低
  Performance Quality 並誤加 `form_flattered`；Aeliana 因而排 Sheza Alibi 之前。
- **假設 A（correctness）**：`Finished 1/N xL` 嘅 `xL` 係勝距，頭馬 beaten margin
  必須為 0。
- **假設 B（refit）**：修正 Performance Quality 分佈後，用 development-only refit
  matrix 權重可以收回整體排序表現。
- **判決**：**A KEEP（資料語義修正，不聲稱整體表現改善）；B REJECT（holdout 不過閘）**。

## 改動邊界

1. Sportsbet HTML parser：只要 `finish_pos == 1`，輸出 `margin:0L`。
2. archived Formguide 防守：舊檔即使寫住 `margin:5.75L`，只要名次係 1，重建
   Facts／engine digest 都歸零。
3. `finish:N/M` transport 由 Facts 及 engine 讀取，未上名試閘不再結構上等同
   「無試閘」。舊檔本身冇保存 token 就無法追溯恢復。
4. 冇改 Performance Quality 公式、matrix gains、wet overlay 或 live matrix weights。
5. SP／odds 完全冇進入 scoring 或 refit。

## 資料與可重現性

- runtime dataset：`/private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json`
- Sportsbet index：181 meetings，2025-08-02 至 2026-08-21，共 1,508 場索引。
- 實際可解析：174 meetings／1,450 race pages／15,604 runner digests。
- canonical cohort：1,411 場；whole-date development 899、terminal 512。
- 同一 Sportsbet point-in-time history（歷史日期嚴格早過 target date）分別重建：
  - absolute-margin baseline；
  - winner-neutral candidate（唯一改動係頭馬 margin → 0）。
- 1,301 次正數 winning-margin 被歸零；1,244 場通過 field gate；10,811 匹分數有變。
- replica 核對：14,109 匹對 mapper 最大 `|Δ| < 0.004`，`>0.01 = 0`。
- shadow 腳本：`scratch/au_winner_margin_20260824/run_experiment.py`。

## Correctness ablation（現役權重不變）

| 指標 | dev | terminal holdout | 95% CI | 判讀 |
|---|---:|---:|---:|---|
| 頭 5 位配對場內 AUC | -0.00131 | -0.00064 | **[-0.00128,-0.00013]** | 排序微跌 |
| 全場配對 AUC | -0.00030 | -0.00011 | [-0.00075,+0.00044] | 不確定 |

全樣本場數指標：Gold `-0.07pp`、Good位置 `-0.28pp`、Pass `+0.14pp`、
winner@3 `+0.14pp`。terminal：Gold `0.00pp`、Good位置 `-0.39pp`、Pass
`-0.39pp`、winner@3 `0.00pp`。

terminal 馬群分層冇隱藏一致改善：≤8 匹 Pass `-0.64pp`；9–10 匹 Good
`-1.32pp`；11–12 匹主要指標全平；13+ 匹 Pass `-1.23pp`。因此唔可以話呢個
correctness fix 改善整體分析表現。佢仍然 KEEP，原因係欄位契約明文係 beaten margin，
錯誤勝距唔應當作一個隱藏 regularizer。

排名 footprint：175 場任何排序有變、97 場 Top 4 次序有變、37 場 Top 4 成員有變。

## 修正後 dev-only refit

`au_matrix_refit.py --obj place` 用 3,000 組候選，38 組贏 dev，7 組通過 4/5 fold；
在開 holdout 前鎖定共識權重：

```json
{"stability":0.377,"pace_perf":0.13037,"race_shape":0.03588,"jockey_trainer":0.25671,"class_weight":0.13795,"track":0.06208}
```

canonical whole-date gate：

| 指標 | dev | terminal holdout | 95% CI | 判決 |
|---|---:|---:|---:|---|
| 頭 5 位配對場內 AUC | +0.00129 | -0.00248 | **[-0.00617,+0.00122]** | REJECT |
| 全場配對 AUC | +0.00103 | -0.00064 | [-0.00335,+0.00218] | REJECT |

全樣本 Good `+0.64pp`，但 Pass `-0.35pp`；holdout 主 AUC 點估計向下且 CI 跨零。
新權重不落 production，現役 matrix weights 保持不變。

## Randwick R9 凍結重播

用 archived 08-22 Race 9 Racecard／Formguide，修正後 full Python pipeline 重建
Facts、Logic 及 scoring：

| 排名 | 原始 | 修正後 | 實際 |
|---:|---|---|---:|
| 1 | Autumn Glow 86.58 | Autumn Glow 85.90 | 1 |
| 2 | Aeliana 85.01 | **Sheza Alibi 85.03** | 2 |
| 3 | Sheza Alibi 83.68 | **Aeliana 84.38** | 11 |

Sheza Alibi Performance Quality `84.68 → 93.75`，`form_flattered` 消失。Aeliana
trial score 仍係 60，因為 archived Formguide 兩課第 4+ 試閘本身冇保存名次；呢個係
不可逆歷史資料缺口。新 Formguide 已 transport `finish:N/M`，之後第 4+ 會保留。

## REF-DA01 五角度覆盤

### 1. 結果偏差

| 原預測 | 實際 | 偏差 | 修正後 |
|---:|---:|---|---:|
| Autumn Glow 1 | 1 | 0 | 1 |
| Aeliana 2 | 11 | +9 | 3 |
| Sheza Alibi 3 | 2 | -1 | 2 |

修正恢復當場正確 Top 2，但未解決 Aeliana 仍被明顯高估。

### 2. 過程偏差

Sheza Alibi 被壓低係確定性語義錯誤；Aeliana 被托高則係多因子結果：強往績、rating／
class、騎練、wet overlay，加上兩課差試閘缺名次後回中性。兩者唔可以當同一根因。

### 3. SIP-DA01 自我審計

審計改變咗舊決定：唔再因 aggregate 指標微跌而保留語義錯欄；但亦阻止咗將「R9
修好」直接延伸成新權重。correctness fix 同 model promotion 分開裁決係有效嘅。

### 4. 泛化性審計

- 🔵 **系統性資料契約問題**：所有 Sportsbet 頭馬正數 margin 都會受影響，必須修。
- 🔵 **系統性 transport 問題**：第 4+ 試閘名次必須保存；forward 已修，舊檔不可逆。
- 🟡 **模型適配問題**：winner-neutral 分佈可能需要更長 forward window，但今次 refit
  未過 holdout，唔准改權重。

### 5. Design Pattern Proposal

- **Issue ID:** REF-20260824-04
- **分類:** 🔵系統性資料契約
- **問題描述:** 同一個 margin token 對頭馬係勝距、對其他馬係輸距，直接當同一語義會
  污染 ranking leaf 同 risk flag。
- **受影響 Protocol:** Sportsbet extraction、Facts rebuild、Performance Quality。
- **建議修改:** 在最早 parser 及兩個 archived-data consumer 以 finish position 正規化；
  model refit 必須另行過 gate。
- **預期效果:** 移除錯誤 noise、修正個案解釋；不承諾 aggregate 命中率上升。
- **SIP-DA01 評價:** 有效 — 分開 correctness KEEP 與 refit REJECT，避免兩種判決互相綁架。

## 結論

**KEEP winner-margin correctness；REJECT refit。** R9 Top 2 已修正，production matrix
權重不變。未來累積足夠 winner-neutral forward outcomes 後，先再開新 confirmation window。

