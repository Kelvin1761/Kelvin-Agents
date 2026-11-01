# EXP-20261101-41 結果：全程速度做速度分核心 —— leaf 準咗，但排名差咗（REJECT）

- **預先登記**：[protocol](EXP-20261101-41-au-whole-race-speed-core-protocol.md)（`a9a7ce2f`，量度之前）。
- **語料**：`dump_pos.json`（現行 production，EXP-40 同一份），**只用 2026-08-05 → 2026-10-16**：2,534 場、24,419 匹；
  10-17 起（S2 forward 窗）一場都冇入 arm。§8 OOS 1,531 場／42 日。
- replica：dump `ability` 由欄位重算 0 差。A_sb 由 EXP-02 原構造計（27,737 場往績事件、69 場衝突隔離）。

## leaf

| | 同一批馬場內 AUC |
|---|---:|
| 現行 `pace_figure` | 0.6063 |
| 全程速度 A_sb | **0.6196** |

覆蓋 21,048／24,419（86.2%）；W 郁到 2,309 場。

## 判決

| | Gold | Good | 判決 |
|---|---:|---:|---|
| v3 W（固定權重） | −0.79pp [−1.89, +0.23] | −0.91pp [−2.00, +0.15] | **REJECT／primary_regression** |
| §8 fixed | −0.85pp | −0.46pp | primary_regression |
| §8 refit（B1 vs B0） | −1.11pp | −0.33pp | primary_regression |
| §8 研究判決 | | | **both_arms_reject** |

CI 全負嘅分層：馬匹數 ≤8 Gold、≤1200m Good、首選守中 Good。

**只報告**：
- W_keep（保留 full_time overlay）同 W 嘅 primary 一模一樣 —— 呢個窗口 overlay 喺 W 郁到嘅場次幾乎冇發揮，拆唔拆冇分別。
- S2_ref（EXP-02 一半一半公式，放喺現行 baseline 上）：Gold −0.16pp、Good −0.28pp，固定權重都係 `primary_regression`。
  S2 嘅判決以 forward（EXP-20261016-03，15／41 日）為準，呢個數只係對照。

## 點解準咗反而差 —— 同其他維度重疊

場內 Spearman（同一批場次）：

| 對 | 現行 pace_figure | 全程速度 |
|---|---:|---:|
| form_score | 0.237 | **0.356** |
| consistency_score | 0.164 | **0.278** |
| class_score | 0.084 | **0.160** |
| performance_quality_score | 0.402 | 0.423 |

全程表現（完成時間對標準）本身係能力嘅好量度，但**狀態、穩定性、班次已經用名次同輸距量緊同一件事**。
現行 L600 分正正因為佢「量得唔準」，帶住賽事環境（快／慢步速）呢份同其他維度唔重疊嘅資訊，所以喺矩陣入面更有用
（記憶 `au-pace-figure-is-the-only-orthogonal-leaf`）。單獨 leaf AUC 升 +0.013 換唔到排名，同
`leaf-auc-gains-do-not-convert-to-ranking` 一致。

## 對重建計劃嘅影響

- 「全程速度做核心」**唔上**。速度分維持現行 L600 構造（`speed.py` 已經 1:1 重現，可以做簡化版本基礎）。
- 全程速度嘅價值留俾 S2 forward 判（一半一半＋refit 權重係另一個設計，未揭盲）。
- 唔准喺呢個窗再試 z 尺度／門檻／一半一半以外嘅混合比例（登記寫明）。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/speed-rebuild"
python3 scratch/au_whole_race_core_eval_20261101.py --dump $S/dump_pos.json --outdir $S/arms41
python3 scratch/au_position_l600_judge_20261101.py $S/arms41/base.json $S/arms41/W.json $S/v3_41/W.json
for a in base W; do python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data $S/arms41/$a.json --out $S/wf41/$a.json; done
python3 scratch/au_paceperf_s8_20261016.py --base $S/wf41/base.json --cand $S/wf41/W.json --label W --out $S/s8_41/W.json
```

refit procedure hash `f92c8377…e033`。證據：`EXP-20261101-41-evidence/`。
