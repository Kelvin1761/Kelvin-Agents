# AU 未用欄位：intake 與 cutoff-aware 速度標準

狀態：**HARNESS／TEMPORAL CORRECTNESS；不是FEATURE WIN**。鎖定 baseline 0328f13a9564c787837e3c4aa1cfff19235c9b0c。沒有實際候選AUC、排序績效、市場統計、production apply、commit或release。

凍結root448個meeting，359在Archive，447有Formguide／評分，36820個parsed runner blocks；所有meeting身份及逐目錄Formguide數量與source_manifest一致。原default mapping181個meeting、只到2026-08-21；root.parent/source_compare.json缺失，old default把form_depth當0，min-depth4令全部被排除。零樣本不是欄位無用。inventory不依賴該mapping或sidecar，也識別per-race scoring；parsed depth不當PIT證据。

速度標準原碼掃全root，未綁cutoff／source available-at，global cache亦不分root：synthetic preserved-old函數把未來WinningTime99收作reference；20次同一event複製足以建reference60；root A60後切root B80仍讀到60。`unused_standard_boundary_v1.json`保存反例及原snapshot hash。

`au_unused_field_intake.fit_speed_standards`只收独立audit PASS、source hash一致、明確時區available-at嚴格早於prediction timestamp的asset；dated runs須早於prediction當地日期，排trials，同venue/date/race/distance只算一個event，conflicting timing/going不任選，至少10 unique events才建venue×distance median，going residual至少40 events。無跨root／cutoff globalcache。標準是winner-time參考，runner時間仍屬margin推算，不等於個體真Time。Hash/PASS字段本身不能證明歷史availability，独立PIT auditor仍必須提供證據。

`runner_features`可接受explicit prepared standard_state與prediction_at；cutoff不相同即拒絕，same-day/future run不進speed signal。沒有已審計state時speed feature缺失，不自行掃root找數；這不證明其他overview欄位安全。Source-bound label/PIT/pre-registration consumer尚未完成，舊CLI不再用date/race-only results_for或未登記AUC排序，明確拒絕；inventory模式可獨立執行。沒有用「停止不安全分析」代替完成field power研究，研究仍列未完成。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_unused_field_power.py --scored "$WONGCHOI_AU_DATA_ROOT" --inventory-only --inventory-output docs/audits/au-full-model-20261011/unused_field_frozen_inventory_v1.json
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/verify_unused_standards_boundary.py
```

前者需先載入同目錄environment.json；fixture proof拒絕覆寫既有output folder。14 scoped tests PASS（先前commentary误报15，已核實修正）；quick/full exit0、AU808及Shared1240 tests。完整code/log hashes、source manifest binding与限制在unused_intake_check_manifest.json。

未完成：完整source-bound outcomes/PIT/registration intake、actual OOS fitted producer與standard state/projection接駁、unused field power／ablation／cohort evidence；legacy helper其他 dated/overview feature chronology亦需逐項覆核。未授予任何歷史樣本fit eligibility。AU stale baseline／HKJC isolated-root skip照保留。
