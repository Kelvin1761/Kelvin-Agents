# Promotion Recommendation

## Decision: DO NOT PROMOTE

Selected feature group: **matrix_7d**. Best standalone ML: **Logistic Regression**. Best evaluated overall: **Matrix Champion**.

Strict gate findings:

- FAIL walk-forward: failed log loss, winner Top-3, 0-hit rate.
- FAIL external holdout: failed log loss, Brier, Top-3 capture@5.
- FAIL evidence sufficiency: external holdout has only nine races; retain research/shadow status even if point estimates improve.
- FAIL Top-2 overlay: the strongest Place overlay reduced walk-forward 0-hit races (26.1%→23.6%) but cut external Top-3 capture@5 to 59.3%; this is not a safe third-pick promotion rule.

Research artifacts are valid regardless of the production decision. The Matrix Champion remains unchanged unless every gate passes.
