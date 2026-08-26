# Wong Choi Stage 2–3 Completion Plan

## Goal

補齊四個 domain 嘅共用平台合約同 unattended automation control plane；保留各自 scoring engine，完成 engineering exit gate 後先正式實作 Stage 4B Evidence Core。

## Sequencing Decision

- Stage 4A 現役 reliability、health、Telegram 同 fail-closed deploy 繼續運行，唔會停低或拆走。
- Stage 4B 可以先做 schema/design，但 implementation 要等 Stage 2B／3B engineering gate 通過。
- NBA 新球季 live acceptance 受賽程限制，列作 deferred production gate；唔阻塞共用結構工程，但未通過前唔會標記 NBA production-proven。

## Tasks

- [x] 1. 建立四線 capability matrix，逐項列出 discover、predict、validate、publish、settle、health、Telegram、season state 同 recovery 現況。→ Verify：AU／HKJC／Tennis／NBA 每格都有入口、輸出及 owner，冇「unknown」。
- [x] 2. 定義 `DomainAdapter` 合約同 canonical domain/event/run IDs，只包裝現役 orchestrator，禁止搬動或合併 domain scoring。→ Verify：四個 adapter contract tests 用同一組 lifecycle cases 通過。
- [x] 3. 建立共用 run-state contract：`DORMANT → READY → RUNNING → SUCCEEDED|PARTIAL|FAILED|BLOCKED`，連 idempotency key、lock、retry 同 immutable run manifest。→ Verify：manifest attempt 不覆寫、terminal state 不可重開；NBA reference adapter 重跑同一 attempt 只讀既有結果。
- [x] 4. 統一 scheduler control plane：timezone、season/calendar discovery、pregame/post-event jobs、missed-run recovery 同 freshness cut-off 由 policy 配置。→ Verify：fixture clock 可重播 off-season、preseason、regular、postseason 同 source outage。
- [x] 5. 統一 operational shell：health schema、structured logs、Telegram severity/dedup、fail-closed publish/deploy；各 domain 保留自己訊息內容。→ Verify：同一 fault matrix 對四線都會阻止 partial/stale release，並只發一次正確告警。
- [x] 6. 為四個 adapter 補 integration fixtures，同時定案 NBA odds freshness：21:00 warm-up、00:30 production、06:30 只刷新未開賽場次並保留所有 snapshots。→ Verify：四線 fixture end-to-end 綠；NBA 已開賽資料不可改寫。
- [x] 7. 跑 Stage 2B／3B engineering review，保存測試結果、health snapshot、未解風險同 rollback target。→ Verify：`./檢查.sh --quick`、`./檢查.sh`、`./健康.sh` 全部通過，roadmap transition record 已更新。
- [ ] 8. 新球季執行 NBA deferred live gate：首個有盤日 coverage smoke、首個完場日 settlement smoke、其後累積 30 個 forward settled recommendations。→ Verify：零漏場、`unverified=0`；只喺足夠證據後建立 NBA bootstrap baseline。
- [ ] 9. 啟用 AU production checkout control plane：scoped save／PR merge後 fast-forward獨立 checkout，deployment verifier必須由目前 `13 missing + 1 different`變成 `aligned`，再做 manifest／health smoke。

## Done When

- [ ] 四個 domain production runtime都由同一 control contract管理；repo code已齊，HKJC／Tennis／NBA已啟用，AU獨立production checkout待部署。
- [x] Stage 2B／3B engineering gates完成；Stage 4B可先完成 `PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease` schema/design，implementation等AU activation gate。
- [x] NBA live gate 未完成時清楚標示 `pipeline ready / production evidence pending`，唔會被當成已證明盈利。
