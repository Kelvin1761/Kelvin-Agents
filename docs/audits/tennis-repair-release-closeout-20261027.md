# Tennis correctness delivery — 2026-10-27

## Activated identity repair

Production checkout verified at `41730c2f559c2a20d574eec9d37ee5cb4931d502`; Central records merged and activation_succeeded events. Original manifests 6dfe0cec3863 and 42e52bd96068 have release_superseded events.

The live fixture audit proved one legacy provider-key mutation (fixture 21718). A consistent external SQLite backup passed quick_check before exact-plan quarantine. That fixture is now DISPUTED. All original match, prediction, prop, CLV, result, odds, feature and history row counts were preserved. The migration seeded 13,016 result observations at actual observation time `2026-10-26T23:35:30.422Z`; it did not backdate their availability. Both match-ID lookup indexes are installed. Details and backup path: `tennis-live-identity-repair-20261027.json`.

## Follow-up release candidate

Saved source head before this closeout: `f55fcd89` (history repair `8e0a2385`, merge with activated main `e4ec4e0b`, pricing-evidence report `f55fcd89`). Earlier evidence and history stages were saved as `a78dc787` and `4c4ed7c9`.

This candidate combines coherent current market captures, immutable pricing-time evidence, read-only feature assembly, historical input guards, current-slate integrity checks, market-contract verification, history generations/source-context audit, round normalization and generated strategy reference. No feature weights, stake limits, evaluation rules or promotion thresholds were tuned. Cross-provider canonical selection remains diagnostic. Rejected WTA research is not promoted.

Latest native integration: **858 tests passed**; final focused history identity tests: **9 passed**. Quick checks and generated-reference check passed. A working-tree full run passed all 16 suites (855 Tennis tests before the final cross-provider dedup reproduction/fix). The immutable final-SHA full gate, merge and activation are still pending at the time this closeout is prepared; only Central events can confirm them.

Source-context audit proves 88 inconsistent legacy rows in the frozen source, leaving unknown evidence explicit. A live repair must recalculate the plan against the live DB after follow-up consumers are activated, create another checked backup and preserve complete row state. It must not blindly apply the frozen research IDs or rewrite old forecasts. No live history quarantine or Elo rebuild is claimed here.

## Performance interpretation

The fixed-corpus raw paper ROI remains **−14.58% over 1,003 settled records**. Formal evidence falls to zero because missing historical pricing receipts are UNKNOWN, not reconstructed as verified. This is evidence correction, not a profitability improvement. The component and Elo input replays quantify behavior changes without using outcomes to tune parameters; they are not out-of-sample performance trials. See the pricing/history/Elo audit JSONs for commands, corpus hashes, ablations and limitations.

Remaining model work starts with verified forward data and independently registered comparisons. The frozen Elo shadow's minimum sample cannot be bypassed. Unmapped historical event identities and older season-file availability remain unresolved evidence gaps.
