# Wong Choi Stage 5 E review scheduler engineering checkpoint — 2026-09-19

## Status

E1 is implemented and verified in an isolated worktree. It is not committed,
pushed, installed, initialized against production HOT state, or activated.
E2 remains a separate release for the transactional runtime wrapper, launchd
installation, explicit four-domain production lock paths, production HOT cursor
initialization, and first live acceptance receipt.

This checkpoint does not change an evaluation ruler, model, feature, score,
weight, domain engine, release policy, Dashboard, notification path, bankroll,
bet, retention policy, or model stage.

## Delivered E1 boundary

- `central_research_review.py` provides one explicit `--initialize` operation
  and one ordinary bounded four-domain review pass.
- An ordinary pass never creates, resets, or repairs a missing cursor.
- AU, HKJC, Tennis, and NBA are bound to the exact frozen ruler bytes from
  evaluation release `297a293e6e00f6dab2ef17e59db13abd9a3b8526` and activation
  time `2026-08-30T11:56:52.796047+00:00`.
- Every cursor binds its registry, WARM root, queue, production evidence,
  monitoring evidence, storage source, and liveness lease source.
- Production prediction and settlement inputs are read from the canonical
  `HOT/evidence/records` store; operational run receipts remain under
  `HOT/runs` and are never treated as research evidence.
- Initialization is idempotent only for the identical configuration. Existing
  mismatched or malformed state fails closed before another domain is changed.
- The runtime requires at least one explicit production lock path. No machine
  path is guessed by this engineering layer.
- One shared timezone-aware timestamp is passed to all four domains. Capacity,
  timeout, and maximum-review limits are pinned in the versioned contract.
- An atomic create-only, hashed run summary is written under
  `HOT/runs/central/<UTC date>/research-review/`.
- Per-domain blocked, deferred, timed-out, preempted, or failed outcomes remain
  visible and cannot be represented as an all-domain success.
- Both `model_promotion_allowed` and `telegram_delivery_confirmed` remain false
  in initialization, per-domain outcomes, and run summaries.

## Verification

TDD started with a collection failure because the entry module did not exist.
After implementation:

```text
python3 -m pytest \
  .agents/skills/central_wong_choi/tests/test_central_research_review.py -q
8 passed

python3 -m pytest \
  .agents/skills/central_wong_choi/tests \
  .agents/skills/shared_wong_choi/tests/test_evaluation_rulers.py \
  .agents/skills/shared_wong_choi/tests/test_research_review_cursor.py \
  .agents/skills/shared_wong_choi/tests/test_research_guard.py -q
100 passed

./檢查.sh --quick
all required quick checks passed
```

The tests prove:

1. all four ruler files match their pinned SHA-256 digests and model releases;
2. explicit initialization creates four complete SQLite cursor bundles;
3. exact reinitialization leaves cursor bytes unchanged;
4. a changed WARM/config binding is rejected without rewriting any cursor;
5. an ordinary pass with no cursor returns blocked outcomes and creates no
   cursor directory;
6. all domains receive one aware clock plus bounded runtime arguments;
7. a deferred Tennis result remains deferred while other domains may complete;
8. an interrupted receipt write leaves no partial file at the official path;
9. the entry imports no delivery or deployment integration.

## Remaining E2 acceptance

Before activation, E2 must:

1. resolve and independently verify the four real production lock paths;
2. add a transactional wrapper and scheduler at a non-conflicting Sydney time;
3. include the scheduler in production install/rollback verification;
4. run the full release gate;
5. initialize the real HOT cursor state only as an explicit activation step;
6. execute one production review pass and retain its hashed receipt;
7. verify all four domain deployments remain aligned and no notification,
   Dashboard, or model-promotion authority has been introduced.

F Telegram acceptance and C private Dashboard projection remain separate later
releases. E1/E2 success cannot mark Task 7 complete by itself.
