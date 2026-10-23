# Release gate latency — 2026-10-23

## Findings

Review baseline: origin/main `d6ddb905e293017a51c23a8eb645c2795c22f15a`.
From 2026-10-21 00:00 UTC to the review, 25 releases with a `merged` event had
manifest-to-merge median 13.08 minutes, maximum 34.57 minutes. This excludes
the preparation gate. The approval lock covered full recheck, replay and activation.
Three observed release processes concurrently ran the Shared Wong Choi suite.

## Changes and retained checks

- Opt-in `single_clean_gate` enabled for delegated releases. A private Git index
  freezes the selected working-tree delta plus existing committed history. An
  unpublished commit object is fully gated in a clean clone, then the exact object
  is published using a compare-and-swap branch update. Failed gates leave real
  HEAD/index unchanged. Source, HEAD and index races block publication.
- Only the same process can hand an attested full-gate receipt to approval. It is
  pinned to SHA, check, interpreter/package versions and locations, environment
  and root marker contents, and expires after 15 minutes. No manifest/log can
  grant reuse. Approval still checks remote branch and main before and after a
  clean quick gate, including live data contracts. Environment races force full
  recheck. Each replayed SHA runs its own full gate. Resume runs a fresh full gate.
- Git hooks, signing and an implicit local venv retain the legacy commit path.
  Setting `single_clean_gate=false` restores the two-gate automatic path without
  disabling delegated approval. No model/ranking/evaluation changes.
- Live stderr, retained diagnostic log paths, gate/suite timings and 30-second
  progress messages. Timeout terminates the entire gate process group.
- Short, unique pytest fixture roots reduce repeated ancestor verification on
  macOS. Explicit/custom/external scratch settings are respected. Successful
  fixture trees are removed, failed trees retained. No fixtures are reduced and
  no safety checks or suites are removed.
- Remote branch namespace conflicts now fail before the expensive gate. The
  actual remote `refs/heads/codex` blocks `codex/...`; this work uses a hyphenated
  branch. No existing remote branch is deleted or renamed.

## Measurements and reproduction

Unchanged research test:

```
PYTHONPATH=.agents/skills PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  .agents/skills/shared_wong_choi/tests/test_research_prediction_page_runtime.py::test_supervised_corpus_above_legacy_reference_cap_is_not_truncated \
  -q -p no:cacheprovider --durations=5
```

Default macOS pytest path: **130.46 seconds call time, failed with phase timeout**
(120-second supervised budget). Same test with
`--basetemp=/private/tmp/wc-release-speed-short-test`: **73.67 seconds call time,
passed** (74.93 seconds total). Both ran under concurrent release workload; the
load was not controlled, so this is a spot comparison, not a controlled speedup
estimate or a guarantee for every machine.

Full-gate invocation counts are exercised against real Git remotes and clean
clones: normal release = one full + one quick on the exact final SHA; replay =
one new full + one quick on the replayed SHA. Resume, stale/mismatched receipts,
failed gates, source/index/HEAD races, hook fallback, environment races and
timeout descendant cleanup are tested.

Validation: 115 release tests passed before the last preflight additions;
32 focused release regressions passed after those additions; two shell-driver
lifecycle tests passed; quick gate passed. The final full check is the release
preparation's clean exact-commit gate, before any branch commit is published.
Its result, duration, SHA and log are recorded in the immutable release manifest;
approval records whether the full gate was reused and the quick recheck log.

Production end-to-end latency reduction remains to be measured from subsequent
releases. The verified engineering reduction is two full-gate executions to one
for the supported normal automatic path, and less work while holding the
approval lock. Four-domain model stages, Dashboard/D1 and storage are unchanged.
