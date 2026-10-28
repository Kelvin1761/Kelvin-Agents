# Tennis card player identity — 2026-10-28

Request: remove the A/B labels and reserved space; identify the player behind a Yes/No "win at least one set" pick.

Confirmed example from read-only live DB: `tennis:prop:563234` is Daniil Ostapenkov, subject player 1988, match 22076 versus Patrick Maloney, recorded odds 1.50, blended probability 0.6383. The saved pick is Yes; the projection previously omitted its subject identity.

Changes: export subject ID/name only if the explicit subject belongs to the exact fixture. Legacy `player_win_a_set_<id>` keys are accepted only with fixture membership validation; invalid explicit subjects cannot fall back to a different identity. Combo legs resolve against their own fixtures. Preserve raw selections and all pricing, stakes, outcomes, timing and ROI logic. Frontend shows `Daniil Ostapenkov · 贏至少一盤`, handles No, and explicitly labels unresolved subjects; subject names are searchable. Remove A/B markup and all reserved marker spacing.

Verification: 9 tracking-export tests and 112 frontend tests passed; repo quick checks passed. Read-only live export confirmed the pictured record. Mobile 390px preview confirmed names align with the card edge and the exact named selection is visible. Complete immutable gate required by scoped save before activation.

Base commit: 52e12fe90b27a490f335a6c5b7be704da4fa0d33.
