# NBA dashboard design preview v1

Standalone, interactive visual prototype. All games, player/team assignments, prices,
EV figures, recommendations and returns are fictional fixtures, not current NBA
information or measured model performance. The banner remains visible on all views.
No model, production dashboard template, scheduler, D1 ledger or deployment changes.

Open `index.html`, or serve this directory locally:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory previews/nba
```

## Review surfaces

- Today: mini SVG jerseys, Chinese prop labels, recent hit counts, formal/research/waiting states, expandable explanation.
- History: won/lost/pending/unpriced examples; pending and uncertain void repricing excluded from simulated returns.
- Performance: day/week/month/overall filters, flat 1u fictional records, cumulative period P&L chart and explicit denominator.
- Desktop: two columns; mobile: one column, long player names wrap.
- Typography: Noto Sans HK via Google Fonts; PingFang HK/system fallback when unavailable. Production font delivery/subsetting remains a later integration task.
- Sports labels are illustrative; only the three NBA tabs, explanations and period filters are interactive.

## Verification

Browser checks at 320 / 375 / 390px across all three views found no horizontal page overflow; no overflowing `.player` text. Desktop inspected at 1440px. Screenshots in `screenshots/`.
Keyboard Left/Right navigation of the tablist verified. Six key text/background contrast pairs measured 5.18:1–9.17:1 (all exceed 4.5:1). Buttons have visible focus; skip link and semantic tab controls included. Automated UX heuristic audit PASS with warnings: several are marketing heuristics inapplicable to a sports analysis UI (discount anchoring / primary purchase CTA / adding gradients). No promotional anchoring or betting CTA was introduced.

Fixture calculations checked through rendered UI:

| Period | Decided combinations | Wins | Net units | ROI |
| --- | ---: | ---: | ---: | ---: |
| Day | 2 | 1 | +0.46 | +23.0% |
| Week (Monday start) | 5 | 3 | +2.16 | +43.2% |
| Month | 7 | 4 | +2.66 | +38.0% |
| Overall | 8 | 4 | +1.66 | +20.8% |

Quick repository check PASS. Full `./檢查.sh` ran every suite: all suites except NBA passed on the first sandboxed run; four existing reflector relocation tests failed because sandbox denied `ps`. Re-running the identical full NBA suite outside that restriction passed all 571 tests (8.63s). No production code or tests were changed to obtain this result. The original full-command exit remained nonzero; its four environmental failures are resolved by this suite rerun. Existing data-contract stale-baseline warnings were not recalibrated as part of a visual prototype.

## After visual approval

Integrate actual immutable published BET snapshots and verified final settlements;
keep research performance and actual personal bets separate. Freeze 1u paper entries
at their publication price, deduplicate reruns, handle correction lineage, define void
rules without guessing repriced SGM returns, add daily/weekly/monthly/overall exports.
No historical recommendations inferred from post-result analysis. Existing Layer C
and EV release policy remain unchanged. Production release requires the user's preview approval.
