# HKJC Matrix-Anchored Full Ranking ML

- Model: `HKJC_MATRIX_ANCHORED_LAMBDARANK_V1`
- Selected feature scope: `matrix_7d`
- Matrix / ML ranking share: `70%` / `30%`
- Development gate: `PASS`
- External 2026-07-15 gate: `FAIL`
- Production Matrix: unchanged

## Outcome

候選喺 development 有系統改善，但 external 未能確認穩定性；保留 research-only，唔推入 production。

### Raw-signal challenger

最佳 7D＋component＋raw 候選用 70% Matrix anchor：0-hit=0.2298、Winner Top2=0.4472、Top3 capture@5=0.6294、Winner Top3=0.5217。Development gate=`FAIL`，所以無用 external 結果補救或重新選模。

## Exact scorecard

| Metric | WF Matrix | WF Hybrid | External Matrix | External Hybrid |
|---|---:|---:|---:|---:|
| top2_zero_hit | 0.2547 | 0.2422 | 0.5556 | 0.5556 |
| top2_one_hit | 0.5217 | 0.5031 | 0.3333 | 0.3333 |
| winner_top2 | 0.4161 | 0.4286 | 0.1111 | 0.1111 |
| winner_top3 | 0.5342 | 0.5342 | 0.3333 | 0.5556 |
| top3_capture_at5 | 0.6294 | 0.6273 | 0.6296 | 0.5926 |
| top5_capture_at5 | 0.5602 | 0.5652 | 0.6000 | 0.6000 |
| competitive_ndcg_at5 | 0.5552 | 0.5574 | 0.5365 | 0.5255 |
| actual_top3_average_rank | 4.8944 | 4.8820 | 5.4444 | 5.3333 |
| log_loss | 0.2554 | 0.2533 | 0.2872 | 0.2828 |
| brier | 0.0695 | 0.0691 | 0.0770 | 0.0770 |

## Weak-race impact

- Baseline 0/1-hit weak races reviewed: 125
- Improved: 15
- Harmed: 12
- Rank 3 placegetter moved into Top 2: 10

## Interpretation

LambdaRank 以頭五名 graded relevance 學整體競爭力；blend 係全場一致規則，唔係逐場 micro tie-break 或 blind swap。Feature scope 同 blend 權重只由 development walk-forward 選擇，external meeting 無參與選模。極冷門／意外事件無可靠 point-in-time 標籤，因此本輪無用賽後理由刪除任何場次，避免主觀 hindsight exclusion。

詳細檔案：`development_candidate_scorecard.csv`、`final_comparison.csv`、`weak_race_review.csv`、`rank_movements.csv`、`feature_importance.csv`。
