# Central review recovery after production preemption

The evidence repair in `37f67d8a` passed both full release gates and was activated
for all four domains. The installed AU 10:00 job then completed at 10:21 Sydney
with no errors or warnings, a verified dashboard deploy and 516 mirrored copies.
All 1,024 current AU mirror files matched after that refresh.

The next native Central acceptance attempts were preempted by ordinary HKJC
scheduler activity. The AU corpus worker retained all seven pages for 698
records and 30,102 references but was preempted after 486.556 seconds. Its next
attempt was preempted after 31.857 seconds. This is correct production priority,
not a reason to remove locks, shorten the corpus or extend a worker deadline.
The old controller tried every domain once and ended the pass; the next pass
repeated even domains that had already completed.

The controller now retains completed domain outcomes and retries only a
`deferred`/`preempted` outcome whose status is `production_active` and whose
cursor did not advance. It waits through the existing shared-lock observer;
it does not pause production or hold a production lock while waiting. The
original aware review clock and ruler bindings stay fixed across attempts.
Data failures, timeouts, other resource failures and already committed work
are terminal for this pass.

A native attempt still receives at most 900 seconds. The complete pass retains
the original maximum allocation, four times the per-domain timeout (3,600
seconds with the production contract), including waiting and retries. Remaining
time is passed down when smaller. An interrupted domain may consume another
attempt from that shared allocation; completed domains consume no new attempts.
There are at most eight attempts per domain. A pass still cannot claim success
unless every domain has a successful native result. The installer and its
strict successful four-domain receipt requirement are unchanged.

The canonical run receipt retains each attempt outcome. Status verification
checks bounded history, agreement with the final outcome and that intermediate
attempts were uncommitted production preemptions. Older receipts remain readable.
This history does not grant model-promotion, notification or sample authority.
No model, ruler, fixture size, source guard or native replay implementation changed.

Validation: 33 Central review regression tests and the required quick checks
pass. Coverage includes same-clock retry, no rerun of completed domains,
production waiting, attempt limits, the original total budget, reduced remaining
attempt time, terminal data/time/resource faults and rehashed inconsistent
history. Full release and immutable checks remain required before activation.

The real HKJC corpus also reached its unchanged 900-second deadline. Its
supervisor measured 259.627 user CPU seconds and 281.799 system CPU seconds;
all 11,186 references are local, so this is not a Drive-path relocation issue.
A 90-second supervised diagnostic on the complete, unchanged source recorded
193,158 resource checkpoints and about 772,000 lock-file opens. Resource
checking consumed 41.472 seconds, including 32.273 in production-lock probes.
The diagnostic timed out intentionally and confers no acceptance authority.

The lock observer now reuses at most sixteen process-local descriptors. Every
probe still stats the path and descriptor, checks write access, and performs a
fresh shared-lock attempt followed by unlock. No lock remains held between
probes. A renamed or deleted path cannot conceal a writer holding the prior
inode; replacement interrupts the current check. Symlinks, permission errors,
failed unlocks and changed descriptors fail closed. Extra paths above the
cache bound are checked with temporary handles. Copies start with an empty
cache, and descriptors are excluded from runtime serialization.

A three-run, 5,000-probe comparison on the same four local lock files measured
median 0.537923 seconds for the original observer and 0.373421 seconds with
handle reuse (30.6% less elapsed time in this microbenchmark). This does not
claim that the whole native pipeline now fits its deadline; a successful native
acceptance remains required. Dedicated tests cover every-call probes,
exclusive-writer detection, replacement/deletion, permission loss, symlinks,
cache limits, copy/serialization, stale FD reuse, initial-open races and unlock
failure cleanup. The focused runner/controller/lock tests passed 80 before
the additional initial-open race case; all required quick checks passed.

The resumption-only release was stopped before staging or commit so the
combined orchestration and measured observer changes receive fresh full and
immutable gates. No timeout or input corpus was increased or reduced.

The first combined full gate caught the existing concurrent-observer regression:
serializing two readers behind one descriptor-cache mutex delayed an observer.
No code from that gate was committed or activated. The cache now belongs to
its first observer thread; secondary threads probe independent temporary
handles without waiting for the owner's I/O mutex. They check cached namespace
identities before and after probing. The original concurrency test and its
five-second assertions are unchanged and pass. The combined process-cleanup,
runner, lock and controller group passes 92 tests; quick checks are green.
A repeated final-code microbenchmark measured medians 0.734217 versus 0.474372
seconds on the same four files. Different background load makes this a separate
sample, not an absolute whole-pipeline speed claim.

The finite retry ceiling is eight attempts per domain to accommodate multiple
periodic checks. The fixed review clock, 900-second native attempt cap and
3,600-second total pass allocation are unchanged. A real full HKJC corpus probe
using the original timed-out cutoff and all production locks completed with
`timed_out` at 902.020 seconds (supervisor termination included). The unchanged
900-second budget remains enforced; handle reuse alone has not resolved whole-
corpus acceptance. A later diagnostic on refreshed main was correctly preempted
by production activity after 79 seconds. Neither diagnostic grants acceptance.
Native acceptance still must succeed before installation.

Release coordination was also checked: automatic approval remains enabled. The
busy `auto-release.lock` belonged to PID 66550 running another approved release
through its immutable full gate, not this recovery. No recovery release process
was active or holding that lock. The four domain launchd groups and Central
durability were loaded and aligned; Central research-review remains missing
until its original strict first-pass requirement succeeds. No failed receipt
was treated as an installation or model-promotion success.
