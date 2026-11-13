# EXP-20261113-41 結果：短直路前置加分（walk-forward 擬合幅度）—— REJECT

- **預先登記**：[protocol](EXP-20261113-41-au-short-straight-front-walkforward-protocol.md)（`a06b76a4`，量度之前 commit）。
- **baseline**：`FINAL.json`（main `1c33b058` 評分），判決窗 2026-08-05 起 3,736 場、99 個賽日。
- **碼**：`scratch/au_short_straight_wf_20261113.py`、`scratch/au_short_straight_wf_judge_20261113.py`。證據：`EXP-20261113-41-evidence/`。
- **決定**：**REJECT / primary_regression**。冇改動。

## 擬合出嚟嘅幅度

warmup 20 日之後，β 喺 1.42–2.96 之間，穩定喺約 2.2 分（08-26 1.50 → 10-04 2.67 → 11-12 2.18；中位 2.20）。
即係數據自己揀嘅幅度同 EXP-20261113-23 L2（人手 +2）差唔多 —— L2 唔係「揀錯幅度」。
郁咗 840 場、1,910 匹。

## v3 walk_forward_oos

| 指標 | Δ | 95% CI | p | 時間塊 ≥0 |
|---|---|---|---|---|
| Gold | +0.08pp | [−0.17, +0.31] | 0.60 | 4/6 |
| Good | −0.05pp | [−0.32, +0.24] | 0.78 | **3/6** |
| top3@5 | +0.11 | [−0.01, +0.23] | 0.083 | |
| ndcg@5 | +0.10 | [−0.01, +0.20] | 0.066 | |
| top5 AUC | **+0.11** | **[+0.02, +0.19]** | **0.007** | |

Good 點估計 < 0 兼時間塊只有 3/6 ≥ 0 → `primary_regression`。冇分層 CI 全負；首選跑法分層全部跨零（首選後上 Gold +0.49 [−0.15, +1.15]）。

## 解讀

- 描述層嘅剩餘超額（短直路前置馬喺模型同名次入面 +2.8～+4.2pp）係真，加分亦真係令**頭 5 名入面嘅排序**準咗
  （AUC CI 全正，三個排序指標方向一致）。
- 但換唔到 Gold／Good：被加分推上頭兩名嘅前置馬，同被擠落去嗰匹差唔多，所以「揀中前三」冇變。
  同 EXP-20261113-23 L2、EXP-20260902-01 同一個形狀，亦即係「cohort 有差距唔等於可上線收益」。
- 就算唔計 primary，AUC p 0.007 喺 4 個 arm 嘅 Holm 下 ≈ 0.028，但 v3 次序係 primary 先判，所以唔會變 RANKING_WIN。

## 唔再試

- 幅度已經由數據揀過，同人手值一樣，換幅度冇空間。
- 唔准改門檻做 400m（睇咗描述先講嘅分界）。
- 呢個 L family 今日已經開咗兩次（L1–L3、W1）。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-short-straight-wf"
python3 scratch/au_short_straight_wf_20261113.py "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113/FINAL.json" "$D"
```
