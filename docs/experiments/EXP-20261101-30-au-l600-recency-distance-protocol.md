# EXP-20261101-30 預先登記：L600 環境分近期加權（R）＋路程相近度加權（P）

> 量度之前寫。結果另寫 `EXP-20261101-30-au-l600-recency-distance-results.md`。

- **日期**：2026-11-01；**平台**：AU；**baseline**：main `5edea8c9`。
- **用戶指示**：「我想試下用 historic races 去 run，想講如果有 Signal 就 implement 然後 keep 住 Monitor」
  （同一對話先問：速度應唔應該好似狀態與穩定性咁按近期加權；唔同路程嘅 L600 有冇標準化好）。
- **搜索過嘅舊記錄**：
  - EXP-20261016-01 D3：leaf 層面衰減 0.8^k Δ AUC **+0.0055 [+0.0015, +0.0095]**，Holm p **0.050**，
    依登記冇入圍；記錄寫明「用戶要求先可以另開登記，用 §8 測」。最近 3／5 場平均係負（−0.0067／−0.0018）。
  - EXP-20261016-01 D2：截短大敗、中位數全部蝕 → 唔再試。F4（秒／馬位隨速度變）冇作用 → 唔再試。
  - EXP-20260823-02：pace_figure 七個修法全 REJECT，冇一個係近期或路程加權。
  - EXP-20260826-01：PF／段速判別力隨距離對調（>1600m）→ 支持「唔同路程嘅 L600 意義唔同」，未試過按路程加權。
  - EXP-20261009-05（WinningTime 速度近期加權）盲測中、未揭盲，同今次唔同量（全程時間 vs L600），唔共用 terminal。
  - memory：`leaf-auc-gains-do-not-convert-to-ranking`、`retest-orthogonality-changes`、
    `au-pace-figure-is-the-only-orthogonal-leaf`。

## 現行（baseline）

```
own_i = l600_delta_i + margin_i × 0.17          （Sportsbet 正式賽 PF 行）
x     = round(mean(own_i), 3)                    每仗一樣重
z     = (x − 場均) / 場內 pstdev                 （場內 ≥3 匹有 own；否則用 race-level l600_delta 同一條路）
PF    = clip(60 − 20z)
```

## 候選（固定值，冇由數據 fit）

只改「逐仗 → 每匹馬」嘅聚合權重 `w_i`：`x = round(Σ w_i·v_i / Σ w_i, 3)`。own 同 race-level fallback 用同一套權重；
場均／場內 SD 用同一個加權後嘅量（全場 Logic 馬匹，同 production 一樣嘅母體）。其餘（0.17、20、≥3 匹、clip、係數）不變。
往績按 `run_date` 由新到舊排，k = 0 係最近一仗。

| arm | `w_i` | 來源 |
|---|---|---|
| **R** 近期加權 | `0.8^k` | EXP-20261016-01 D3c 原值，唔改 |
| **P** 路程相近度 | `exp(−|ln(d_i / d_today)| / 0.25)`；`d_i` 或 `d_today` 缺 → `w_i = 1` | 同 live `full_time_speed.aggregate` 嘅路程核一樣 |
| **RP** 兩樣一齊 | `0.8^k × P 權重` | 只做 ablation |

**唔登記 Trend 候選**：3–6 個點嘅斜率雜訊大，而且「越跑越好」好可能同近績質素重疊（memory
`au-late-fade-is-redundant-with-form`）。只報 leaf 層面診斷（每匹馬 own_i 對 k 嘅 OLS 斜率，≥3 仗），唔入判決。

## 判決

1. **replica**：baseline 離線重算 `pace_figure_score` 對引擎差 ≤ 1e-3（容許 dump 6dp 捨入），綜合分差 ≤ 0.005；唔過即停。
2. **leaf 診斷**（只報告）：場內配對 AUC，同 EXP-20261016-01 同一條式。
3. **v3 fixed_rule 全紀錄**（`evaluate_full_record`，2026-08-05 起乾淨窗、完整賽果、賽日 bootstrap 2000）。
4. **§8 四 arm**（`au_walkforward_refit.py predict` + `scratch/au_paceperf_s8_20261016.py`；refit 程序兩邊 hash 一樣）：
   - fixed arm WIN → 用 live 權重上線；否則 refit arm WIN 而且 live guard 唔係 `primary_regression`／`ranking_metric_harm`
     → 連 refit 權重一齊上線；其他一律 REJECT。
5. **多重比較**：R、P、RP 三個 arm × fixed／refit 當一個 family，**Holm**（6 個 p）。調整後 p < 0.05 先算 WIN。
6. **Ablation**：RP 只喺 R 同 P 各自 Gold、Good 點估計都 ≥ 0 先可以上線；否則用 R、P 之中過閘嘅單一個。
   兩個都過閘而 RP 唔過 → 揀 primary 合計較大嗰個。
7. **分層**（任一格 primary CI 全負 = 唔上線）：馬匹數（≤8／9–12／13+）、首選 SP（$1–3／$3–6／$6+）、
   今仗路程（≤1200／1201–1600／>1600）、首選 PF 仗數（1–2／3–5／6+）。

**Leakage**：權重只用 `run_date` 同路程（往績行本身同今仗賽事資料，賽前已知）。dump 斷言每條 PF 行 `run_date < 今仗日期`，
有一條唔係就停。PF 行來源同現行 production 一樣（Sportsbet form 頁洩漏已喺 `au-sportsbet-postrace-leakage` 修好）。

## 上線之後監察（過閘先做）

- 上線 commit 記低；凍結 baseline（上線前 code）喺 shadow 平行計，賽後逐場對比 Gold／Good。
- 預先登記 forward 確認：上線後 **600 場**完整賽果（約 3 星期），primary 點估計唔准負（v3 規則），否則提請 Kelvin 還原。
  中途唔准提早判；每週 Telegram 報進度。

## 唔准做

改 0.8、0.25、加權方式、缺路程規則；睇完結果加 arm（例如 0.7^k、0.9^k）；換窗口或指標救候選；
將 Trend 診斷當候選；未過閘就上線。
