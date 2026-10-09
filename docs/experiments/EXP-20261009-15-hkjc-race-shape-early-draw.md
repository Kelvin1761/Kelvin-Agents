# EXP-20261009-15 — HKJC race_shape：按條件調整、習慣前速、檔位 × 前速

- 日期：2026-10-09；平台：HKJC
- 狀態：**E3 USER-ACCEPTANCE PENDING（release 待 `/approve`）／未通過 Stage-4 閘**；
  E1、E2 唔上線；「按條件調檔位權重」判死
- 目標（Kelvin）：race_shape 要反映唔同賽日嘅馬匹同條件，令賽日之間表現穩定啲
- 上游：EXP-20261009-14（賽日穩定性分析）

## 1. 檔位重要性隨條件變？唔穩定 → 唔做

`rail_draw_results.csv` 1,785 場（2024-09 → 2026-10）。每個 venue × track × rail × 路程格，
24/25 季同 25/26 季分別計「內檔入位」AUC：

- **檔位**：兩季相關 r = +0.106（運氣門檻 +0.392）→ 細格差異係噪音，
  「按欄位調 race_shape 權重」會 fit 噪音。解釋埋點解 draw context v2 次次量唔到。
- **首段位置**：兩季相關 r = +0.607（門檻 +0.402）→ 「跑前有幾著數」係穩定嘅條件特性：
  C／C+3 短途 ~0.68–0.69，A 欄一哩 ~0.52–0.57。整體首段位置 AUC 0.614 > 檔位 0.559。

## 2. 習慣前速（賽前可知）

近 ≤6 仗首段位置百分位（profile running_positions，賽日之前；馬匹數取 rail_draw_results，
否則 12）。dev 診斷：預測今仗首段位置 r = 0.52；固定我哋排名後預測入位 AUC 0.562
[0.531, 0.593]；同 race_shape 相關 r = −0.006（完全正交）。

## 3. 預先登記（跑排名結果之前寫低，原文）

### PRE-REGISTRATION — HKJC habitual early speed (2026-10-09, before any ranking outcome)

Diagnostics already seen (dev only): habitual early position predicts today's first call
(r 0.52), predicts placing conditional on our rank (AUC 0.562 [0.531, 0.593]), is orthogonal
to race_shape (r −0.006). Cell early-importance is season-stable (r 0.607); cell draw
importance is not (r 0.106) — so no draw-by-condition candidate is registered.

## Feature (fixed)
habitual = mean over the horse's last ≤6 HK runs strictly before race date of
(first running position − 1)/(field size − 1); field size from rail_draw_results for that
(date, race), else 12. Needs ≥2 runs, else missing. Identity via racecard ID + name match.
early = −habitual (higher = more forward). z = within-race standardised early over runners
with data; missing → 0; races with <4 runners with data → no adjustment.

## Arms
E1 (flat): ability' = ability + w·z, w ∈ {0.5, 1.0, 2.0}.
E2 (condition-aware): ability' = ability + w*·m_c·z, w* = E1's selected w (no new grid);
m_c = clip((imp_c − 0.5)/(imp_venue − 0.5), 0.5, 1.5); imp_c = mean first-call AUC in
venue×track×rail×distance band (≤1200/≤1650/longer) over races strictly before race date,
shrunk to the venue mean with 30 pseudo-races; FirstCall > FieldSize+1 treated as missing.

## Baseline / data
Live outer weights (race_shape 0.2416 arm of EXP-20261009-13 corpus run), 332 races,
same engine-refused races excluded. Dev = before 2026-09-16; terminal = 09-16 → 10-07.
NOTE: this terminal window was already opened for EXP-20261008-07 and EXP-20261009-13;
it is not pristine. Forward meetings after 2026-10-09 are the clean confirmation.

## Selection (dev only)
E1: eligible if dev Gold Δ ≥ 0, Good Δ ≥ 0, ≥3/5 chronological blocks non-negative on both,
≥2 of (capture@5, NDCG@5, competitive recall@5) Δ > 0. Pick the smallest eligible w.
None → REJECT_DEV (E2 not run, terminal not opened).
E2 replaces E1 only if, on dev, E2 − E1 has Gold Δ ≥ 0 and Good Δ ≥ 0 and capture@5 Δ > 0.
Terminal opened once for the final arm; Stage-4 v2; any primary terminal point regression → REJECT.
A KEEP must be re-verified by a real engine implementation before release.

## ADDENDUM — E3 draw × early-speed interaction (written after E1 terminal, before any E3 run)
Motivation (dev diagnostic, so dev is NOT clean evidence for E3): draw AUC among forward /
mid / back thirds 0.553 / 0.630 / 0.706; wide (9+) forward runners place 22.1% vs wide
back-markers 9.3%, yet race_shape scores them identically (54.4 vs 54.5).
Term: d = −z(barrier) within race (inner positive); e = early z as above (0 if missing);
I = max(0, −d) × e  (only runners drawn wider than the race average; forward → bonus,
back → penalty). ability' = ability + w·z(I) with z over the race, w ∈ {0.5, 1.0, 2.0}.
Barrier = official draw (rail_draw_results Draw), fixed at declaration. Same dev selection rule
as E1; terminal once; forward meetings after 2026-10-09 are the confirmation that counts.
E3 is evaluated against the live baseline, not stacked on E1.


## 4. 結果（offline screen，332 場）

| Arm | dev 判斷 | terminal | 判決 |
|---|---|---|---|
| E1 平坦前速 w=0.5 | Gold／Good 0、排序三項 + | Gold +1.75pp、Good +1.75pp，CI 下界 0 | REJECT（ranking evidence too weak） |
| E2 按條件縮放 | 對 E1：Good −0.38pp | — | 唔取代 E1 |
| **E3 檔位×前速 w=0.5** | Good +0.75pp、capture +0.50pp、block 4/5 | Gold +1.75pp、capture +0.58pp、recall +0.35pp | REJECT（ranking evidence too weak），零 primary 退步 |

### 獨立驗證機制（1,436 場，2024-09 → 2026-04，完全唔喺語料入面）

| 習慣跑法 | 檔位 AUC（內檔較好） |
|---|---|
| 慣性前置 | 0.519 [0.497, 0.539] |
| 中間 | 0.569 |
| 慣性後上 | 0.582 [0.556, 0.612] |

大外檔（9+）前置馬入位 25.5%，後上馬 16.9%；舊 race_shape 對兩者評分一樣（54.4 vs 54.5）。

## 5. E3 真 engine 驗證（338 場）

Baseline release `2a3cb4e`，candidate = 本改動；兩邊同一份 Logic，只轉移 Facts 新欄位。
Harness 改用排位表 ID＋較早賽日嘅 profile cache（只會用 race date 之前 fetch 嘅），
身份棄權由 1,108 減到 206（905 匹由較早 cache 補返）。

| 指標 | Dev Δ | Terminal Δ | Terminal CI |
|---|---:|---:|---|
| gold | +0.0072 | +0.0169 | [0.0000, +0.0508] |
| good_positional | +0.0072 | 0.0000 | [0, 0] |
| top3_capture_at5 | +0.0096 | 0.0000 | [−0.0169, +0.0169] |
| ndcg_at5 | +0.0037 | −0.0069 | [−0.0178, +0.0035] |
| competitive_recall_at5 | +0.0030 | +0.0034 | [0.0000, +0.0102] |
| mean_top3_model_rank（越低越好） | −0.0299 | +0.0226 | [−0.0395, +0.0847] |

Cohorts（全語料）：HV Gold +0.84pp；ST Gold +0.91pp／Good +0.91pp；≥11 匹 Gold +1.29pp；
≤10 匹（29 場）Gold −3.45pp（一場）。220 場排名有郁。
賽日穩定性：Good 賽日 SD 0.161 → 0.153；零 Good 日 4 → 3；最差五日 capture 49.1% → 49.4%。

**Stage-4 判決：REJECT（ranking_evidence_too_weak）—— 冇 primary 退步，但冇 CI 支持。**
**呢個冇通過表現閘，唔係一個已證實嘅改善。** 上線與否由 Kelvin 批 release 決定（同 EXP-20261009-14）。
Terminal 窗口今日已開過三次（EXP-20261008-07、-03、本實驗），唔再乾淨；10-09 之後嘅賽日先算。

## 6. 實作

- Facts：`- **習慣前速:** 0.2500 (近6仗…)`（`habitual_early_position`，race date 之前，<2 仗＝未有）。
- Logic：`_data.habitual_early_position`／`habitual_early_runs`。
- Orchestrator race-level：race_shape 封頂之後、正式排名之前加 `early_draw_adjustment`；
  validator `SCORE-004` 計埋佢。`EARLY_DRAW_DISPLAY_WEIGHT = 0.5`，少過 4 匹有資料＝整場唔做。
- 回退對照 shadow `early_draw_rollback`（120 場；舊式淨多贏 ≥2 場 Gold 或 Good → recommend_rollback）。
- Contract `…_EARLY_DRAW_X05`；模型說明列明呢項 adjustment。

## 7. 順手修正／發現

- **前瞻權重 arms 一直冇經 race_shape 封頂**：`weight_refit_t02` 用未封頂 shape（例：75.22 vs live 75.0），
  即係佢同 live 嘅差 = 權重 + 封頂。而家四個純權重 arm 都經同一個封頂同 E3，只差權重。
  t02 頭 9 場（10-07）係舊算法；rollback_0809／w200／w170 未收過任何前瞻場。
- **Validator 同排名嘅同分次序唔一致**：`ensure_verdict` 同分用 raw，`VERDICT-002/003` 用 2 位小數顯示分。
  已統一用 raw。
- **初出馬 `SCORE-004`（已修，live bug）**：race_shape 封頂對初出馬用咗 live 權重
  （`MATRIX_WEIGHTS["race_shape"]`），但初出馬用 `DEBUT_MATRIX_WEIGHTS`（0.20）計分 →
  分數多咗 Δ權重 × 封頂幅度，validator 拒絕**成場**。舊語料 18 場就係咁冇咗；封頂 10-07/08
  先上線，所以 live 未中過，但下一個有初出馬被封頂嘅場次就會冇咗成場。改用 validator 同一條
  初出馬規則揀權重＋測試。
- **`rail_draw_results.csv` 2026-05-03 FirstCall 壞咗（已修）**：沿途位黏埋（例如 101010093），
  builder 用 `positive_int(running_positions)`。改為只取第一個以空格分隔嘅位置；冇分隔又多過兩位
  ＝分唔清 → 空白；大過 14（香港最大馬匹數）→ 空白。重建後 05-03 嘅 278 行變空白（唔係垃圾值）。
  Live 排名唔讀呢欄；`hkjc_rail_position_shadow.py` 讀。
- 模型說明「同程性能修正」嘅數字（+0.43／−0.17）跟權重變咗做 +0.46／−0.18，已更新。

## 8. 最終全語料驗證（修好初出馬之後，351 場，0 場被拒）

Baseline = 同一份 code 但 `EARLY_DRAW_DISPLAY_WEIGHT = 0`（兩邊都有初出馬修正），只差 E3。

| 指標 | Dev Δ | Terminal Δ | Terminal CI |
|---|---:|---:|---|
| gold | +0.0068 | +0.0169 | [0.0000, +0.0508] |
| good_positional | +0.0034 | 0.0000 | [0, 0] |
| top3_capture_at5 | +0.0103 | 0.0000 | [−0.0169, +0.0169] |
| ndcg_at5 | +0.0036 | −0.0069 | [−0.0178, +0.0035] |
| competitive_recall_at5 | +0.0038 | +0.0034 | [0.0000, +0.0102] |

Cohorts：HV Gold +0.81pp；ST Gold +0.88pp／Good +0.44pp；≤10 匹 Gold −3.45pp（29 場入面一場）。
賽日穩定性：Good 賽日 SD 0.155 → 0.150。判決不變：REJECT（ranking_evidence_too_weak），零 primary 退步。

## 9. 「完全優化」嘅界線（誠實版）

用現有 351 場可以做嘅已經做晒：每個方向都有預先登記嘅判決，最好嘅候選（E3）冇任何 primary
退步，機制喺獨立歷史證實。冇做到嘅係**證明**改善 —— 語料一場 Good＝0.29pp，E3 嘅效應
細過 CI 解像度。呢個唔係再試幾個 w 可以解決（嗰樣叫用 holdout 調參），要靠 10-09 之後
嘅前瞻賽日。所有 arm 已經喺 immutable snapshot 量緊，120 場（約 6 星期）出判決。
