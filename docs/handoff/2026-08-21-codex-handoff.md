# 交接：AU Wong Choi 現狀 → Codex（2026-08-21）

呢份係俾另一個 agent（Codex）**獨立覆核**用嘅。每一項都附命令，唔好信數字，跑一次。
完整審計：[`docs/audits/2026-08-21-repo-model-audit.md`](../audits/2026-08-21-repo-model-audit.md)

## Baseline

- **commit**：`b51793d7`（喺 `1c483561` 一樣成立 —— 引擎冇變，golden 過）
- **語料**：1,413 場 / 14,121 匹 / 2025-08-02 → 2026-08-20
- **模型**：手工擬合六維加權線性；**冇訓練步驟**、**冇 ML**、**賠率唔入分**

```bash
export PYTHONDONTWRITEBYTECODE=1          # 必須：macOS .pyc 靠 (mtime,大細) 判斷
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
python3 au_dump_engine_leaves.py --out /tmp/leaves.json
python3 au_matrix_refit.py verify --data /tmp/leaves.json
python3 au_eval.py --data /tmp/leaves.json --output-json /tmp/baseline_au.json
```

覆核應該見到：`races 1413  runners 14121`、`pace_figure state=ok 8884/14121 = 62.9%`、
verify `ability max|Δ|=0.0108`、`matrix max|Δ|=0.0033`。

| 指標 | all | dev (901) | holdout (512) |
|---|---|---|---|
| 頭5位 AUC（**主判決**） | 0.6793 | 0.6871 | 0.6631 |
| 全場 AUC | 0.6655 | 0.6725 | 0.6503 |
| gold | 17.79% | 16.13% | 20.70% |
| good_positional | 23.53% | 21.47% | 27.15% |
| pass | 46.99% | 43.72% | 52.73% |
| champion | 25.73% | 24.81% | 27.34% |

## 判決規則（唔准改）

完整合約：[`docs/model-evaluation-contract.md`](../model-evaluation-contract.md)


> 頭 K=5 位配對場內 AUC，**holdout** 95% 配對 bootstrap 區間唔過 0；**dev** 點估計唔准負。

場數指標係次要。理由：±0.3 中性擾動 40 次，三道場數閘全過 **0/40** —— 冇功效。

## 三個必須知嘅陷阱

1. **`Archive/`**：AU 排程搬完成場次入 `<root>/Archive/`。用 `corpus_paths.py`，
   **唔准 `rglob`**（HKJC 有真 backup 目錄會被當語料）。2026-08-21 之前呢個盲點
   令 49.1% 場次隱形（EXP-01）。
2. **bytecode**：改權重之前 `export PYTHONDONTWRITEBYTECODE=1`。
   「A/B 同 baseline 一模一樣」**先查有冇接通**，唔好報「冇效果」。
3. **並行寫入**：呢個 repo 有多過一個 agent 同時寫。commit 前睇 `git status`，
   只 stage 自己改嘅，**唔好 `git add -A`**。

## 主要風險（覆核重點）

| 風險 | 覆核命令 |
|---|---|
| **draw bias 只影響歷史評估** | matrix 喺 `_pace_map_score()`（`engine_core:1245`）用 → 餵 `race_shape`（w .135, gain **4.1142** 最大）。**live 唔受影響**（相對今日全部係過去）。回測就有：`au_draw_bias_matrix.json` mtime 2026-08-09，728 個 per-track cell 中位 sample_size **7**、43.5% < 5，dev 窗全部早過 08-09。**專用工具已存在**：`au_draw_walkforward_audit.py`，我搵唔到跑過嘅記錄 |
| **dev/holdout 係 regime 切分** | dev 11.0% 乾淨 point-in-time / 平均馬群 10.51；holdout 100% / 9.08 |
| **場數指標唔按馬群正規化** | dev 內 Gold：≤8 匹 31.58% → 13+ 匹 8.91%。控制馬群（9–10 匹）後 dev 15.38% **>** holdout 13.33% —— 同 pooled 方向相反 |
| holdout 實際 36.2% 唔係 15% | `date_partitions` 取日期百分比（`au_eval.py` 而家會印出嚟） |
| `form_line` 權重 0 | `MATRIX_FORMULAS` 有佢，`MATRIX_WEIGHTS` 冇 |
| `rating_score` 係時間窗欄位 | RA 個窗只回溯一星期，歷史值未必係當日真值 |

## 洩漏判定

SAFE：賠率（完全唔入分）、賽果欄位。
LIKELY SAFE：form / performance_quality / jockey / trainer / jockey_horse_fit / pace_figure / sectional。
QUESTIONABLE：`rating_score`。
**歷史評估限定：`pace_map_score` / draw bias（live 無洩漏）。**
CONFIRMED（已剔除）：sire signal —— leave-one-out +4.9pp 但 point-in-time 全負。
**LOO 唔係 leakage control。**

## 唔准重試（冇新數據源）

sire signal、Sportsbet Speedmap、轉贏注、位賠 ≥2 門檻、當朝落注、PF backfill、
jockey/trainer 六個公式方向、layoff 做排名特徵、自己 derive run style、
J/T combo 表入分、pairwise 權重逐對搜索、gain/權重聯合重 fit（EXP-02 已 REJECT）。
**唔准用** `au_matrix_weight_search.py` / `au_clean_7d_weight_search.py` /
`au_weight_improvement_search.py` —— 三個都係 argmax，實測 overfit。

## 建議 P1

1. **跑 `au_draw_walkforward_audit.py`** —— 工具已存在，唔使新寫。
   目標唔係升分，係令 `race_shape`（最大 gain）嘅過去量度可信。
   ⚠️ 該檔 2026-08-21 有另一個 session 未 commit 嘅改動，等落地先跑。
2. **場數指標按馬群分層** —— 必須**先於任何候選**做，否則就變成「改量度救候選」。

兩個都**未實作**。
