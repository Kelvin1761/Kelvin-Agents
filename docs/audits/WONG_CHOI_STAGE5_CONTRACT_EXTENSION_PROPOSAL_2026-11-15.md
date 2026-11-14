# Stage5 proposed contract extensions — decision pending

This is a reviewable implementation proposal, not an amended frozen contract,
installation authority, pilot registration or permission to execute historical
research. Existing input/control/ruler files are unchanged. The same authorized
reviewer inspected the proposal read-only; no independent test or statistical
approval is inferred.

## Requested decision and strict scope

Authorize implementation and synthetic validation of two opt-in, versioned
contract extensions below. Preserve legacy contracts and all existing metric,
holdout, control-bound, effect, power, promotion, release and incident guards.
This decision would not authorize historical corpus execution, actual pilots,
profile publication, model/scoring/weight changes, installation, credentials,
incident unfreeze, ledger writes or migration/deletion of historical evidence.

## 1. Heterogeneous racing control correspondence

The current registered development_label_rotation rotates whole outcomes within
family. It cannot compare distinct global horse IDs or different field sizes
without an explicit correspondence. The canonical measurement correctly blocks
these before any scorer call. Filtering races, renaming IDs after seeing results,
padding missing runners or skipping controls is forbidden.

Proposed new opt-in control kind/version:

- Group all development rows by existing family and pre-decision roster size.
  Preserve the existing sorted-row ordering and seed-derived nonzero rotation
  within each group. Singleton groups block; no fallback and no row exclusion.
- Bind each actual pre-decision roster to a deterministic ordered list of its
  entity IDs. Freeze the ordering rule before inspecting predictions/outcomes.
  Donor slot i maps bijectively to target slot i. No entity is invented or lost.
- Transfer the donor complete outcome through this bijection for control
  measurement only, including official dead heats and explicit withdrawals.
  Donor withdrawal states become control labels on corresponding target slots;
  normal measurement continues using the target's actual outcome.
- Never group by scores, finish position, observed gain or post-decision
  withdrawal count. Terminal rows never participate. Every dev row participates
  exactly once; label controls cannot alter ordinary labels or source records.
- Bind kind/version, grouping inputs, donor map and exact roster bijections in
  execution evidence. Independent postflight reconstructs all of them from
  frozen rows and registered rule; a caller-supplied passed flag is insufficient.

This changes control meaning and requires explicit authorization even though it
supplies no new statistical threshold or effect value. A pilot must preregister
the authorized version and mapping rule before execution.

## 2. Audited raw-resource projection

The current audited scorer projection supports number/category features and
removes resource references. Hidden closures, event-ID lookups and JSON encoded
as a category bypass that boundary and are not acceptable full-model replay.

Proposed new opt-in input-protocol version: a typed resource bundle reference
binding domain, event, decision cutoff, real pre-decision roster, and:

- Exact raw input/auxiliary bytes, logical roles, sizes and hashes; original
  metadata where production behavior uses it, including mtime.
- Explicit required absences and permitted native fallback behavior.
- Availability/history evidence references distinct from later capture times.
- Code, configuration, environment and importer/resolver versions needed to
  reproduce the complete native scoring/ranking behavior.

The audit/materializer validates the complete bundle before scoring and exposes
only verified resources via domain-specific read-only resolvers. All relevant
AU/HKJC readers must be covered: profile, priors, sidecars, import-time resources
and fallbacks. Undeclared/live/network/neutral-substitute reads cannot silently
supply missing resources. Preserve native enrichment, overlays, display rounding
and final tie ordering; do not substitute a matrix-only scorer.

Current-event outcomes, evaluation-only prices, split/terminal annotations and
unrelated corpus data cannot enter scorer resources. Genuine prior-training
outcomes keep their existing audited treatment. Trace binds manifest, projected
input digest, actual resource-use records and declared absences. Postflight
independently verifies these bindings and byte stability. Hash identity alone
never proves historical availability; unknown availability blocks.

A reviewed Python resolver alone is not an OS filesystem/network sandbox. State
actual isolation/read-tracing limits accurately and test the real native reader
paths rather than claiming universal isolation from helper fixtures.

## Required acceptance before any enablement

1. Legacy projections/control mappings unchanged; old versions reject new kinds.
2. Different global IDs map through frozen equal-size rosters; different sizes
   stay in distinct groups. Grouping/correspondence never depend on predictions
   or outcomes; dead heats/withdrawals are preserved exactly.
3. Singleton groups, incomplete fields, altered bijections, fixed points,
   omitted dev rows or terminal participation block before scoring.
4. Missing, changed, oversized, symlinked, undeclared or unavailable resources
   block without published metrics. Import-time dependencies and metadata-
   sensitive branches are covered; no hidden live/cache/network fallback.
5. Current labels/terminal annotations never enter scorer inputs. Measurement
   receives held outcomes only after completed predictions.
6. Full synthetic AU/HKJC native replay parity covers enrichment, ranking,
   metadata and tie behavior. Tampered traces/manifests/control records fail
   independently reconstructed postflight, not just matching local hashes.
7. Parent/worker power actions stay disabled until the complete separately
   reviewed workflow satisfies every existing gate. Normal full source and
   independent immutable release gates still apply to any completed engineering.

## Separate real-pilot prerequisites

An actual preregistered dataset, protocol, comparator and defensible pre-decision
availability proof are still required. There are currently no canonical HOT
registry/queue records in the observed audit and0/4 verified power profiles.
Neither this proposal nor later synthetic parity supplies meaningful effect,
method approval, historical PIT evidence or valid monitoring samples.

Before authorization, standalone materializer/native synthetic parity engineering
can proceed without connecting raw inputs to the frozen supervised harness or
unlocking power. Do not describe that intermediate work as a runnable pilot.
