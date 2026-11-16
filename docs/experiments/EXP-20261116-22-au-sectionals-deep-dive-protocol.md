# EXP-20261116-22 預先登記：段速深入診斷（正規化、殘差資訊、配權、情境、功效、QLD 大樣本、pace_figure 換真 L600）

> 編號更正：原本以 EXP-20261116-18 登記（commit `17c8d95b`，內容同時間未改），但 main 上 -18 已經俾 HKJC 用咗，改做 -22。

- **日期**：2026-11-16；**平台**：AU；**類型**：診斷 + 一個零擬合參數候選（arm P）。唔改生產模型。
- **起因**：Kelvin 對 EXP-20261116-19 嘅判決：「doesnt makes sense, try to dig deeper, sectional is one of the most important signals」。
- **寫喺量度之前**：以下所有特徵、量度、判決規則喺計任何新結果之前寫好、commit。EXP-19 嘅數字已經睇過（佢係呢個實驗嘅起因），
  所以 EXP-19 嘅五個 arm 唔會再用嚟判決，只會喺第 3 節做「配權」對照。
- **唔抓新數據**：只用已存 370 版手機頁（11-08→11-15）、場次資料夾入面賽前寫好嘅 `Formguide.md`／`Meeting_Auto_Scoring.csv`、
  同 RQ XML（`AU_Racing_Time_Evidence/*.zip`）。03:00 前唔掂 sportsbetform。

## 0. 先答 Kelvin 第 1、3 點（事實，唔使量）

- EXP-19 嘅 E／L／D **唔係**生 km/h：每仗喺 (場地, 路程段) 入面 z-score（標準用 11-06 之前嘅行）。但係**冇**對嗰場往績本身（同場其他馬）、
  地況、班次做正規化 —— 一場慢步速賽事嘅「快 L600」同一場快步速賽事嘅「慢 L600」會撈埋。呢點 Kelvin 講得啱。
- 配權：β walk-forward conditional logistic（β = c/b，夾 ±10），頭 2 日 β = 0。冇手揀權重，但 8 日 fit 出嚟嘅 β 本身好嘈（L：0.92 → −0.66 → 0.11）。
  所以 EXP-19 嘅「L 有害」可能係**配權噪音**，唔一定係訊號有害 —— 第 3、5 節會分開量。
- 引擎已經有嘅：`pace_figure`（`pace_perf`，係數 0.0879／分）= 近期加權（0.8^k）嘅「賽事 L600 − 標準 + 本駒輸距 × 0.17」，場內 z；
  `full_time_speed_feature` overlay（逐駒全程情境速度，gain 1.5）。即係「完成時間」同「估算末段」已經喺模型入面。

## 1. 數據同 join（手機語料，A 部分）

每版手機頁嘅每匹馬每仗，用 (今仗場次資料夾 → 今仗 `Race N Formguide.md` → 馬名 → 往績日期) 對返 Formguide 往績行，攞：
`RaceL600`（場級 L600）、`WinningTime`、`L600 Delta`（場級 L600 − 標準）、`margin`、`cond`、`RaceClass`、`@800m`／`@400m` 位置、`starters`、`finish`。
只用往績日期**嚴格早過**今仗嘅行（Formguide 係賽前寫，照驗：數有幾多行日期 ≥ 今仗）。報 join 率。

`RaceL600` 語義先量（唔睇賽果）：頭馬（finish 1）嘅手機 L600 對 `RaceL600` 差嘅分佈。

## 2. 逐仗特徵（A 部分；全部「越大 = 越好」）

| 名 | 定義 |
|---|---|
| `Lr` 末段（對嗰場） | −(本駒 L600 − 嗰場 `RaceL600`)（秒） |
| `Ls` 末段（對標準＋地況） | −(本駒 L600 − 標準 L600(場地,路程)) − 地況族平均殘差（族 = Good/Firm、Soft、Heavy；平均只用 11-06 之前行） |
| `Er` 前段（對嗰場） | −(本駒去到 600m 時間 − 嗰場頭馬去到 600m 時間)，頭馬去到 600m = `WinningTime − RaceL600`（只喺第 1 節量到 RaceL600 ≈ 頭馬 L600 先用；否則改用「對 RaceL600 參照馬」並照報） |
| `CxP` 收腳×步速 | `Lr` × 嗰場前段步速 z（嗰場 (距離−600)/(WinningTime − RaceL600)，喺 (路程段, 地況族) 入面 z，11-06 前標準） |
| `Lpos` 末段扣位置 | `Lr` 對 `@800m` 位置（馬數正規化 (pos−1)/(starters−1)）做線性殘差（係數用 11-06 前行 fit） |

**聚合三種**（每匹馬）：最近一仗、最近 ≤4 仗平均（主）、最近 3 仗最好。冇值 = NA（唔入嗰個量度），排名合成時 = 場內 0。

**主家族（Holm）**：`Lr`、`Ls`、`Er`、`CxP`、`Lpos` 嘅「≤4 仗平均」共 5 個。其他聚合同分層 = 探索性，只報唔判。

## 3. 量度（A 部分，318 場有賽果）

1. **單獨**：場內 Spearman（特徵 vs 名次，取場平均）、場內 win AUC、place（頭 3）AUC；賽日 bootstrap 2000 CI。
2. **殘差資訊（主判）**：conditional logit（每場 softmax）`place ~ a·base_z + c·signal_z` 同 `win ~ …`，base = `final_rank_score` 場內 z；
   c 嘅 CI 用賽日 bootstrap（每次重 fit）。另報偏 Spearman（喺場內將名次同特徵都對 base 做線性殘差）。
   - **「有資訊」** = place 模型 c 嘅 95% CI 全正，**而且** Holm 後仍然顯著（p 用 bootstrap 雙尾）。
3. **配權**：只用 dev（11-08→11-12）揀 k ∈ {0.25, 0.5, 1, 2, 4}（候選 = base + k·場內 z(特徵)，k 以 base 場內 SD 為單位），
   取 dev Gold／Good 都唔負、dev 頭5 AUC > 0 嘅 k 中位數；冇合格 k → 唔入 test。test（11-13→11-15）報 v3 判決。
   同時報 EXP-19 β 嘅逐日值做對照。
4. **情境（探索性）**：路程 短途 ≤1200／一哩 1201–1700／長途 >1700；今日地況 乾（Good/Firm）／濕；今日班次 Maiden／Class 1–3／BM／Open+。報 n 同 c，唔判。
5. **功效**：用 v3 賽日 bootstrap SE 計 Gold／Good 嘅 80% 功效 MDE（≈ 2.8×SE）；對 L 加一個「固定小 k」嘅敏感度測試，睇「有害」係咪配權造成。

## 4. QLD 大樣本（B 部分，EXP-42 語料重跑擴充）

EXP-42 已經做咗**同場正規化**（本駒 ÷ 嗰場中位 − 1），但冇：地況／班次調整、收腳×步速、位置、最好／最近聚合、對我哋模型嘅殘差。今次加：

- 語料同 EXP-42 一樣（`scratch/au_rq_sectionals_diag_20261101.py` 嘅 parse，目標 2026-01-01 起，train < 07-01、test ≥ 07-01）。
- 新逐仗特徵（同場相對）：`fin`（基準）、`L600`、`early`、`CxP`（L600 相對 × 嗰場前段步速 z）、`Lpos`（L600 相對扣 400m-to-go… 用 RQ `Ranks` 喺 L600 起點嘅名次）、
  `ground`（`DistanceTravelled` 相對場中位，越少越好）。地況調整：每個特徵減 (地況族, 路程段) 平均（train 期 fit）。
- 聚合：近期加權（EXP-42：0.8^k，≤6 仗）、最近一仗、最近 3 仗最好。
- 量度：(i) 單獨 AUC；(ii) 疊加喺 `fin` 上 test 期 log-lik／AUC Δ（同 EXP-42 一樣嘅 conditional logit，train fit）；
  (iii) 有我哋 `final_rank_score`（場次資料夾，只用 2026-08-05 之後乾淨 point-in-time）嘅 QLD 場次，報殘差 c 同 bootstrap CI。
- **判「有資訊」** = (ii) test log-lik CI 全正 **而且** AUC Δ CI 全正（EXP-42 已經見到 log-lik 正而 AUC 跨零／負 = 只改尺度唔改排序，唔算）。

## 5. Arm P：pace_figure 換真 L600（零擬合參數候選）

- 現行：`own_i = l600_delta + margin × 0.17`。候選：有手機分段嗰仗 `own_i = l600_delta + (手機本駒 L600 − RaceL600)`；冇就保持現行估算。
  其餘（0.8^k 近期加權、場內 z、`clip(60 − 20z)`、≥3 匹先用 own）全部唔變，用 `au_racing_engine.speed` 原 code。
- 候選分 = `final_rank_score + 0.08792517 × (pf_new − pf_old)`，pf_old = 同一條 code 用現行估算重算（報同 CSV `pace_figure_score` 嘅重現率；
  重現唔到嘅場次照報、照用重算值做 baseline，兩邊同一條路）。
- 判決：v3 `evaluate_full_record(domain="au", mode="walk_forward_oos")`。8 個賽日 KEEP 幾乎冇可能；REJECT 只限明確有害（同 EXP-19 一樣）；其餘 NEEDS MORE TESTING。
  另報 leaf 層：pf_new vs pf_old 嘅單獨場內 AUC 同配對 bootstrap 差。

## 6. 洩漏

- 手機行同 Formguide 行都只用日期 < 今仗；所有標準／地況平均／位置殘差係數只用 11-06 之前（手機）或 train 期（RQ）。
- RQ：同 EXP-42 一樣只用目標日之前往績；試閘排除。
- `final_rank_score` 只用場次資料夾賽前版本；QLD 殘差只用 2026-08-05 之後。

## 7. 誠實條款

如果正規化之後殘差資訊仍然係零，就照數字講「段速喺我哋現有模型之上冇額外資訊」，唔會換指標或者揀分層去救。
如果有資訊但配權輸，就講「訊號有，配法未搵到」，下一步係 forward 累積，唔係上線。
