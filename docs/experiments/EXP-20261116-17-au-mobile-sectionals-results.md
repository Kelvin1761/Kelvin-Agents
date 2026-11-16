# EXP-20261116-17 結果：sportsbetform 手機版逐駒分段（前段／末段速度）

- **預先登記**：[`EXP-20261116-17-au-mobile-sectionals-protocol.md`](EXP-20261116-17-au-mobile-sectionals-protocol.md)
  （原本編號 -11，commit `e9bf1628`；補充登記 `69e0879d`、`ea22e324`，全部喺睇候選結果之前）。
- ⚠️ **2026-11-16 後續（EXP-20261116-18）**：L 嘅「有害」係配權過大（β 比正確比率大 10–40 倍）造成，唔係訊號有害；對嗰場正規化同扣位置之後，末段速度喺現行模型之上有殘差資訊（Holm p 0.013／0.02）。另外本實驗 harness 嘅 Holm 讀錯欄位（全部 1.0 冇意義）。見 [EXP-20261116-18](EXP-20261116-18-au-sectionals-deep-dive-results.md)。
- **判決**：數據來源 **point-in-time 安全、逐駒、準確**；但五個候選 arm 冇一個贏現行模型。
  - 末段 **L**（本駒 L600 速度）：**REJECT**（明確有害）。
  - 前段可變基準 **E2**：**REJECT**（明確有害）。
  - 前段 **E**、末段減速 **D**、平均速度對照 **A**：**NEEDS MORE TESTING**（CI 跨零，量唔到）。
  - **唔建議**為呢三個 arm 專登每日累積語料（理由見最尾）。
- 生產模型冇改。冇 model code commit，只有實驗腳本同記錄。

## 1. 來源同欄位語義

`https://www.sportsbetform.com.au/mobile/{eventId}/{n}/` 嘅 Speed 分頁（`mobile-sectional-times`）係**成場** server-render，
每場一版就有全部出賽馬最近 ≤10 仗。每仗：名次／馬數、場地、狀況、日期、路程、本駒完成時間、6 格 200m 分段
（`1000m`／`800m`／`600m`／`400m`／`200m`／`Fnsh`，每格有秒數同 km/h）。

- 格名 = 嗰段 200m 嘅**起點離終點距離**：`Fnsh` = 最後 200m，`200m` = 400→200，`400m` = 600→400，
  `600m` = 800→600，`800m` = 1000→800，`1000m` = 1200→1000。起步段從來冇記錄（800m 賽 3 格、1000m 賽 4 格，自洽）。
- **逐駒**：同一場往績見到兩匹馬嘅 204 對，分段全部唔同（相同嘅 33 對全部係空白）；完成時間係本駒時間。
- **準確度**（對 Racing Queensland XML，剔走 RQ 壞值）：同場兩匹馬 L600 差相關 **0.991**、完成時間差 **1.000**；
  L600 絕對值中位差 0.16 秒。Sportsbet 時間係 0.04 秒倍數，分段捨入到 0.1 秒（所以 E2 由 km/h 反推）。
- Sportsbet 自己嘅 EARLY／MID／LATE／AVG 摘要 = 頁面顯示 ≤10 行嘅平均（AVG 同 路程/時間 中位差 0.003），唔係新資訊。

## 2. 覆蓋率（370 版，全部有評分嘅場次）

`coverage.json`：

| | 數量 |
|---|---|
| 版（場） | 370（11 版冇分段表） |
| 出賽馬 | 3,506；有 ≥1 仗往績 3,340（95.3%） |
| 往績行 | 26,215；有 L400／L600 25,046（95.5%）、L800 24,320（92.8%）、L1000 9,917（37.8%） |
| 全空白行 | 1,169（4.5%） |
| 評估入面有特徵嘅馬 | E／L／D 2,875 / 3,038（94.6%） |

按路程：≤1100m 嘅 L1000 幾乎冇（3 行，正常 —— 起步段冇記錄），其他路程 L600 ≈ 95%。

## 3. Point-in-time／洩漏判斷

| 檢查 | 結果 |
|---|---|
| 頁面有冇包今仗或之後嘅仗 | **0 行**（370 版、11-08 至 11-15 賽後先抓，全部冇日期 ≥ 賽日嘅行）→ 舊賽事頁固定喺賽事日期，唔會補入之後嘅仗 |
| 賽前可唔可以攞到 | 可以（11-17 賽事喺 11-16 已經有 Speed 分頁） |
| 試閘有冇混入分段表 | **冇**：1 號馬 long-form 1,757 個試閘日期，喺佢分段行入面 0 個對到 |
| 重複行一致性 | 25,573 個不同往績，只有 1 個唔一致（兩行都係全空白，時間唔同） |
| 賽前版 vs 賽後版同一仗 | **未做**：今晚 21:29 一版逾時即停（照規矩唔重試），22:00–03:00 唔准掂 sportsbetform，所以冇抓 11-17 賽前手機版。上面「0 行 ≥ 賽日」已經直接證明往績表唔會包今仗；未證明嘅只係「舊仗分段會唔會事後修正」（細風險，唔影響結論） |

特徵只用日期**嚴格早過**今仗嘅行；(場地, 路程段) 標準只用 2026-11-06 之前嘅行（25,415 行）。

**結論：冇洩漏。** 可以用作 live 特徵。

## 4. 評估

語料：370 版 → 有賽果嘅 318 場／8 個賽日（11-08 只得 3 場；11-06／11-07 冇抓到；49 版冇賽果，主要係 11-15 Warwick 唔喺結果 CSV）。
v3 判決器 `evaluate_full_record(domain="au", mode="walk_forward_oos")`，賽日 bootstrap 2000；頭 2 個賽日 β = 0，所以 302 場有非零 β。
Baseline（現行 `final_rank_score`）：Gold 21.27%、Good 28.89%（315 場）。

| arm | 單獨 leaf AUC | 同綜合分場內相關 | 同 A 相關 | Gold Δ [95% CI] | Good Δ [95% CI] | 場內 AUC Δ [95% CI] | log-lik Δ／匹 [95% CI] | v3 | 預先登記判決 |
|---|---|---|---|---|---|---|---|---|---|
| E 前段 | 0.5589 | 0.136 | 0.539 | +0.95pp [−2.14, +3.41] | −0.95pp [−4.05, +1.35] | +0.0003 [−0.0107, +0.0102] | −0.0010 [−0.0047, +0.0031] | REJECT（primary_regression） | **NEEDS MORE TESTING** |
| E2 前段可變基準 | 0.5264 | 0.117 | 0.282 | −0.32pp [−1.85, +0.72] | 0.00pp [−1.36, +1.82] | −0.0018 [−0.0036, −0.0004] | −0.0016 [−0.0040, −0.0003] | REJECT | **REJECT**（ranking CI 全負；mean_top3_model_rank +0.017 [+0.005, +0.034] 變差） |
| L 末段 L600 | 0.5814 | 0.341 | 0.646 | −0.95pp [−2.30, −0.20] | −0.63pp [−2.31, +0.74] | −0.0030 [−0.0083, +0.0000] | −0.0008 [−0.0026, +0.0002] | REJECT（primary_regression） | **REJECT**（Gold 點估計負、CI 全負、時間塊唔達標） |
| A 平均速度（對照） | 0.5983 | 0.344 | — | +0.95pp [−1.46, +2.66] | 0.00pp [−4.58, +4.15] | +0.0015 [−0.0132, +0.0127] | −0.0003 [−0.0044, +0.0026] | REJECT（ranking_evidence_too_weak） | NEEDS MORE TESTING |
| D 末段減速 | 0.5557 | 0.266 | 0.132 | 0.00pp [−1.69, +1.59] | +0.95pp [−1.68, +4.14] | −0.0025 [−0.0087, +0.0026] | −0.0023 [−0.0059, +0.0001] | REJECT（ranking_evidence_too_weak） | NEEDS MORE TESTING |

Holm（5 個 arm）：全部調整後 p = 1.0。

walk-forward β（11-08 → 11-15）：
- E：0, 0, 4.40, 5.42, 3.22, 2.30, 1.33, 1.65（穩定正，但隨訓練樣本增加縮細）
- E2：0, 0, −0.92, −0.18, 2.09, 0.84, −0.04, −0.06（正負跳 = 冇穩定訊號）
- L：0, 0, 0.92, 1.47, −0.66, 0.27, 0.14, 0.11（收埋去 ≈ 0）
- A：0, 0, 3.31, 4.32, 1.44, 1.08, 0.80, 1.08
- D：0, 0, −3.83, −3.72, −1.68, −1.05, −0.12, −0.59（負：控制咗綜合分之後「收得好」反而略差）

### 解讀

1. **單獨 leaf 全部輸畀「完成時間」對照 A**（0.5983）：E 0.559、L 0.581、D 0.556。同 EXP-20261101-42（QLD 逐駒 200m 分段）一樣：
   **分段單獨唔贏完成時間**。全國覆蓋冇改變呢個結論。
2. **疊加喺現行綜合分上冇一個有正增益**：場內 AUC Δ 同 log-lik Δ 冇一個 CI 全正。E 嘅 β 穩定正，但 E 同 A 相關 0.54、而 A 本身都係正 β
   —— E 帶住嘅大概係「完成時間」嗰份，唔係前段獨有資訊。現行模型已經有完成時間（頭馬時間＋輸距 → `pace_figure`）。
3. **L 同 E2 明確有害**：L 同綜合分場內相關 0.341，最重複；加落去只係加噪音。E2 嘅前段長度隨有值格數變，標準化之後混咗唔同長度嘅段，β 正負跳。
4. **D 嘅 β 係負**：同 `au-late-fade-is-redundant-with-form` 一致 —— 末段收法嘅訊號已經喺 form 入面，控制之後符號反轉。

## 5. RacecardWithContext 欄位（只審計，冇開臂）

主站 API（`www.sportsbet.com.au/apigw`），`rc_audit.py`。我哋取得：12 場 11-14／11-15 舊賽事（169 匹，全部係賽後先抓），
同 16 場 11-17 賽前快照（199 匹，存咗喺 `EXP-20261116-17-evidence/rc_prerace_20261117.tar.gz`）。

| 欄位 | 結果 | 判斷 |
|---|---|---|
| `recentStartsThoroughbreds`（舊賽事） | 169 匹冇一匹包今仗日期 | 往績清單**唔會**賽後補入今仗 |
| `total`（生涯出賽數） | 同我哋賽前 Racecard `Career: N` 比：117／118 一樣，1 匹少 1 | 生涯統計**冇**賽後更新嘅跡象 |
| `winPercentage`／`placePercentage`／`horseJockey` 等 `N:w,s,t` 統計 | 同 `total` 同一組計數 | 大機會同上一樣安全，但只直接驗咗 `total` |
| `speed`、`dryRating`、`wetRating` | 計法未公開；賽前覆蓋 198–199／199 | **flag：洩漏答唔到**。舊賽事只有賽後版本，未知會唔會賽後重算。要聽日（11-17 賽後）再抓同一批 16 場，同賽前快照逐匹比 |
| `expectedSettlingPosition` | 6 類（Leader／Pace／Off Pace／Midfield／Off Midfield／Backmarker），賽前覆蓋 198／199 | **唔係** Speedmap 嗰個：同我哋 Facts 嘅 `official_settle`（Speedmap 定位序）對，Leader 平均定位序 8.5、Backmarker 8.1、Midfield 6.5 —— 冇單調關係。係另一個來源，價值未知。定位預測呢條線已經有三個 REJECT（`au-sportsbet-speedmap-rejected`、`au-run-style-*`），唔建議再開臂 |

**未做**：`speed`／`rating` 嘅賽前 vs 賽後比較（11-17 賽後先做得，主站 API，冇時間限制）。做之前呢幾個欄位**唔可以當安全**。

## 6. 抓取量同可持續性

- `AllRacing/{day}` 只回溯約 10 日（11-06 得、11-05 之前 400 "Invalid Date"），舊 event ID 我哋冇存 → **歷史語料攞唔返，只可以向前累積**。
- 每場一版、隔 25 秒：平日 ~55 場 ≈ 23 分鐘，星期六 ~100 場 ≈ 42 分鐘；每日 ~14MB。
- 今晚 18:46–21:29 抓咗 370 版，21:29 一版 30 秒逾時（0 bytes）即停，冇重試。

## 7. 要唔要每日累積？

**唔建議為 E／D／A 專登累積。** 理由：
- EXP-42 用 5,413 場 QLD 逐駒分段已經量過同一個問題，加前段 CI 全負、其他 log-lik 微升而場內 AUC 冇一個 CI 全正。
  今次 318 場嘅點估計同佢方向一致（E 接近零、L 負）。要量到 EXP-42 見到嘅 0.0004 nats／上名馬，要幾千場 ≈ 2–3 個月每日抓，
  而先驗話就算量到都細過閘門。
- 每日多 ~25–40 分鐘打 sportsbetform，要同生產 evening job 同 `/form/` 對照錯開。

**值得另開嘅唯一方向**（未測，唔係呢個實驗嘅結論）：用逐駒 L600 **個體化** `pace_figure` 而家食緊嘅場級 L600 欄位
（記憶 `au-pace-figure-consumes-one-race-level-field`：個體化 +0.0598 AUC 但正交性由 0.103 跌到 0.418）。
呢個係改 leaf 公式，唔係加特徵，要另外預先登記。手機頁覆蓋 95% 而且全國，比 RQ 只得 QLD 好。

## 可重現

```bash
W=/Users/imac/wc-worktrees/claude-au-mobile-sectionals-20261116/docs/experiments/patches/au_mobile_sectionals
PYTHONDONTWRITEBYTECODE=1 python3 -I $W/coverage.py <raw/mob> <events.json> <out.json>
PYTHONDONTWRITEBYTECODE=1 python3 -I $W/evaluate.py <raw/mob> <events.json> <outdir>
python3 -I $W/rc_audit.py <rc json 目錄> <events.json>
```

- 手機頁原檔（89MB，370 版）冇入 repo；`events.json`（event ID 對場次）、`coverage.json`、`eval_report.json`、`harvest.log`
  喺 [`EXP-20261116-17-evidence/`](EXP-20261116-17-evidence/)。
- 分支 `claude-au-mobile-sectionals-20261116`；base `final_rank_score` 來自各場次 `Meeting_Auto_Scoring.csv`（live 版），賽果 `AU_Historical_Raw_Race_Results.csv`。
