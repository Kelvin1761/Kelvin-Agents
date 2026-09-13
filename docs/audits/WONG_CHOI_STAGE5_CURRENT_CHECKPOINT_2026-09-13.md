# Wong Choi Stage 5 current checkpoint — 2026-09-13

## Decision

Stage 5繼續進行。Task 1–5已進入main及production；Task 6同Task 7均未完成。
Release A令共用research safety／review工程核心可以正式使用，但冇授予任何model、ruler、
holdout、promotion、betting、bankroll、scheduler、Telegram或Dashboard deployment權力。

## Authoritative release state

- Shared Release A：`44c9df55ca722b1e0f7b7b1560738495887e4b80`。
- Scope：89個exact paths，只限`.agents/skills/shared_wong_choi/research_*.py`同matching tests。
- Release gate：`risk=code`、`check=full`、check及push exit code均為0；冇installer、Dashboard
  deploy或manual activation reason。
- Release A已fast-forward merge到main。第一次activation因production checkout有未提交
  HKJC runtime data而安全rollback，冇刪資料。
- 後續production release `cf98f9580d58e841cc509c46ba5ce5a1f2146171`以Release A為
  rollback base，activation event逐一證明AU、HKJC、NBA、Tennis全部aligned。現役checkout
  `84d20f25acaec8c0e7915511c11581dc34e9bff6`仍包含Release A ancestor。

## Task 6 evidence

2026-09-12／13喺隔離Release A worktree重跑：

- safety、postflight、guard、power applicability／projection／variance／producer：148 passed；
- AU／HKJC／NBA／Tennis feature provenance、settlement source、Tennis earliest-source witness：
  149 passed；
- 合計297 focused tests，冇failure。

測試直接覆蓋結果／future leakage、late或in-play price、feature availability、constant／neutral
field、negative control、bundled-change ablation、偽造`safety_passed=True`、missing／mismatched
power evidence，以及任何失敗唔可產生promotion proposal。Release A full repository gate亦通過，
AU／HKJC golden scoring冇改。

## Why Task 6 is not checked off

Fail-closed contract唔等於真實證據已存在。四線future compact producer同real callback仲未逐項
批准／啟用；power applicability仍需獨立reviewed evidence；Task 10要求嘅platform safety review
同全局health亦未過。Task 6因此係「engineering core active／acceptance NOT READY」。

## Task 7 boundary

Release A已包含read-only research index、Sydney replay clock、append-only receipts、supervised review、
durable notification intents、dedup／reconciliation、storage／liveness／drift projection等共用primitive。
但production activation仍要獨立分拆：

1. D-AU、D-HKJC、D-Tennis、D-NBA metadata producers；
2. E Central review scheduler同HOT cursor初始化；
3. F authorized Telegram acceptance；
4. C private Dashboard research feed、visual acceptance同deployment。

以上全部超出Stage 5低風險standing auto-approval；每項要獨立full gate、immutable approval、rollback
同production receipt。部分成功唔可將Task 7標完成。

## Current operational gate

`./健康.sh`於2026-09-13 exit 1。最新domain run狀態係AU／HKJC／Tennis succeeded、NBA正常休季
dormant；主要未解項係Drive mirror落後、Artifact COLD 6/8、AU／Tennis 30日SLO未達標。
呢啲只會令checkpoint保持開放，唔會用改ruler／holdout或假設健康去通關。

## Next safe action

先按獨立scope實作D-AU future compact producer，以同一個production run生成、hash-pin及append
prediction-time input／feature lineage同settlement result evidence；唔改AU scoring engine、weights、
odds policy或歷史artifact。完成本機TDD同full gate後先建立獨立高風險release等待人手批准。
