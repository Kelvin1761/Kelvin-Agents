# Tennis forward result provenance recovery

Base: `2ed4feac796a96e99a021e74413cf9ac1e063263`. Recovered in isolated
`/private/tmp/codex-sort-tennis-20261014`, without production DB writes,
provider requests, wagering, commit, push, install, or deployment.

## Existing integration and recovered scope

The earlier legacy-worktree audit missed the current adapter when searching:
`research_adapter.record_research_settlement` already calls the current
`research_evidence.build_settlement_artifacts` v2. The current CLI already
invokes that observer after native settlement and research retry. Those hooks,
the v3 prediction producer, and current immutable receipt contract are retained.
Neither the superseded v1 settlement builder nor v2 prediction builder nor old
probability metadata is ported.

The recovered changes retain fetched provider result records in
`raw_api_responses`, carry their IDs through result inserts/upserts and local
history resolution, and retain TennisExplorer's fetched HTML with its parsed
result projection. TennisExplorer history now retains each day's actual
response instead of a summary placeholder. TennisMyLife retains the considered
CSV records, and the event resolver retains its fetched response. Result rows
continue to use the existing native identities, matching and settlement rules.

The research observer now rejects disagreement between native result winners,
including a disagreement hidden behind the existing preferred-provider/aces
priority. Native betting-ledger settlement priority is unchanged. Consistent
results still use the existing canonical selection. Formal research capture
still fails closed on absent raw provenance, participant/winner mismatch,
chronology errors and differing raw/result provider identities.

## Verification

`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q` over these six files:

- `tennis-wong-choi/tests/test_research_adapter.py`
- `tennis-wong-choi/tests/test_result_matching.py`
- `tennis-wong-choi/tests/test_tennisexplorer.py`
- `tennis-wong-choi/tests/test_tennisexplorer_history.py`
- `tennis-wong-choi/tests/test_ledger.py`
- `tennis-wong-choi/tests/test_stage5_settlement_evidence.py`

Result: **88 passed**. `./檢查.sh --quick`: **all checks passed**.
`git diff --check`: passed. Full delivery suite remains the release owner's gate.

The new forward integration fixture mocks only HTTP and clocks, and runs the
real TennisExplorer parser, ingestion, raw-row store, current v2 adapter,
immutable artifact writer and Central receipt consumer against an isolated DB.
It verifies exact retained response JSON SHA-256, frozen forecast/decision
identity, retry idempotence, and independently verified outcome counts. Missing
raw data, contradictory raw winner, and conflicting provider winner produce
unverified evidence with zero verified outcomes. Altered captured raw artifact
bytes fail the receipt consumer's hash check.

## Limits

No predictive improvement is claimed. Scores, weights, thresholds, tracker
point-in-time gates and historical records are unchanged. This retains the
payload representation supplied by existing providers (decoded HTML and parsed
API/CSV records), not original network transport bytes; hashes pin exact
stored response JSON and frozen artifact bytes. Providers returning only
parsed rows retain that projection. Existing `local_history_resolver` and
`sportsbook_event_resolver` aliases may differ from the original raw provider;
those remain unverified for formal evidence rather than being relabeled.
Absent or conflicting source information is not reconstructed. No live
acceptance or research-to-production promotion is claimed.
