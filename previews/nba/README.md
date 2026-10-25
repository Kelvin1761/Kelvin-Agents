# NBA dashboard design preview v2

User-directed revision: use existing Wong Choi blue branding, embed period controls
inside the dashboard, show a complete today/history tracking dashboard, and display
$1 per simulated bet instead of unit notation.

Standalone interactive prototype. All fixtures (games, rosters, prices, model EV,
recommendations, scores and returns) are fictional. No production template,
model, scheduler, settlement service or D1 ledger is connected or modified.

Open `index.html`, or serve this directory locally:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory previews/nba
```

## Review surfaces

- Today: embedded Today / Week / Month / All controls, tracked bet count, separate SGM and leg hit rates, ROI, dollar P&L chart, settlement progress and individual bet records.
- History: same dashboard, per-day performance and expandable per-bet leg results. Mobile daily cards retain bet count, SGM, leg counts, profit and ROI.
- Analysis: blue styling, Noto Sans HK, SVG jerseys, Chinese props and expandable explanations.
- Demo settlement: finish one fictional pending game, update leg outcomes, then recompute both today and history summaries. Reset restores the fixtures; reload also resets. No requests to an external ledger.
- Every displayed stake is $1 per bet. Dollars are a display convention for the simulated stake, not actual account money.

## Definitions

SGM rate = winning / decided combinations. Pending and unpriced combinations are
excluded. Leg rate uses only verified won/lost legs; void/pending legs are excluded.
A verified leg in an unpriced SGM can count toward leg accuracy while its SGM return
remains unknown. ROI = settled dollar profit / settled $1 stakes. Uncertain void
repricing is unpriced, never silently treated as a zero-profit refund. Dollar sums
are rounded at cent precision before percentage display.

Sydney dates; week starts Monday. Chart and metrics use the selected period.

## Browser verification

- 320 / 375 / 390px, all three tabs: no horizontal page overflow or overflowing player names (`layout-checks.json`).
- Period controls checked against independent fixture totals (`interaction-checks.json`).
- First demo settlement: SGM 4 中 3 = 75%; legs 12 中 11 = 91.7%; profit +$3.41.
- Second demo settlement: SGM 5 中 3 = 60%; legs 14 中 12 = 85.7%; profit +$2.41; ROI 48.2%.
- History synchronises to 8 中 5 / +$4.11 / 51.4% for the week after both demo settlements.
- Dashboard filter buttons and footer controls have 44px mobile touch targets. Tab keyboard navigation and focus styles retained.
- Screenshots in `screenshots/` reflect v2; v1 remains recoverable in commit a7df438a.

| Initial period | Tracked | Decided | Wins | Leg hits / decided | Net dollars | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Day | 6 | 3 | 2 | 8 / 9 | +$2.06 | 68.7% |
| Week | 9 | 6 | 4 | 15 / 17 | +$3.76 | 62.7% |
| Month | 11 | 8 | 5 | 20 / 23 | +$4.26 | 53.3% |
| All | 12 | 9 | 5 | 21 / 25 | +$3.26 | 36.2% |

Repository checks: `./檢查.sh --quick` PASS; full `./檢查.sh` PASS (all suites, including 571 NBA tests). Full run used the permitted environment for the existing process-state checks; no test or production code was changed. UX heuristic audit PASS with generic typography/marketing warnings; no purchase CTA, discount anchoring or gratuitous effects were introduced. Existing data-contract stale-baseline warnings were not recalibrated for this preview. Production release is explicitly excluded until the user has reviewed the revised visual preview.

## Later integration

Reuse immutable published BET snapshots and verified final settlements. Freeze each
simulated $1 entry at its publication price, deduplicate reruns, preserve correction
lineage, and keep research performance / actual personal betting separate. Never
infer a historical bet from post-result analysis or invent a missing SGM price.
Layer C and the EV release policy remain unchanged.
