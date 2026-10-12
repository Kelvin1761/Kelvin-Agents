# EXP-20261012-23 — Refresh false-success fix / actual field E2E

- Type: independent correctness patch and operational integration audit, not model improvement.
- Prior search: AU refresh/rebuild failure and field-level records searched before patch; serving-directory-cache audit and first15/H plan references reviewed. No ranking candidate or old terminal reopened.
- RED: successfulextract/nonzeroscorer returnedTrue; 1failed/2passed retained. Patch adds returnFalse; onlyrebuild_meeting_from_cache AST changes. No score/feature/clock/label change or new leakage input.
- GREEN: 6 new regressions plus existing scheduler suite172passed; rc1/2/124 reject, successpreserved, realrefresh→rebuild fault chain refuses rescored/update/success snapshot. Quick/fullPASS;golden/explanations unchanged;AUstalebaseline/HKcontractSKIP explicit.
- Actual frozen8race fieldrebuild: injectscratch/rider into copiedHTML;actualparser/diff/refresh/claw/Facts/Logic/score/render/parse roster16→15, jockeyfeaturechanges, densebarriers/fieldcountcorrect, snapshotfilehashespreserved. RA/market seamsdisabled, no liveprovider/PIT certification.
- Unfinished E2E: directautoHeavy8 succeeds/Logicupdates, but parsedgoing=None; v2driver FAIL retained. Post-field unchangedprovider falselyproducesbarriers-only delta; actualgoing-only scheduler branch stillpending. Do notlabelcompleteE2EPASS.
- Harness failures: v1missedzero-paddedIDs;freshv2fix retained; unmodifiedeight-racechanges={} initiallymislabelledfalsepositive, v2observationcorrects status andretainsv1. Independentcollector binds partialoutputs/snapshots.
- Scope limits: no transactionalrollback orfailed-runpublishproof;noRA/provider/emergency/browser certification. No outcome/price metrics, modelWIN, blindshadowstatus/results, productionapply/commit/push/deploy/notification.
- Reproduce: test_refresh_rebuild_failure_gate.py; run_refresh_rebuild_full_checks_v1.py; run_refresh_field_e2e_v1/v2.py; collect_refresh_e2e_partial_v2.py; observe_same_cache_refresh_barriers_v1.py (containsretainedlabelingmistake; usev2interpretation). Immutablefixtures requirefreshversionpaths.
- Decision: scopedcorrectnessfixreadyforreview, not已證實改善; allbroaderH/refresh/dashboard/provenance requirements remainpartial. Next:raw/densecomparison,explicitgoingtransport,fullscheduler/static/browser/failedrun evidence chain.
