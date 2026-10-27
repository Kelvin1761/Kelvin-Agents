# Tennis player card readability — 2026-10-27

Scope: dashboard rendering only. No model, stake, settlement, recommendation gate, database or tracking projection changes.

- Display each player separately with an explicit VS separator; desktop side by side, narrow mobile stacked. Keep ambiguous fixture labels intact rather than inventing player identities.
- Separate the model selection and market into a green panel. Label odds, model probability, and per-$1 simulated P/L individually. Explain excluded settled returns beside the timing evidence.
- Show every combo leg's selection, market and fixture directly; retain source records behind disclosure. Do not present one combo source label as the entire combination's fixture.
- Keep existing full record list, pagination, filters, URL state and actual wager separation.

Validation: 111 static template tests; repo quick checks passed. Browser preview verified desktop and 390px mobile, including player-name wrapping, single-card content, historical records, and combo leg layout. Preview retained 14,079 model records. Full immutable release gate is required by scoped save before deployment.

Base: f38d9333d933133c58d0fe1269b2a389e491454d.

First full-gate attempt: one unrelated existing test, `test_warm_loss_keeps_hot_intent_and_does_not_recreate_lost_volume`, failed because the fake helper had not created its marker within its 2-second worker budget. Other 1,756 shared tests passed; the notification-runtime module independently reran with 29/29 passing. No production or test timeout code was changed. Release must pass a fresh complete gate.

Second full attempt: the prior notification test passed, but two existing one-second supervision tests missed worker-ready markers under host delay (`prediction_artifact_hashing... [True]`, `full_archive_hash... [True]`). All 15 other suites passed, including 858 Tennis tests and 111 static-template tests. On 2026-10-28 the four supervision cases independently passed in 2.89s, with each preemption case reaching completion in 0.19s. No timeout or gate was changed; retry the complete immutable gate.
