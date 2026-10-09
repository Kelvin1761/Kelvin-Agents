# Pending release gate recovery — 2026-10-09

Kelvin authorized resolving the current pending queue, refreshing expired scopes,
and approving releases through the existing controller. No gate bypass or model
promotion was authorized by this engineering repair.

## Reproduced blocker

Approval of NBA `e17d187395a7` failed its clean-clone full gate. A direct full
gate on the identical commit identified one failing suite: Dashboard Python,
`test_hkjc_horses_get_the_ranking_matrix_too`. Latest materialized meeting
`2026-10-11_ShaTin` contained 138 report horses but only 128 parsed matrices.
All ten missing matrices were in Race 4: Logic no longer contained
`python_auto.grade_transparency` (one report horse was absent altogether), while
the report still carried complete six-column raw/display weighted matrices.
This is observed source state, not proof of which process replaced the sidecar.

## Exact repair

Parser keeps structured sidecar precedence. When sidecar transparency is absent,
it reads the horse's own report matrix. Six-column rows distinguish display from
raw score; the raw score is paired with the recorded weight and contribution.
Legacy five-column rows remain supported. No engine constants, scores, weights,
rankings, production data or ledger are changed or recomputed. Missing report
values remain missing, never fabricated.

## Evidence

New isolated regression tests first produced 2 failures / 2 passes on unchanged
parser, then all four passed after repair. Combined existing live parity and
new regression selection: 69 passed, 12 skipped. Command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=Horse_Racing_Dashboard/backend python3 -m pytest Horse_Racing_Dashboard/backend/tests/test_hkjc_matrix_report_fallback.py Horse_Racing_Dashboard/backend/tests/test_parser_au_structured.py -q -p no:cacheprovider
```

Full release gate and clean approval gate are still required. This report does
not claim deployment, live prediction acceptance, model improvement or Stage 5
completion. Immutable release manifests/events are authoritative for delivery.

## Historical queue reconciliation

`8b93e87f6a95` and `165f923a1aa4` are ancestors of main `1973e53ef32b`.
An initial erroneous rejected bookkeeping classification was corrected through
append-only merged events; original events and branches remain intact.
`9c055061ef6c` is not an ancestor, but all 18 non-index scope blobs equal main;
every old index line remains, with only newer experiments added. Its pending
record was marked superseded, without deploying again.

HKJC `83735115d929` remains pending: its own experiment records state Stage-4
REJECT for outer weights / early-draw candidate. Human approval is not evidence
that a failed statistical gate passed. Other original releases remain pending
until exact-scope refresh, gates and controlled activation complete.
