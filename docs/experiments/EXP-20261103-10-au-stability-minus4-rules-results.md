# EXP-20261103-10 結果：剷走兩條「−4」手寫規則 —— 上線（§7）

- **預先登記**：[protocol](EXP-20261103-10-au-stability-minus4-rules-protocol.md)；**baseline**：EXP-20261103-09（分數 = `cefaa88f`）。
- **⚠️ 冇通過表現閘，唔係已證實嘅改善** —— §7 正確性修正（重複計分、冇來源）。

全語料 561 場、809 匹分數郁；乾淨窗口（08-05 起 3,302 場）184 場郁。

| 指標 | Δ | 95% CI | p |
|---|---|---|---|
| Gold | +0.061pp | [0.000, +0.153] | 0.254 |
| good_positional | −0.030pp | [−0.148, +0.063] | 0.773 |
| top3_capture_at5 | −0.020 | [−0.062, +0.020] | 0.275 |
| ndcg_at5 | +0.009 | [−0.015, +0.032] | 0.448 |
| top5_pairwise_auc | +0.004 | [−0.022, +0.028] | 0.718 |

v3 標籤 `REJECT / primary_regression`（Good 點估計負），但 primary 冇顯著負、預先聲明分層冇 CI 全負 → **§7 過，上線**。
兩條一齊剷（結果冇分歧，唔使逐條 ablation）。`TRACK_WEAK_THRESHOLD` 一齊剷。

## 可重現

    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out {refactor,minus4}.json
    python3 scratch/au_track_simplify_judge_20261103.py refactor.json minus4.json judge.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/stability/`。
