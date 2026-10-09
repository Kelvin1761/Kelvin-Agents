# EXP-20261009-12 — HKJC 今季評分升幅

- 日期：2026-10-09；平台：HKJC；狀態：**REJECT_DEV／terminal 未開／前瞻觀察**
- 上游：EXP-20261009-11。Baseline：release `7aa8cda` corpus（333 場）。
- 呢個係**失敗實驗**；冇改 model code。

## 預先登記（跑結果之前寫低，原文）

### PRE-REGISTRATION — HKJC rating progress (written 2026-10-09, before any outcome run)

Hypothesis: a horse whose official rating has risen since the start of its latest
active season is improving faster than our composite credits. Dev-only diagnostic
(93 races with data): AUC 0.581 [0.510, 0.648] conditional on our rank AND form tercile.
Exploratory — picked after looking at 16 fields, so treat as a hypothesis, not evidence.

## Feature (fixed)
- `current_rating`: racecard `評分:` for the target race (pre-race, official).
- `rating_season_start`: existing orchestrator definition, unchanged — rating carried
  at the earliest run of the horse's most recent season with a run, from profile
  entries strictly before race date (`_profile_season_key`).
- `progress = current_rating − rating_season_start`. Missing either → no adjustment.
- Debutants / no profile identity → no adjustment.

## Candidate (fixed form, one free parameter)
ability' = ability + w × z, z = within-race standardised progress (runners with data,
mean 0, SD 1; races with < 4 runners with data → no adjustment). Rank by ability'.
Grid (pre-declared, nothing else): w ∈ {0.5, 1.0, 2.0} composite points per SD.

## Data
Baseline = corpus-replay/candidate arm (history-alignment fix, release 7aa8cda),
333 races / 35 meetings 2026-04-12 → 2026-10-07; same 18 engine-refused races excluded.
Terminal = locked last 15% of dates (2026-09-16 → 2026-10-07), untouched until a w is selected.

## Selection (dev only)
Dev split into 5 chronological blocks of equal date count. A w is eligible only if:
aggregate dev Gold Δ ≥ 0 and Good Δ ≥ 0; ≥ 3/5 blocks non-negative on both;
≥ 2 of (top3_capture_at5, ndcg_at5, competitive_recall_at5) dev Δ > 0.
Select the SMALLEST eligible w. None eligible → REJECT_DEV, terminal not opened.

## Terminal (once)
Stage-4 v2 via `build_evaluation_input` / `evaluate_candidate`. Any primary terminal
point regression → REJECT. Cohorts HV/ST and field ≤10/≥11 reported.
Offline screen only: a KEEP must be re-verified by a real engine implementation on
the same corpus before any release.

## Leakage checks
Profile entries strictly < race date; racecard rating is the declared pre-race value;
no results, odds or in-running fields used. Odds are not used at any stage.


## 數據修正（判決之前，同候選無關）

第一次跑覆蓋率只得 19.3%：舊 Logic 冇 `hkjc_horse_id`，profile cache 對唔到。
改用排位表 `HKJC馬匹ID`／`烙號`（名仍然要對得上）之後係 72.3%（2,996/4,141）。
排位表評分本身 98.5% 有值。下面係修正後結果；修正前嘅結果亦係 REJECT_DEV。

## 結果（dev，275 場，terminal 封住）

| w | Gold Δ | Good Δ | capture@5 Δ | NDCG Δ | comp. recall Δ | block 過關 | 頭三有變嘅場 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.5 | 0.0000 | −0.0109 | +0.0024 | −0.0004 | +0.0030 | 2/5 | 31 |
| 1.0 | +0.0036 | −0.0036 | +0.0085 | +0.0038 | +0.0075 | 1/5 | 75 |
| 2.0 | +0.0036 | −0.0073 | +0.0170 | +0.0052 | +0.0098 | 3/5 | 116 |

**判決：REJECT_DEV**。Good 喺每個 w 都係負，冇一個 w 合資格；terminal 冇開。
形狀：排序指標隨 w 升，但「頭兩揀都入位」跌，同 EXP-20261009-13 一樣。

## 前瞻觀察（Kelvin：「at least continue to observe」）

輸入（排位表評分＋賽前 profile cache）每個賽日都會存檔，所以唔使改 engine 都可以前瞻量。
**預先宣告**：只用 2026-10-09 之後嘅賽日，固定 w = 2.0（dev 排序增益最大、Gold 無負），
儲夠 120 場先用 Stage-4 v2 判一次；唔再加 arm、唔再改 w。
Script：`scratch/hkjc_rating_progress_screen.py`。
