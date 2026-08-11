# Decisions

## HKJC ML program

1. Keep analysis and betting as separate layers. No odds, market rank, dividends, ROI, or post-race information may enter analysis-model features.
2. Freeze the deterministic Matrix Champion before training challengers.
3. Use chronological splits and expanding-window walk-forward only; no random cross-validation.
4. Define Place using applicable HKJC field-size rules and exclude races without a valid Place target.
5. Treat score bands as calibrated competitiveness tiers, evaluated by observed win/place rate and ranking capture—not as cosmetic grades.
6. Make a research commit regardless of promotion outcome. Change production only when the strict promotion gate passes.
7. Keep the Matrix Champion in production. Logistic, LightGBM, XGBoost, probability hybrids, and the Top-2 Place overlay all failed at least one cross-period promotion gate.
8. Use the published Win/Place probability bands for monitoring, but do not reinterpret them as bet grades.
9. The next meaningful validation source is a new HK season with genuinely unseen races and fixed-time odds snapshots; further archive-only micro-tuning is not justified.
10. Separate the immutable Champion freeze commit from the later research-run commit in all manifests and reports.
11. Report unsupported betting metrics and unavailable going/rail segments as N/A; never infer them from post-race annotations.
12. Rebuild the research Champion from the seven stored Matrix dimensions and the current production weights. Preserve archived ability as an audit field; never label a stale exported score as the current contract.
13. Keep trainer signal, race shape and stability production formulas unchanged. Ablation confirms all three are useful, but none of their bounded residual models passes both development and external gates.
14. Retain stability residual ML as a research finding only. Its Rank-3→Top-2 corrections match the desired failure mode, but the same model worsened one development race and external NDCG/capture; do not convert segment observations into post-hoc rules.
15. Operationalize the frozen stability residual only as an explicit opt-in shadow. Pin model checksum, 15-feature contract, L2=1.0 and cap=0.05; write separate artifacts and prohibit any change to mainline rank, Grade, verdict, Top Pick or betting recommendation.
