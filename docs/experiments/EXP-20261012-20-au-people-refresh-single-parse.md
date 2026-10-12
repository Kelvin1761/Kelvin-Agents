# EXP-20261012-20 — AU people refresh single parse

- Type: isolated performance-only patch, not fitted/ranking candidate or overall model-improvement claim.
- Baseline witness SHA:4a820412326199ebd565d0b754894c84f441cfa8802c8e71b5f718721a67e179; candidate SHA:e48faf4bec13925966151bfaa2b8a9b050d275f6458868fc60e56210c063f38d. APIparse_person preserved, refresh deriveslegacyview fromoneparse/deepcopy; per-personcachecheckpoint/snapshotappend retained.
- Fixedclock20realcachedpeople:cache/snapshotbyteidentical,fetchorderexact,parse40→20,independentobjectviews.
- 3baselinevs3candidatewarmcachefull8racepipeline:median 16.985507→15.366653s (9.53% observed decrease);extract 11.02%. Sequentialnonrandomizedobservations/noCI/no live-nightlygeneralization.
- Full 51 stable outputfiles bytes andwholeLogicexact;Data_Health.md exact;Data_Health.json onlygenerated_at/meeting_dirdiffer;allotherhealthpayloadexact. Oddsfileexcluded,nomarketanalysis.
- Checks:6scope tests,quick/fullPASS;goldenunchanged;AUstalebaseline/HKcontractSKIPexplicit.
- Currentruntime sourceobservation: schedulerHEAD1dc706a...,15sourcefilescomparedlockedGit,onlyschedulerpychanged;installedplistnotloadedruntimeproof. Noactualscheduler/shadowexecution.
- Commands:verify_people_refresh_bytes_v1.py;run_people_parse_candidate_repeats_v1.py;compare_people_parse_pipeline_v1.py;verify_people_parse_scope_v1.py;run_people_parse_full_checks_v1.py. Immutableoutputsneedfreshversionpaths;manifestbindssource/tests/commands/env/artifacts.
- Decision: scopedperformancechangehasexactdata/outputevidenceandmeasuredwarmcachebenefit;PLAN-L255stillPARTIAL. No model performanceWIN,blind status/results,productionapply,commit/push/deploy/notification.
- Rollback:restore EXP19sourcewitness tosb_people_stats.py/removeonlynewtest;keepallreports/evidence. No scoring/golden/calibrationchange.
