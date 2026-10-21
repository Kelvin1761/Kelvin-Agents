# Stage 5 Tennis capture diagnostics — refreshed 2026-10-22

Restores the source/test payload preserved in WIP `8663249c` onto current
main `19e8fa05`; no difference in those two paths existed between the old
base `660b0952` and current main. The user explicitly approved this session's
completed engineering scoped releases on 2026-10-22. Existing full gates,
immutable checks, rollback and exact-scope requirements still apply.

The only behavior change adds the validated prediction ID to component and
decision-input provenance ValueErrors, retaining the original exception as
the cause. It does not skip rows, relax PIT/component warnings, change scoring,
build retrospective features, settle bets or grant promotion authority.

Historical WIP evidence: three contextual cases failed before source changes;
50 focused tests, 713 Tennis tests and quick gate then passed. These are old-base
results, not release evidence for this refresh. The preserved successful fixture
artifact digest is `760863df33638a1209d4b98302e031ef97dff816d4298c58175c7a3184f07dd7`.
Regression cases require unchanged valid bytes, original error cause, unchanged
inputs and no partial raw-artifact construction when another row fails.

Current read-only diagnosis found 105 central Tennis predictions, 105 decisions
and no settlements. Latest native forecast contexts for October 20/21/22 fail
with missing frozen feature evidence. Their original status-artifact hashes
still match central records: active component warnings, incomplete component
set, and incomplete observation coverage respectively. New diagnostics identify
the row behind the first two causes; they do not themselves fix those inputs
or the separate card-coverage cause. Zero qualified samples is not pilot success.

Fresh focused evidence/adapter regression passed 50 tests in 2.27 seconds
(`wc-run-s4tdy62g`). Fresh quick gate passed (`wc-run-9_oz5sp0`), including
both unchanged scoring goldens; existing AU sparse/new-field and HKJC stale
calibration warnings remain. Full gate and immutable release verification
remain open; neither old-base evidence nor quick checks authorize activation.
No live DB, old snapshot, evidence record, scheduler, ruler or ledger was edited.
