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
4. `Control Tower`：只讀呈現operational health、model health、settlement、exposure同incident。

Canonical JSON records係證據真源；SQLite只可做可重建索引。中央層不得重新計分、改rank、共用domain weight、用跨domain「信心分」取代原評估尺、自動promotion、auto-merge模型改動或auto加注。

## Consequences

- 四條Wong Choi仍然係四個prediction authority；中央Wong Choi係管理角色。
- 每個正式建議可追到data／code／model version、重播、結算同rollback。
- 暫時唔引入microservices、queue或完整event sourcing；量化需要出現先重新評估。
