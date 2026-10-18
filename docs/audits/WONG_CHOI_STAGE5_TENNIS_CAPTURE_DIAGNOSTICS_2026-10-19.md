# Stage 5 Tennis capture diagnostics — source-only checkpoint

## Scope and authority

Based on approved main `660b0952d952cf57ca9e35f55dd8a96f005a4c9e`.
The only behavior change adds the validated prediction ID to component and
decision-input provenance `ValueError` messages, retaining the original cause.
There is no new acceptance rule, partial capture, source repair, scoring,
family/ruler change, scheduler, ledger, model promotion or deployment.

This is an isolated non-main checkpoint. A complete repo release gate,
current-main/SHA recheck and separately authorized scoped release are still
required. It is not part of the 36-file reader release and must not be bundled
into that release. The standing research-only heartbeat allowlist does not
authorize this Tennis production-source path.

## Reproduction and change

Existing capture errors such as `incomplete Tennis component set` omitted the
prediction ID, so the operator could not identify which row stopped the card.
The separate prerequisite audit records why an empty card must not be confused
with a nonempty capture failure, and why the existing strict source boundary
must remain in place.

The small `try/except` around `_components` and decision-input projection now
raises, for example, `Tennis prediction 202: incomplete Tennis component set`.
It does not catch-and-continue, remove a forecast or return earlier valid rows.
All checks and artifact-building code remain unchanged.

## Evidence

- Before modifying source, the complete valid fixture artifact mapping digest
  was measured as
  `760863df33638a1209d4b98302e031ef97dff816d4298c58175c7a3184f07dd7`.
  A regression test pins those same bytes after the change; this is an
  engineering fixture, not live model-performance evidence.
- RED: three new contextual-error cases failed and 12 tests passed, with
  unchanged source. Cases cover a neutral-only component set, an effectful
  warning and a missing decision input.
  External scratch: `wc-run-n0hi2g_w`.
- GREEN: evidence plus research-adapter suites passed **50 tests in 0.76s**.
  They assert the ID and original cause, no partial raw-artifact construction,
  unchanged input objects and unchanged successful artifact bytes.
  External scratch: `wc-run-2apkgcxr`.
- Complete Tennis suite, using its actual package working directory, passed
  **713 tests in 150.24s**. Command from `tennis-wong-choi/`:
  `PYTHONDONTWRITEBYTECODE=1 python3 ../.agents/scripts/wongchoi_external_run.py -- python3 -m pytest tests -q -p no:cacheprovider`.
  External scratch: `wc-run-o_dasrt7`.
- The first manual full-suite invocation from the repository root failed
  collection (`No module named 'scripts'`). The repo's `run_tests.sh` runs the
  Tennis suite from its package directory. Repeating that correct invocation
  passed; no test was changed or deselected to fix collection.
- `./檢查.sh --quick` passed, including both unchanged scoring goldens and
  actual AU/HKJC 60-meeting data-contract checks. Existing AU sparse/new-field
  warnings remained warnings. External scratch: `wc-run-uxj3f_iu`.
- The host Python emitted its existing urllib3/LibreSSL compatibility warning;
  no dependency or runtime change was made.

All test scratch was routed to the mounted external archive. Tests use isolated
DBs; no live DB, native snapshot, evidence record or external ledger was changed.
The complete repo full gate has **not** been run for this diagnostic candidate.
Task 8 remains not ready; no additional qualified sample or promotion authority
is inferred from the new diagnostics or the fixture tests.
