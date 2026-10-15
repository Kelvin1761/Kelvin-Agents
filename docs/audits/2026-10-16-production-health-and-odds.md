# Production health gaps: Gatton/Penola, 16 October 2026

## Evidence and diagnosis

Investigated from main `9f0360c7d57a72f6aedc86241a0aaf63302364c0`, in an isolated worktree. Sydney time.

- Production `run-evening-20261015T220005.json` ran 22:00–00:29. Gatton (8 races) and Penola (7) had `odds-snapshot: missing`, no Odds.json or odds_history.json, and `WinOdds: - / PlcOdds: -` in all inspected form guides. Bathurst and Taree had numeric prices.
- The same run reported `status: ok`, `errors: []`, `dashboard_validation.ok: true`, and successful verified deployment. The Central AU attempt also reported `succeeded` with zero warnings. Thus process/deployment success did not establish product completeness.
- Cached source HTML contained W/P placeholders. A fresh rendered browser inspection of Gatton R1 (`453266/3450878`) and Penola R1 (`453271/3450929`) at approximately 01:30 also contained W/P, not numeric prices. This establishes source unavailability in those inspected races; it does not establish why the provider withheld prices, or that every current race page was checked again.
- Existing local odds checks were disabled before 11:00. They accepted an empty snapshot object as proof of capture. `morning-refresh` tags bypassed date parsing. Existing passing test fixtures encoded this same false assumption.
- A refresh callback without an exception was counted as successful without checking the resulting artifact. Morning odds were appended to history, but dashboard market prices came from markdown. A price-only refresh could therefore leave cards unchanged. The parsed-meeting cache also did not track odds_history.json.
- Central attention surfaced running-job overruns and aggregate SLO failures but did not explicitly flag the latest terminal `partial`/`failed`/`blocked` run in every domain.

## Implemented controls

1. Require finite decimal win/place prices greater than 1; empty snapshots, W/P, NaN, infinity and booleans fail. Interpret timestamps in Sydney, including historical naive timestamps. A tag cannot override its date.
2. Diagnose missing local odds immediately; retain the 11:00 deadline specifically for race-day freshness and going-refresh audits.
3. Independently inspect the published dashboard's actual per-race horse prices. Partial runner coverage is visible. Read failure means verification failed, never healthy.
4. Record unsuccessful morning capture, check refresh postconditions, and return a partial run while observed odds gaps remain. Recovery clears the latest observation per meeting. Missing market prices remain separate from independent model/scoring readiness; valid analysis can still be published.
5. Transport the latest eligible captured prices directly to existing dashboard horse IDs, with capture timestamp. Track the history file in cache fingerprints. Scores, ranking, earliest-market reference probabilities, and immutable prediction snapshots are not modified by this display enrichment.
6. Display an explicit unavailable message instead of silently omitting the market line.
7. Flag the latest terminal fault/error across AU, HKJC, Tennis and NBA. `健康.sh` now includes immediate four-domain run checks and independent AU local/live odds checks in its exit status.
8. Add incident regression tests and replace empty healthy fixtures with numeric evidence.

## Four-domain prevention system: next coverage requirements

These are requirements for further work, not claims of implemented coverage. Reuse the current Central control plane and domain health checks; do not merge the models.

| Boundary | Required evidence | Failure action |
| --- | --- | --- |
| Provider → extracted data | Expected event/runner IDs, timestamps, units, nonempty values, field coverage; distinguish unavailable, delayed, corrupt and unknown | Quarantine corrupt input; bounded retry for unavailable data; expose affected event/field |
| Extracted data → model | Per-event contract, neutral/default rates, score provenance, scratchings, point-in-time availability | Block affected predictions on critical model-input failure |
| Model → report/CSV | Same runner IDs and ordering, reconciled contributions, finite scores, input and code hashes | Block inconsistent artifacts; retain known-good baseline |
| Report → public dashboard | Verify actual displayed fields, event counts, timestamps and projection hash after deployment | Mark product degraded; recover the smallest affected component and verify again |
| Predictions → settlement | Immutable prediction linkage, authoritative results, complete settled records, no duplicate settlement | Hold incomplete settlement; never invent results or auto-apply external ledger proposals |
| All stages → Central | Separate execution/data/model/display/settlement readiness; latest failed slot must remain visible through unrelated dormant/health runs | One incident keyed by domain/event/field, notify on meaningful transition, close only with passing evidence |

Priority follow-ups:

- Extend artifact-level checks equivalent to AU's to HKJC, NBA and Tennis with their own expected-event discovery and schedule-aware deadlines. Current cross-domain status changes detect terminal run failures; they do not prove all four domains' artifact correctness.
- Persist open incidents independently of the latest run. A later unrelated dormant run must not erase an unresolved prediction/settlement failure. Record first seen, event/field, owner, input/code/artifact hashes, recovery attempts and verified resolution.
- Add small real provider fixtures and fault-injection tests at each boundary: successful HTTP with empty fields, renamed keys, wrong units, timezone rollover, stale cache, partial runners, swallowed import errors, missing dependencies, and unavailable providers. Tests must assert the business invariant, not merely call success or file existence.
- Run a read-only canary on the actual installed production interpreter/checkout before activation and verify public output after deployment. Full offline tests cannot establish that live data is available.
- Require incident fixes to include a regression that fails on the previous code, plus checks for the same failure class in the other domains. Preserve evaluation rules and prohibit opportunistic model retuning during an operational repair.

## Initial cross-domain observations

Central read-only status at 01:29: AU latest succeeded despite the odds gaps; HKJC dormant; Tennis latest daily succeeded; NBA latest pregame partial. The 30-day NBA run SLO was 58.8% (110/187 healthy), versus the 95% target. This is an operational signal, not a measure of prediction accuracy. Evidence audit passed; all 666 recorded production decisions were traced. Registry stages were AU/HKJC production and Tennis/NBA shadow.

D1 backup status was stale (~46 hours) with a previously verified local restore and WARM copy. HOT free space was ~25 GiB; WARM was available. COLD catalog coverage was 14/17, with a backlog. These are separate findings, not repaired by the odds changes. Runtime alignment was not configured in that invocation; installed plist alignment must be checked with production-root mappings before claiming activation.

## Reproduction and validation commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  .agents/skills/au_racing/au_daily_auto/tests \
  .agents/skills/shared_wong_choi/tests/test_central_status.py \
  Horse_Racing_Dashboard/tests/test_au_market_odds_transport.py -q -p no:cacheprovider
./檢查.sh --quick
./檢查.sh
./健康.sh
```

Source odds cannot be reconstructed retrospectively. Do not backdate a later quote or fill missing prices with predictions. The existing morning and midday refreshes are the recovery opportunities; success must be established from new numeric snapshots and the published cards.
