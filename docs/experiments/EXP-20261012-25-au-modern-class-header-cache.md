# EXP-20261012-25 — Modern AU class header / cache semantics

- Type: isolated display metadata correctness; no modelclassscore/weight/threshold change.
- Prior search: EXP24 modernheader observation plus AU class/race_class/table records before codechange; no oldterminal reopened.
- RED5F1P: modern thirdcomponentclass misparsedasRace1, emptyclass inferredwrong;legacytableworks. Exactsource/log retained.
- Repair: modern row class/distance authoritative, missing valuesnotborrowedfromhistory;legacygrammar retained. Captured3385races/34473runners classchanged3385/distance0; allotherparserfields exact. No source-authority/PIT or modelquality claim.
- Actual fixture→parser→serializer/slimmer→VMdetailheader shows realclass/Heavy8,15runners andtop-picks/registry preserved. Browser/deploymentnotcertified.
- Cachev6 acceptsoldentry inhelperfixture;version7 rejectswithoutmutatingoldfile, freshroundtrip/missing/corruptPASS. GeneratorASTonlyCACHE_VERSION;parserASTonlyheaderfunction.
- Separate remaining issue: JSON fingerprinttuple→list cannotcompareequalfresh; actualhelpersobserved,nocollector/ROI/productionrun. Loader acceptanceisnotproofactualcollectorhit. Cache reuse/performance stillpending.
- Checks: parser-onlyv1fullPASS, finalv2scope/quick/fullPASS includingcache7. Golden/explanationsunchanged;AUstalebaseline/HKSKIPexplicit. No calibration/goldenrecord.
- Aggregate report created as explicitDRAFT,notfinaljudgement. Writer failedafterreportbeforemanifest onundefinedr;failedsource retained andmanifest-onlyrecovery fixedsnapshot withoutoverwritingreport.
- Reproduce: test_au_modern_class_header.py; verify_modern_class_corpus_v1.py; run_modern_class_checks_v1/v2.py; verify_class_static_transport_v2.py; audit_class_static_render_v2.mjs; actualcachefixtures. Freshversionpaths required;manifestbindsinput/output/source/logs.
- Decision: scopedmetadata/cacheversionrepair verified;fullaudit/PLAN-L259/L275partial. No fit/outcome/market analysis,realblindstatus/results,productionapply/commit/push/deploy/notification.
