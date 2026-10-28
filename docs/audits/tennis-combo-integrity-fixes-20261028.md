# Tennis combo integrity fixes — 2026-10-28

Base: 5382677c855c9519f00a0fde2da4a309f7891b26.

## Changes

- `_upsert_combo_tracker` updates only PENDING rows with no settlement timestamp. Final rows retain all original odds, stake, legs, outcomes, timestamps and P/L; skipped rows no longer count as synced. Settlement also skips timestamped records.
- New completed combination settlements persist the actual WON/LOST result for each leg. Missing historical per-leg evidence exports as unverified, never an invented PENDING result. Explicit saved leg states remain authoritative. Retirement/unsupported settlement policy is unchanged; missing evidence remains unverified.
- Search indexes every leg's fixture, selection, subject, market and translated market label.
- The eight inconsistent historical financial records below remain untouched in SQLite. Their projection carries a verification note and no usable unit P/L. Complete combo stakes/P&L are checked against the recorded odds/outcome with a 0.02u absolute rounding tolerance (relative tolerance 1e-6). No price, stake or result is reconstructed.

## Evidence

39 targeted Python tests and 117 frontend tests passed, including whole-row immutability for WON/LOST/VOID and already timestamped records, pending refresh, actual per-leg settlement, missing versus explicit leg states, search of the second fixture, and ROI exclusion for inconsistent finances. Repo quick checks passed. Complete immutable release gate remains required before activation.

Read-only before/after export retained all 14,142 IDs. Eligible settled observations remained 2,130 and aggregate per-$1 P/L remained -251.0427; exactly eight historical anomalies were flagged with no projected unit P/L. The live DB was not modified. Mobile 390px preview found three combinations when searching Roberto Carballes Baena; expanded source details showed 待核實 for missing leg outcomes, with no horizontal overflow.

## Historical records requiring reconciliation

These are model-tracking units, not confirmed actual wager balances. Original saved values are listed; original quote/stake evidence is required before any repair. Current records are excluded from point-in-time combo ROI already.

| DB ID | Source date | State | Saved stake (u) | Saved odds | Saved P/L (u) |
| --- | --- | --- | --- | --- | --- |
| 88 | 2026-05-10 | LOST | 1.5 | 3.2752 | -0.25 |
| 94 | 2026-06-17 | LOST | 4.0 | 3.408 | -5.0 |
| 95 | 2026-06-17 | WON | 4.5 | 2.7264 | 8.632 |
| 96 | 2026-06-17 | WON | 3.5 | 3.7352 | 13.675999999999998 |
| 98 | 2026-06-17 | LOST | 1.5 | 12.2688 | -5.0 |
| 99 | 2026-06-17 | LOST | 1.5 | 11.8368 | -5.0 |
| 100 | 2026-06-17 | LOST | 1.0 | 7.7816 | -5.0 |
| 101 | 2026-06-17 | LOST | 1.0 | 5.0 | -5.0 |
