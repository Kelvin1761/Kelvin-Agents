# ADR-003: Central Wong Choi Is a Governance Plane, Not a Fifth Predictor

## Status

Proposed — Stage 4 architecture decision.

## Context

AU、HKJC、Tennis、NBA使用唔同數據、預測方法、推薦產品、季節週期同評估尺。Stage 2B／3B已經統一adapter同automation lifecycle，但平台仍未能用一條chain回答prediction provenance、落注decision、settlement、model release同promotion狀態。

現況係單一repo、單機batch automation、低吞吐量。需要中央可見性同治理，但唔需要將四個domain model合成一個meta-model，亦未需要microservices、message queue或完整event sourcing。

## Options Considered

| Option | 優點 | 缺點 |
|---|---|---|
| 維持四線完全分散 | 最少新code | 冇統一provenance、SLO、portfolio risk或promotion audit |
| 建立中央meta-model重新排序四線建議 | 表面上得一個總分 | 不同市場概率同評估尺不可直接比較；新增隱藏模型及洩漏風險 |
| 建立中央治理／證據層 | 統一營運、追溯、結算、risk同promotion；保留domain truth | 要維護schema、adapter mappings同中央索引 |

## Decision

選擇中央 modular-monolith governance plane，建立四個職責：

1. `Control`：沿用現有scheduler、run state、lock、retry、health同Telegram。
2. `Evidence`：append-only `PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`。
3. `Governance`：domain-specific evaluation contract、champion／challenger、promotion、approval同rollback。
4. `Control Tower`：只讀呈現operational health、model health、settlement、portfolio exposure同incident。

中央層不得重新計分、改rank、共用domain feature weight、用一個跨domain「信心分」取代原評估尺，或者自動merge／promotion／加注。Canonical JSON records係證據真源；需要查詢時建立可重建SQLite index，暫不引入distributed services。

## Trade-offs

- 接受中央schema同mapping維護成本，換取完整audit chain。
- 暫時唔做跨domain meta-model；portfolio allocation只可以食已校準概率、stake同exposure，唔可以比較AU Gold同HKJC Gold等唔同指標。
- JSON真源較易審計同備份，但複雜查詢較慢；以derived SQLite index補足。

## Consequences

- 四條Wong Choi仍然係四個prediction authority；中央Wong Choi係第五個「管理角色」，唔係第五個預測模型。
- 每個正式建議可以重播、結算、追到data／code／model version，並安全回退。
- Stage 5 research runner同Stage 6 agent lab可以用同一證據層，但無權繞過domain ruler或human approval。

## Revisit Trigger

只有當有多部worker、中央索引吞吐出現量化瓶頸、或者需要多使用者即時一致性，先評估database service、queue或event streaming。只有當四線都有長期、同尺度、可校準嘅forward probabilities，先研究跨domain portfolio optimizer；仍唔等於合併scoring engine。

