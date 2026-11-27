# EXP-20261127-31 — HKJC 舊實驗重評：EXP-20260927-04／20260928-01／20260928-03

- **日期**：2026-11-27 ・ **平台**：HKJC ・ **commit**：`ab0876e8`（量度用 main）
- **起因**：Kelvin 2026-11-27 要求重評改善空間清單（`gap_report.json` 嘅 `old_rejects`）入面三個 HKJC 舊實驗。
  當時 247–320 場，而家多咗一個新馬季。
- **狀態**：**冇候選升級，冇改 live**。27-04 嘅 rail 連續 shadow 建議收咗；28-01／28-03 方向維持，靠現有 forward（沙田 draw70）同已上線嘅跑馬地 V3 監察判。
- **執行**：量度由 Codex Terra 做（`codex_delegate.py run grunt`），Claude 收貨同判斷。原始輸出喺外置碟
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/reeval-20261127/evidence/hkjc/`（`REPORT.md`、`v2.json`、`v2_oos.json`、
  `surface_ml.json`、`surface_ml_oos.json`、`course*.json`、`market_draw_surface.json`）。
- **搜索過嘅舊記錄**：EXP-20260927-04、EXP-20260928-01／03／06／10、EXP-20260929-01／02、EXP-20261014-11、EXP-20261015-02、EXP-20261105-04。

## 語料

| | 當時 | 而家 |
|---|---:|---:|
| ranking dataset | 32 meeting／320 場／3,972 匹（04-12 至 09-27） | **49 meeting／489 場／6,049 匹**（04-12 至 11-25） |
| 09-28 後新賽事（從未用嚟形成假設） | — | **17 meeting／169 場／2,077 匹**（10-01 至 11-25） |
| PIT 場地歷史覆蓋 | 87.89% | 86.10% |

**最重要嗰組數係「新賽事」169 場**：佢哋喺三個實驗之後先跑，係真正 out-of-sample。全部 489 場有 320 場已經用過。

## 三個要知嘅限制（Terra 標出，Claude 核實過邏輯）

1. **baseline 唔等於而家 live。** 28-03 harness 用固定 0.2737／0.20 線性替換 race-shape，而家跑馬地已經係 V3（EXP-20260929-01，
   draw + 0.45×PIT 谷草）。即係跑馬地嗰行 `draw_surface` 其實大致等於「V3 對舊版」，唔係新候選。沙田嘅 `current_live` 同而家 live 接近（沙田 race-shape 冇改過，只有 draw70 shadow）。
   dataset 嘅能力分係用今日引擎重算，唔係當時發出嘅預測。
2. **27-04 harness 有 9 場重複**（2026-05-13 跑馬地 R1–R9 各出兩次）：427 行 = 418 場唯一。全樣本數會輕微偏；新賽事 169 場冇呢個問題。
3. **同場同程覆蓋**而家報 64.09%，當時 16.54%，可能係來源／定義改咗，未查清，所以 `same_venue_distance` arm 唔作結論。

## 結果

### EXP-20260927-04 —— 場地適性／rail 先驗／預測跑法

| arm | 當時（247 場） | 新賽事 169 場 | 判讀 |
|---|---|---|---|
| 移除今仗預測跑法 | KEEP（已上線） | 全部 0.00（已經冇呢樣嘢） | 一致：上線版本已經冇預測跑法 |
| 同場同程直接加分（C） | Good −3.24 [−6.48,−0.40] REJECT | Gold −1.18 [−2.96,0.00]、Min −1.78 | **REJECT 維持** |
| rail 離散重排 | REJECT | Gold +0.59、Good −1.18，CI 全跨零 | **REJECT 維持** |
| rail 連續 excess（當時 **SHADOW ONLY**） | Gold 0、Good −0.40、NDCG +0.49 | **Good −3.55 [−7.69,0.00]**、Min −3.55、沙田 Min −7.89 [−15.79,−1.32] | **收咗**：新數據方向轉負 |

另外：而家 `DrawScorer` 本身已經有 PIT rail 調整（EXP-20261014-11 之後），harness 用候選成個覆蓋 draw scorer，同當時定義唔同。
即係 rail 連續版而家同 live 重疊，就算唔負都冇獨立空間。**建議唔再保留呢個 shadow。**

### EXP-20260928-01 —— 個別場地性能／race-shape component（ML 診斷，walk-forward）

| 對照 | 當時（189 場 OOS） | 新賽事 169 場 | 判讀 |
|---|---|---|---|
| draw 加落 base-6 | Champion +5.29、NDCG +2.74 | **Good +8.28 [+4.14,+13.02]**、NDCG +2.04 | **draw 再次確認有用**（沙田 Good +10.53 [+3.95,+18.42]） |
| fit 加喺 draw 後 | 全部 CI 跨零 | Good −1.18 [−2.96,0.00] | 仍然係噪音 |
| trip 加喺 draw 後 | 全部 CI 跨零 | Good −2.37 [−6.52,+1.78]；沙田 Good −5.26 | 仍然冇用，方向偏負 |
| surface_quality 加落 base-6 | **Good +4.23 [0,+8.47]** | Gold −1.18、Good +1.18 [−3.55,+6.51]、NDCG +1.68 [−0.54,+3.92] | **減弱咗**：OOS 冇再企穩 |
| shape+surface 對 current live | NDCG +4.27 | Gold +2.37 [−2.96,+7.69]、Good −0.59、NDCG +1.67 | CI 全跨零 |

結論同當時一致嘅部分：draw 係 race-shape 入面唯一穩陣有用嘅成分；fit／trip 加極少或者負。
**唔一致嘅部分**：個別場地性能（surface_quality）喺新賽事明顯弱咗，當時嘅 Good +4.23 冇重現。跑馬地 V3 就係用呢個訊號，所以要靠 V3 嘅 rollback 對照監察（EXP-20260929-01）繼續睇。

### EXP-20260928-03 —— Race Shape v2 deterministic A/B（鎖定規則：Stage-4 v2，dev／terminal Gold、Good 點估計唔准跌）

| arm | 全部 489（dev 411／terminal 78） | 新賽事 169 | 鎖定規則判決 |
|---|---|---|---|
| `surface_replaces_trip`（唯一合資格） | Gold −0.61；**dev Gold −0.73**；capture@5 +0.48 | Gold +0.59、Good 0.00、capture@5 +1.58 [+0.20,+2.96] | **REJECT 維持**（`primary_regression: gold`，dev） |
| `no_trip` | dev Gold −0.73、Good −0.49 | Gold +0.59、capture +1.78 [+0.39,+3.35] | 診斷 arm，冇晉級資格 |
| `draw_only` | dev Gold −0.49 | Gold +0.59、Good +0.59、NDCG +0.63 | 診斷 arm |
| `draw_surface` | dev Gold −0.24、Good +0.49 | Gold +0.59、Good 0.00、NDCG +0.85 [−0.00,+1.69] | 診斷 arm（跑馬地部分已經以 V3 上線） |

市場尺（m3，只做咗 `draw_surface`）：285 場／29 日（**未夠 30 計分日門檻**）。同市場差距 −0.00473 [−0.00979,+0.00023] nll／場，即係收窄少少但 CI 掂零；
而且繼承上面 baseline 失配，只係參考。

新賽事上排序指標（capture／recall）有細嘅正數，但 Gold／Good 冇郁，而 dev Gold 仍然係負。按鎖定規則，**唔可以用 secondary 指標救返**。
沙田（新賽事 76 場）：`no_trip`／`surface_replaces_trip` Gold +1.32、Good −1.32，一場來回，冇資訊。

## Forward 狀態（`forward_tests/hkjc.json`，2026-11-25）

- EXP-20260928-10 A（shape→stability 2pp）：11-23 鎖定 review 123／120 場 → REJECT（已判）。
- EXP-20260928-10 A+B：已撤（V3 上線後等於 A+B）。
- EXP-20260929-02 沙田 `draw70`：**53／80 場，收集中**。呢個係沙田 race-shape 方向嘅正式測試，夠數先判。
- 27-04 rail 連續 shadow：harness 層面嘅 shadow，冇登記入 tracker，今次建議收咗。

## 決定

- **冇 KEEP、冇改 live、冇新 forward。**
- **27-04 rail 連續版**：建議收咗（新數據 Good −3.55，而且同現行 PIT rail 調整重疊）。
- **28-01**：draw 再確認；fit／trip 仍然冇用；surface_quality 喺新數據減弱 → 跑馬地 V3 要繼續靠 rollback 對照監察，唔好當佢已證實。
- **28-03**：鎖定規則下 REJECT 維持；沙田方向交返 draw70 forward（53/80）判。
- **改善空間（唔准講做晒）**：(1) 用凍結版本做真正 replay，令 baseline 對齊而家 live（今次未做到）；(2) 查清同場同程覆蓋 16.54%→64.09% 嘅原因；
  (3) 27-04 harness 嘅 2026-05-13 重複行要修；(4) 市場尺等夠 30 個計分日再跑一次 `draw_surface`。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TMPDIR=<out>
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/build_hkjc_ranking_dataset.py --output $TMPDIR/dataset.csv --summary-output $TMPDIR/dataset_summary.json
python3 docs/experiments/patches/hkjc_course_style_ab.py --json-out $TMPDIR/course.json
python3 docs/experiments/patches/hkjc_surface_shape_ml.py --dataset $TMPDIR/dataset.csv --output $TMPDIR/surface_ml.json
python3 docs/experiments/patches/hkjc_race_shape_v2_ab.py --dataset $TMPDIR/dataset.csv --output $TMPDIR/v2.json
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform hkjc $TMPDIR/market_current_live.jsonl $TMPDIR/market_draw_surface.jsonl --out $TMPDIR/market_draw_surface.json
```
新賽事分組同 cohort 擴充用 out 目錄入面嘅 `v2_oos.py`、`surface_ml_oos.py`、`course_detail.py`、`course_continuous.py`（只加評估分組，訓練仍用全部歷史）。
