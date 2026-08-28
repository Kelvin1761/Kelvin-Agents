# Wong Choi Stage 4 Production／Evidence Plan

## Goal

將四條獨立domain engine升級成可量度可靠性、可追溯、可重播、可受控升級嘅production platform；中央層永遠唔改寫AU、HKJC、Tennis、NBA各自嘅scoring同評估尺。

## Tasks

- [x] 1. 凍結Stage 4 baseline同中央治理ADR，獨立處理任何stale evaluation baseline。→ Verify：ADR accepted；四線golden／evaluation contract可信。
- [x] 2. 建立policy-based release automation：只stage本次scope，自動check／commit／push／記錄狀態；高風險改動經Telegram批准先merge／deploy。→ Verify：其他worktree改動永不入commit；每個release有immutable manifest同rollback target。
- [x] 3. 完成Stage 4A canonical health／SLO／immutable snapshot／recovery。→ Verify：四線health可機讀；partial／stale不publish；30日reliability可計；restore drill通過。
- [x] 4. 獨立更新AU／HKJC evaluation contract：Gold／Good仍係第一優先；Gold／Good無回歸時容許有統計證據嘅ranking-only improvement path。→ Verify：primary/ranking/reject三種fixtures；holdout不可用作調參。
- [x] 5. 建立Stage 4B append-only evidence chain：`PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`。→ Verify：ID、hash、point-in-time、parent links、duplicate/conflict tests全綠。
- [x] 6. 逐線接入evidence writer：AU first，再Tennis、HKJC、NBA；舊domain output保持不變。→ Verify：每個正式推介／no-bet／shadow可追到source、commit、model release同結果。
- [x] 7. 建立中央Wong Choi CLI／Telegram：`status`、`git`、`models`、`evidence`、`release`、白名單approval。→ Verify：同一Telegram token只有一個poller；未授權chat零回覆；重複approval冇side effect。
- [x] 8. 完成Stage 4C model registry／promotion：`research→shadow→paper→limited→production→retired`，PR可自動開但模型不可自動merge／加注。→ Verify：缺holdout、forward evidence、rollback或人手批准一律block。
- [x] 9. 建立Stage 4D storage／Dashboard foundation：HOT／WARM／COLD policy、容量status、Telegram `/storage`；Dashboard正式歸中央control tower、D1 betting ledger同model evidence分權。→ Verify：ADR-005、storage/dashboard tests；Dashboard不可計prediction。
- [ ] 10. 完成Stage 4D durability cutover：artifact catalog／verified archive executor已完成；Tennis 4.387 GB WARM copy＋restore同live D1 export＋restore已通過；尚欠COLD second copy、nightly launchd production activation同multi-root readers。→ Verify：外置碟offline只defer；hash／SQLite／D1 restore一致；刪本機前另有scoped approval。
- [ ] 11. 完整exit review同production deployment。→ Verify：`./檢查.sh`、`./健康.sh`、fault matrix、release smoke、Telegram smoke全綠；100%新production decisions有provenance；roadmap更新。

## Done When

- [ ] Kelvin唔需要估「有冇commit／push／deploy」：中央status同Telegram清楚列每個checkout、remote、automation同release狀態。
- [ ] 中央Wong Choi只做control、evidence、risk、governance同display，唔係第五個預測模型。
- [ ] AU／HKJC登記production；Tennis／NBA未過各自performance/live evidence gate前只登記shadow，automation live唔等於model production-ready。
- [ ] NBA live evidence未齊時，平台只標記`engineering complete / NBA evidence pending`。
