# EXP-20261103-08 結果：Flemington 直路賽檔位分歸零 —— 上線

- **預先登記**：[protocol](EXP-20261103-08-au-flemington-straight-draw-protocol.md)；**baseline**：`0c2c1166`。
- **決定**：上線（USER-ACCEPTED 機制修正）；v3 判決 `RANKING_WIN / primary_neutral_ranking_supported_gain`，§7 亦過。

## 範圍核對（全語料 dump）

4,105 場入面只有 **67 場**郁（全部 Flemington ≤1200m ≥8 匹），737 匹，郁咗嘅 `draw` 全部變 0；範圍外 0 場。
乾淨窗口（08-05 起）12 場。

## v3 fixed_rule（08-05 起 3,302 場，12 場分數郁）

| 指標 | Δ | 95% CI | p |
|---|---|---|---|
| Gold | 0.000pp | [0.000, 0.000] | 1.0 |
| good_positional | +0.061pp | [0.000, +0.150] | 0.259 |
| top3_capture_at5 | −0.010 | [−0.031, 0.000] | 0.716 |
| ndcg_at5 | +0.006 | [0.000, +0.013] | 0.032 |
| top5_pairwise_auc | +0.004 | [−0.005, +0.013] | 0.506 |

預先聲明分層冇 CI 全負。得 12 場，ndcg 嘅 p 0.032 唔好當證據 —— 上線理據係機制（直路冇彎），唔係呢個數。

## Forward

`au_draw_forward.py` 讀已存 `draw_feature`，直路賽變 0 之後自動一致；EXP-20261102-08 繼續計 1,000 場。
Flemington 彎道賽內檔都差（19.7%），冇機制理由，今次唔郁；夠場數再睇。

## 可重現

    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out {base,cand}.json
    python3 scratch/au_track_simplify_judge_20261103.py base.json cand.json judge.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/draw-straight/`。
