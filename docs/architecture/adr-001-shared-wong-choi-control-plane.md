# ADR-001: Shared Wong Choi Control Plane as a Modular Monolith

## Status

Accepted — Stage 2B foundation.

## Context

AU、HKJC、Tennis、NBA 已有獨立 production-oriented pipeline，但 scheduler modes、run status、health record、retry 同 idempotency 語言各自不同。共用層要統一 control lifecycle，同時遵守硬規則：domain scoring engine、features、ruler 同 holdout 不可合併。

現況係單一 repo、單機 launchd、低吞吐 batch jobs；唔需要獨立擴展服務，亦冇即時 multi-user consistency 要求。

## Options Considered

| Option | 優點 | 缺點 |
|---|---|---|
| 直接重寫四個 scheduler | 表面最一致 | 高 regression 風險；會一次過改動成熟 production paths |
| Microservices + queue | 隔離同可擴展 | 對現時規模過重；增加部署、重試及訊息一致性問題 |
| Modular monolith adapter layer | 漸進接入；保留現役入口；容易 contract test | 過渡期會同時存在 domain status 同 canonical status |

## Decision

採用 modular monolith：新增 `.agents/skills/shared_wong_choi/`，只定義 domain adapter、capability registry、canonical IDs 同 run-state contract。現役 launchd、orchestrator 及 subprocess boundaries 保持不變；adapter 逐條接入，唔直接 import 或搬動 scoring implementation。

第一階段只建 sync Python contract 同 append-only／atomic JSON-compatible vocabulary；唔引入 database、message queue、microservice 或 event sourcing。未知 domain status 必須 fail closed，唔可以預設成功。

## Trade-offs

- 接受過渡期需要 status normalization；以 explicit mapping 同 contract tests 控制。
- 暫時未有一個 central scheduler process；先統一 contract，再以 fixture fault matrix 證明可安全接管。
- 共用 registry 會知道 domain entrypoint 路徑，但唔知道 domain feature 或 scoring schema。

## Consequences

- 四線可以用同一 lifecycle vocabulary、capability audit 同 idempotency identity。
- 各 domain 可以按風險逐步接入，現役 production automation 不受一次性大遷移影響。
- Stage 4B Evidence Core 可重用 canonical event/run IDs，但 prediction／decision／settlement schema 仍留待下一 stage。

## Revisit Trigger

只有當多部 worker 同時執行、單機 lock 無法滿足，或者 job throughput／recovery latency 有量化瓶頸，先重新評估 queue 或分散式服務。
