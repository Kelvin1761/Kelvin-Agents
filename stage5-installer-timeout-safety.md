# Stage 5 installer timeout safety

Keep the existing installer deadlines, preflights and rollback policy. Before
rollback, terminate the owned installer process group on timeout and retain
bounded stdout/stderr with explicit installer stage markers. Never stop a
production scheduler, edit a database or retry an unverified cutover manually.

- [x] RED: timeout diagnostics and delayed child-write tests; success/nonzero parity.
- [x] Implement installer-only process isolation/timeout cleanup and safe stage markers.
- [x] Run focused tests and quick gate; preserve exact source/test/plan scope.
- [x] Full-gated source release and immutable approval/merge.
- [ ] Actual installed/calendar acceptance, separately proven.

Incident: `5e1fa7d8f27d` passed its clean full gate (1321.558 s), immutable
approval recheck and merge. Activation failed after 300 s, event
`20261023T175957.277860Z-bbfcc53f6903a8aa`; external restore and Git rollback
reported success/errors empty. Existing failure Telegram was delivered.
Reflog then records normal `merge origin/main` back to 5e at 17:59:59Z,
two seconds after rollback. HKJC startup log reports advancing to main. That
is not a successful installer event. Read-only installed/loaded all4+Central
probe is aligned/attention empty, but calendar verifier still blocks.

The exact command that stalled is unproven: timeout dropped captured output.
No installer/controller descendants remain at the inspection. Python's current
subprocess.run timeout kills only its direct child, a source-level gap; this
does not prove a particular orphan caused the incident. Preserve uncertainty.

RED: four failures for the missing installer-safe execution interface in
`wc-run-tw1f3swv`. Initial helper/activation tests passed 14 in 43.03 s
(`wc-run-xtymiqxs`); stage-marker/installer tests passed 26 in 74.39 s
(`wc-run-pz2xp0kj`). Final runner preserves check=False semantics: timeout
returns nonzero 124 with bounded diagnostics, so failed restore bookkeeping
continues rather than escaping the rollback block. Final activation regression
rerun passed **15 in 45.40 s** (`wc-run-hnarhg_9`) after this refinement. Final quick gate passed
`wc-run-ht_1frx6`; both scoring goldens unchanged, contract warnings retained.

All installer/snapshot/status/restore deadlines remain 120/300/60/300 seconds.
Only owned POSIX process groups are terminated; real launchd jobs are not
children of this group. New tests cover a TERM-ignoring child that must not
write after timeout or after its parent exits. Stage markers contain operation
names, not credentials or DB contents. Temporary outputs are externally routed.
This hardens cleanup and observability; it does not establish the original
timeout's precise cause or prove a successful production install.

Release preparation: exact five-path source/test/plan payload is preserved as
non-main WIP `bc232db0`. Rechecked main is still `5e1fa7d8f27d`, with no other
release controller live. Preview must include all five unmerged paths, select
the existing unified installer only, and retain full gate / immutable approval
and rollback requirements. Do not reclassify this as docs-only or retry the
previous failed manifest in place of a fresh verified candidate.

## Terminal release checkpoint

Release `e7e1d28e0076f9981b8bf135cfc1f42eb90c353f` passed its clean full
gate (1956.18 s), immutable approval/quick recheck and merged at
2026-10-23T22:08:39Z. Activation failed at 22:09:07Z at the active-run
preflight, not a timeout. New diagnostics retained the interpreter/SQLite/
active-run stage markers and the explicit busy guard. External restore and
Git rollback to 5e succeeded, both error arrays empty, event
`20261023T220907.489360Z-44c3eb8bab1c1148`. Primary failure Telegram was
already sent. Session84278 is terminal1, PID17139/17137 absent.

Fetched main/production subsequently advanced to
`9f103c277769062c402ed4a409ac370b0f59a7d8`, containing e7; later AU changes
were observed only, not approved by this chat. Current read-only process probe
finds no controller or matching domain scheduler. Actual all4/Central loaded
state is aligned, attention empty, but installed calendar still blocks.
Neither source in main nor an idle probe constitutes installer acceptance.
No refresh/retry/downgrade was attempted: refresh explicitly refuses a release
already contained in main, and activation correctly pins the old manifest SHA.

See `stage5-forward-activation-reconciliation.md` for the forward-only path.
Kelvin explicitly approved that workflow on 2026-10-28; the former decision
hold is resolved. The read-only implementation checkpoint found changed
installer/dependency bytes and missing four-domain exact-target deployment
provenance at observed main/production `51ea46ef`. Kelvin also authorized one
independent read-only subagent review. Retain all evidence; do not infer
installation authority from source in main, a test pass or the review starting.
No old activation retry, duplicate alert, invented source delta or manual install.
