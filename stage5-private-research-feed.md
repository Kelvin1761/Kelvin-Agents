# Stage5 private research projection — unfinished source

This branch starts at e6e45aa1d131f5e9e3787c340304e7c4ddfc1587 and implements an explicit receipt publisher, private API and actual Dashboard template view. It does not complete Task7 or Stage5.

The foreground Python publisher uses the existing receipt presentation verifier, one HTTPS POST, no redirects and the existing WC_SYNC_TOKEN. There is no new credential, background schedule or live upload. Ambiguous responses require reconciliation, never automatic retry.

The API requires configured token authentication for both reads and writes; same-origin access does not bypass authentication. Only dedicated WC_STATE projection-cache keys are used. Publication blobs are content-addressed and checked on reads. The latest pointer is best effort, not atomic cross-writer CAS, monotonic ordering or canonical evidence history. Concurrent publication can regress the pointer; eventual visibility can temporarily return unavailable. No ledger or authoritative research-history writes are involved.

Receipt lineage is publisher-reported. API body-hash validation does not independently verify receipt lineage, source safety, process liveness, current health or promotion eligibility. Explicit freeze state, supporting arrays and bounded numeric counts are required. Timestamps over five minutes ahead of server time are rejected before any cache write. The view displays as-of dates and uses text-only rendering for private evidence.

## Evidence and remaining work

- Initial missing-module/API tests failed; initial implementation passed 12 Python publisher tests including actual Node API round-trip and ambiguous-response single-attempt tests.
- Same authorized reviewer found missing freeze state and future-date pointer poisoning. Actual API regression failed before correction; corrected API tests pass. Reviewer subsequently confirmed the two narrow source fixes, without independent tests or release approval.
- Full Dashboard npm test command includes the new API and actual-template DOM tests. All three suites pass after correcting the test harness's text traversal; the real template clears stale data and renders hostile hypothesis strings as text.
- Quick check and git diff check pass; scoring goldens remain unchanged. No full repository source gate or immutable approval has run for this branch.
- Actual-template Playwright browser checks passed at desktop 1440x1000 and mobile 390x844, using the generator's real CSS with synthetic embedded data and intercepted requests only. The visible header button opens the dialog, existing credential prompt is exercised, freeze warnings remain visible, hostile hypothesis markup stays text, denied access clears prior evidence, and no page errors occur. Screenshots were inspected; no live requests or credentials were used. Log: /private/tmp/stage5-dashboard-browser.log; screenshots: /private/tmp/stage5-research-desktop.png and /private/tmp/stage5-research-mobile.png.
- The same authorized independent reviewer completed the full seven-path source review at local merge 6a6b9a7edceb3de8699fc35afb114f24d29bf5b8 (plus this plan's browser-evidence addition), finding no must-fix. This was source inspection only, not independent test execution, release approval, native authorization or production acceptance.
- Fresh Central dry-run against fa31d4568542244e7fe6e4c28c675321097f69b6 proves exactly seven release/activation paths, full gate, all four code-sync domains, Dashboard deploy, installers empty and no manual action. The three intervening HKJC documents are observed only and excluded from this slice. Production was observed at fa31d456 with only its two existing allowlisted mutable mapping files dirty; no other release controller was observed.
- Fresh full/immutable gates and authorized private deployment/publication acceptance remain outstanding. The next action is the normal exact-scope controller, retaining its SHA/ref/lock/rollback checks. Manual publisher source is not proof of unattended bounded execution.
- No deployment, live publication, Telegram, native job, model, database or historical evidence mutation has been performed.
