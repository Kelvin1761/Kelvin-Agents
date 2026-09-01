# Wong Choi Stage 5 Research Registry — 2026-08-31

## Verdict

**Task 2 release `9b2af3909547`已批准、merge及四domain activation；Task 3 dataset resolver已進入獨立engineering checkpoint。** 新registry只負責凍結研究身份、provenance同append-only evidence，唔會執行模型、計metric、改ruler、作promotion或接觸bankroll。

## Contracts

| Record | Required provenance | Typed parent |
|---|---|---|
| `ExperimentSpec` | hypothesis、domain、ruler ID／digest、baseline／candidate full commit、pre-registered metrics、seed、commands、protocol artifact digest | 可選同domain `parent_spec_id` |
| `DatasetManifest` | PIT cutoff、sample hash、row count、source availability／content digest、train／dev／terminal split hash、artifact digest | `spec_id` |
| `ExperimentRun` | exact spec ruler／commits／seed／commands、dataset、start／complete time、state、metrics／stdout／artifact digest | `spec_id`＋`dataset_manifest_id`，dataset必須屬於同一spec |
| `ExperimentDecision` | `reject／inconclusive／shadow_review_proposal／blocked`、rationale、metrics／artifact digest | `run_id`，metrics digest同run一致 |

全部record使用timezone-aware timestamps、canonical domain ID、full git SHA或SHA-256、canonical JSON content hash同create-only hard-link publish。相同payload retry回傳`duplicate`；同ID異內容、缺parent、錯kind、跨domain、provenance不一致、PIT後availability、split totals不符或未知v1欄位全部fail closed。Registry冇update／delete API；外部tamper或刪parent會令audit失敗，failed／inconclusive record亦不可改寫。

## TDD Evidence

- RED 1：`research_registry`未存在，test collection以`ModuleNotFoundError`失敗。
- GREEN 1：完整四層chain、duplicate、conflict、typed links、frozen run provenance、schema、failed／inconclusive immutability同tamper audit通過。
- RED 2：重新計算合法content hash後加入未知v1欄位，舊loader錯誤接受。
- GREEN 2：固定每種kind嘅exact top-level field及link set；未知／缺失欄位一律拒絕。
- Research registry tests：19 passed。
- Task 1 rulers＋Stage 4 evidence／release compatibility focused gate：45 passed。
- `./檢查.sh` full gate：1,372個Python tests passed（另2 xfailed、4 skipped），Dashboard Node 69 checks passed；ruff、AU／HKJC golden各120匹及模型說明全部通過。data-contract因clean worktree冇近期評分archive而明確skip，唔係pass證據。
- `./健康.sh`：exit 0、冇嚴重問題；四線排程已載入、production provenance 16/16、WARM約883 GiB、COLD 5/5。既有HOT 21 GiB warning同AU Google Drive mirror best-effort permission warning保留，Task 4 production-safe queue啟用前唔會跑heavy research。

## Deliberately Deferred

- Queue、production preemption、single heavy worker、timeout、resource accounting同domain adapters屬Task 4。
- Statistical decision、leakage／ablation、Dashboard／Telegram projection同pilots屬Task 5–9。
- Task 2完成唔代表Tennis／NBA model成熟，亦唔產生任何candidate promotion權。
