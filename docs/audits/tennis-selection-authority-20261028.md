# Tennis named selection authority — 2026-10-28

Regression: the prior subject-name enhancement prefixed Nick Hardt to the stored selection `Juan Manuel La Serna (-1.5)`, making the handicap ambiguous.

Read-only DB verification: prop 563066, match 22053, recorded odds 1.91, blended probability 0.4871; `selection` is `Juan Manuel La Serna (-1.5)` and Sportsbet `feed_selection_name` is `Juan Manuel La Serna -1.5`. The subject player is Nick Hardt because `props/daily.py::_log_spread` canonically records both sides against player A's raw margin, with the B side on the complementary under. A spread subject is a model reference, not necessarily the selected player. Do not change the stored subject or settlement to fix a display issue.

Fix: preserve all named source selections exactly. Fill missing subject context only for bare Yes/No win-a-set picks and bare Over/Under individual ace/double-fault/game totals, where the subject denotes the actual player. Match totals remain unprefixed. The shared formatter covers standalone cards, combo leg previews/source disclosures and native actual-bet cards.

Validation: 115 frontend tests passed, covering positive/negative game and set handicaps, first-set markets, combo legs, continued named Yes/No display, individual and match totals. Repo quick checks passed. Browser preview of the exact fixture shows only `Juan Manuel La Serna (-1.5)` at 1.91 / 48.7%. Full immutable release gate is required before activation. No pricing, stake, result or ROI calculations changed.

Base: a1eb8bb954dbfcc60113ad372db385d31978bdd1.
