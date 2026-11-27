# EXP-20261127-30 — AU 舊實驗重評：EXP-20260826-02／20260821-02／20260821-03

- **日期**：2026-11-27 ・ **平台**：AU ・ **commit**：`ab0876e8`（量度用 main）
- **起因**：Kelvin 2026-11-27 要求重評改善空間清單（`gap_report.json` 嘅 `old_rejects`）入面三個 AU 舊實驗。當時 709–1,611 場，而家 5,102 場。
- **狀態**：**REJECT 維持，冇改 live**。有一樣同當時唔同：權重 refit 而家搵到過 fold 閘嘅候選（當時 0/400），而且方向好穩定，
  但係 walk-forward 樣本外冇過（Good −0.12、OBJ 6 個窗口贏 2 個）。
- **分工**：Terra（Codex）dump 語料、verify；Hydrogen（Gemini）寫 21-03 診斷腳本（Claude 修咗最外桶定義）；
  Codex 5 小時窗用到 96% 停派之後，掃描、refit、walk-forward 由 Claude 自己跑。
- **證據**：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/reeval-20261127/evidence/au-weights/`（`refit_*.log`、`consensus_*.json`、
  `sweep_*.json`、`wf_place_0805.log`、`pp_sweep.py`、`REPORT.md`）同 `evidence/au-diag/`（21-03 診斷 JSON／MD、腳本）。
- **搜索過嘅舊記錄**：EXP-20260821-02／03／04、EXP-20260822-03、EXP-20260826-02／03、EXP-20261013-01、EXP-20261015-20、EXP-20261102-07／08／09、EXP-20261103-08。

## 語料

| | 當時 | 而家 |
|---|---:|---:|
| 全語料（leaves dump） | 1,413（21-02）／1,611（26-02） | **5,102 場／49,713 匹**（2025-08-02 至 2026-11-26） |
| 2026-06+ | 1,033 | 4,524 |
| 2026-08-05+ 乾淨 PIT | 709–809 | **4,299** |
| replica 對引擎 ability | max\|Δ\| 0.0108 | **0.000000** |

**verify 有個工具 bug**（Terra 搵到）：`cmd_verify` 嘅慢速對照只加 wet／proven_class／full_time／draw，冇加 `Dataset.fixed_overlays` 入面嘅
old_horse／trainer_residual／people_prize／speed，所以慢速對照差 7.25。refit 用嘅 `Dataset` 有齊 overlay，replica 對引擎存檔 0 差，所以唔影響今次結果。
慢速對照要修（改善空間第 3 項）。

現行排名權重（`dimensions.py`）：stability 0.3357、pace_perf **0.1441**（當時 0.12205）、jockey_trainer 0.8417、class_weight 0.3759、track 0.0960、preparation 0.1865。
race_shape 已經退出排名；顯示尺 gain 機制已退役（`MATRIX_DISPLAY_GAINS` 空表、`cmd_gains` 直接 raise）。

## EXP-20260826-02 —— pace_perf 權重

### 掃描（其餘維度按比例縮放保持總和；逐場配對 bootstrap 2,000、seed 7；pp [95% CI]）

全語料 5,102 場（dev 3,924／holdout 1,178）：

| pace_perf | dev Gold | dev Good | dev NDCG@5 | holdout Gold | holdout Good | holdout NDCG@5 |
|---:|---|---|---|---|---|---|
| 0.00 | −0.56 [−1.22,+0.05] | −0.61 [−1.33,+0.03] | **−0.41 [−0.70,−0.14]** | −1.19 [−2.55,+0.17] | −0.17 | −0.34 |
| 0.05 | −0.13 | −0.51 | **−0.24 [−0.48,−0.01]** | −0.93 | −0.17 | −0.25 |
| 0.09 | −0.20 | −0.31 | **−0.17 [−0.33,−0.01]** | +0.08 | +0.25 | −0.17 |
| **0.1441（現值）** | — | — | — | — | — | — |
| 0.18 | +0.15 | +0.03 | +0.12 [−0.03,+0.26] | 0.00 | +0.25 | −0.02 |
| 0.22 | +0.15 | +0.03 | **+0.24 [+0.06,+0.44]** | +0.08 | +0.25 | −0.04 |
| 0.26 | +0.08 | −0.10 | +0.23 | −0.25 | −0.17 | −0.04 |

乾淨 08-05+（4,299 場，dev 3,606／holdout 693）：調低一樣 dev 負（0.00：holdout Gold **−1.73 [−3.32,−0.14]**、NDCG **−0.72 [−1.35,−0.08]**）；
調高到 0.18／0.22 dev NDCG CI 正，但 holdout Gold −0.29／−0.43、NDCG −0.23／−0.34（CI 跨零）。2026-06+ 同一個形狀。

**判讀**：同當時一樣，**調低一定差**（dev NDCG CI 全負，乾淨語料 holdout 都顯著負）。**調高 dev 有少少好處，holdout 冇跟**。現值坐喺平頂上。

### refit（`--obj place`，400 條，seed 20260826，共識取過閘候選中位數）

| 語料 | 過 4/5 fold 閘 | 共識 pace_perf | holdout Gold／Good／NDCG（點估計） |
|---|---:|---:|---|
| 全部 | 19／400（贏 dev 57） | 0.1666 | +0.68／+0.42／+0.07 |
| 2026-06+ | 19／400 | 0.1792 | +0.86／0.00／+0.18 |
| 08-05+ | 26／400 | 0.1925 | +0.29／+1.30／−0.15 |

**同當時唔同**：8 月 0 條過閘，而家有 19–26 條，而且三個語料嘅共識方向一致：pace_perf ↑、jockey_trainer ↑、class_weight ↓、stability ↓、track ↓。

### drop pace_perf（`--drop-dim pace_perf`）

基準 dev OBJ：全部 36.2534 → **35.7543（−0.50）**；2026-06+ 37.2463 → 36.7030（−0.54）。剷走之後重 fit 都補唔返（全部 holdout Gold −0.42）。
pace_perf 邊際貢獻仍然係正，同當時（−1.03）一致，幅度細咗一半。

## EXP-20260821-02 —— gain＋權重聯合重 fit

- **Candidate B（新 gain＋等價權重）**：**唔適用**，gain 機制已退役。
- **Candidate A（權重 refit，`--obj balanced`、400 條、seed 20260821，同原實驗）**：64 條贏 dev、**20 條過 4/5 fold**（當時 7／0）。
  共識：stability 0.2811、pace_perf 0.1819、jockey_trainer 0.9249、class_weight 0.2870、track 0.1136、preparation 0.1914。
  holdout（1,178 場）點估計 Gold +0.42、Good +0.08、NDCG +0.08、winT3 +0.59。

## 判決用嘅測試：walk-forward（合約：fit 類候選一定要 walk-forward，AU 只用 08-05+ 乾淨段）

`au_matrix_refit.py walkforward --obj place --n 400 --wf-start 1500 --wf-window 400`，6 個窗口、2,400 場**全部樣本外**：

| 窗口 | 共識 pace_perf | ΔGold | ΔGood | ΔNDCG@5 |
|---|---:|---:|---:|---:|
| 1500→1900 | 0.206 | −0.50 | −1.75 | +0.35 |
| 1900→2300 | 0.188 | 0.00 | −0.25 | +0.47 |
| 2300→2700 | 0.158 | −0.50 | 0.00 | −0.17 |
| 2700→3100 | 0.169 | +0.75 | −0.25 | +0.36 |
| 3100→3500 | 0.199 | +0.75 | +1.00 | +0.35 |
| 3500→3900 | 0.196 | +1.00 | +0.50 | +0.61 |
| **平均** | 0.191 | **+0.25** | **−0.12** | **+0.33** |

OBJ（place）贏嘅窗口 **2/6**。Good 點估計倒退，按 Stage-4 規則 **REJECT**。最近兩個窗口都係正，但呢個係睇完結果先見到嘅形狀，唔可以用嚟救。
市場尺：冇候選過閘，**唔適用**（冇做）。

## EXP-20260821-03 —— pace_map_score 4 級階梯同馬匹數

診斷腳本：`evidence/au-diag/reeval_au_pace_map_gradient.py`（Hydrogen 寫；Claude 將「最外桶」改為按馬匹數揀天然最外桶：
5–8→中檔、9–11→外檔、12–14／15+→大外檔。原版揀咗退出馬留低嘅 n=1 檔位桶，9–11 匹場出咗 −27pp 假差距）。
入位 = 前 3 名；超額 = 入位 − 3/馬匹數；以場為單位 bootstrap 2,000、seed 7。

| 量度 | 當時（709 場） | 而家 08-22+ 新數據（4,240 場） | 11-02 後（1,208 場） |
|---|---|---|---|
| 每場唔同分值 | 3.13 | 4.45 | **8.46** |
| 同分馬匹比例 | 96.6% | 74.3% | **14.5%** |
| 內↔最外差距 5–8 匹 | 1.6pp（CI 重疊） | **2.6 [+0.4,+4.8]** | 3.1 [−1.2,+7.2] |
| 內↔最外差距 9–11 匹 | 7.6pp | **4.4 [+2.5,+6.3]** | 4.9 [+1.1,+8.6] |
| 內↔最外差距 12–14 匹 | 10.7pp | **4.8 [+0.3,+9.2]** | 5.1 [−1.9,+12.0] |

（我用同一個腳本重算當時嗰段（≤08-21，670 場）得 3.3／1.9／6.6，CI 全部跨零，即係當時嗰個「6.7 倍」本身係細樣本，同而家嘅計法亦唔完全一樣。）

**判讀**：
1. **4 級階梯問題已經冇咗**：11-02 起 `pace_map_score` 改用 `draw.py`（EXP-20261102-09），每場 8.5 個分值。
2. **「按馬匹數縮放」嘅前提弱咗**：新數據大場次對細場次只係約 1.8 倍（當時講 6.7 倍），而且 **5–8 匹細場次都有細而顯著嘅內檔優勢（+2.6pp）**。
3. 呢個方向已經有正式測試：大場次檔位分（≥8 匹，EXP-20261102-08）係用戶接受嘅實驗性上線，forward **793／1,000 場**，夠數自動判。唔另開 A/B。

## 決定

- **EXP-20260826-02**：REJECT 維持，pace_perf 留 0.1441。調低肯定差；調高 dev 好、樣本外冇跟。
- **EXP-20260821-02**：Candidate B 不適用（機制退役）；Candidate A 而家過到 fold 閘，但 walk-forward Good −0.12、OBJ 2/6 → **REJECT**。
- **EXP-20260821-03**：診斷更新（見上），交返 EXP-20261102-08 forward 判（793/1,000）。
- **冇改 model code，冇改 golden／data_contract。**

## 改善空間（唔准講做晒）

1. **refit 方向而家穩定**（pace_perf ↑ 到約 0.19、track ↓、騎練 ↑；6 個 walk-forward 窗口全部同一方向）。值得用合約 v3 正式 harness 判一次：
   逐場 walk-forward 預測 + 賽日 bootstrap + **市場尺**（m3 追市場軌）。但 AU walk-forward 預測產生器仲未整理成可重用工具（合約 §8 註），要先整。
2. 細場次（5–8 匹）內檔 +2.6pp 喺新數據顯著，而現行 `draw.py` 只管 ≥8 匹 → 等 EXP-20261102-08 判完之後，可以預先登記一個細場次 arm。
3. 修 `au_matrix_refit.py cmd_verify` 慢速對照漏 overlay。
4. 21-03 診斷腳本可以放入 `shared_racing/scripts`，每季跑一次檔位桶 × 馬匹數，捉檔位訊號漂移。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=<out>
S=.agents/skills/au_racing/au_wong_choi_auto/scripts
python3 $S/au_dump_engine_leaves.py --out $TMPDIR/leaves.json
python3 $S/au_matrix_refit.py verify --data $TMPDIR/leaves.json
python3 $S/au_matrix_refit.py refit --data $TMPDIR/leaves.json --obj place --n 400 --seed 20260826        # 06+／08-05+ 用按 date 篩嘅子檔
python3 $S/au_matrix_refit.py refit --data $TMPDIR/leaves.json --obj place --drop-dim pace_perf --n 400 --seed 20260826
python3 $S/au_matrix_refit.py refit --data $TMPDIR/leaves.json --obj balanced --n 400 --seed 20260821
python3 $S/au_matrix_refit.py walkforward --data $TMPDIR/leaves_0805.json --obj place --n 400 --seed 20260826 --wf-start 1500 --wf-window 400
python3 <evidence>/au-weights/pp_sweep.py $TMPDIR/leaves.json $TMPDIR/sweep_all.json
python3 <evidence>/au-diag/reeval_au_pace_map_gradient.py --out <dir> [--since/--until]
```
