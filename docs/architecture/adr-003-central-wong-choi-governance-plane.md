# ADR-003: Central Wong Choi Is a Governance Plane, Not a Fifth Predictor

## Status

Accepted — Stage 4, 2026-08-26.

## Context

四條domain engine使用唔同數據、預測方法、產品、季節週期同評估尺。Stage 2B／3B已統一adapter同automation lifecycle，但未有一條完整prediction provenance、decision、settlement、model release同promotion chain。

## Decision

建立中央modular-monolith governance plane：

1. `Control`：scheduler、run state、lock、retry、health同Telegram。
2. `Evidence`：append-only `PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`。
3. `Governance`：domain-specific evaluation contract、champion／challenger、approval同rollback。
4. `Control Tower`：`Horse_Racing_Dashboard`係中央旺財嘅正式display／interaction surface，呈現四線analysis、operational health、model health、settlement、exposure同incident。

Dashboard有兩個唔可以混淆嘅真源：

- model prediction／decision／settlement provenance以中央append-only Evidence為準；
- Kelvin手動輸入、跨裝置同步同實際投注記帳以Cloudflare D1 `WC_LEDGER`為準，KV只係shadow compatibility layer。

兩邊以immutable prediction／decision／source ID連結。Dashboard只做projection、interaction同ledger input，唔可以自行計prediction、改rank或將畫面狀態反寫做模型證據。

Canonical JSON records係證據真源；SQLite只可做可重建索引。中央層不得重新計分、改rank、共用domain weight、用跨domain「信心分」取代原評估尺、自動promotion、auto-merge模型改動或auto加注。

## Consequences

- 四條Wong Choi仍然係四個prediction authority；中央Wong Choi係管理角色。
- 每個正式建議可追到data／code／model version、重播、結算同rollback。
- 中央`status`／Telegram會同時顯示Dashboard configuration、D1 ledger同storage狀態。
- 暫時唔引入microservices、queue或完整event sourcing；量化需要出現先重新評估。
