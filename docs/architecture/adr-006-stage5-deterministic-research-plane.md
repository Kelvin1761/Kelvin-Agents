# ADR-006: Stage 5 Uses a Deterministic Research Plane

## Status

Accepted — Stage 5 entry, 2026-08-30.

## Context

Stage 4已建立四線domain authority、append-only evidence、promotion approval、rollback同HOT／WARM／COLD lifecycle。Stage 5要自動重跑baseline／candidate、ablation、walk-forward同leakage checks，但Kelvin係solo operator、內置HOT空間有限，而且研究automation唔可以成為第五個predictor或繞過Stage 4。

## Options Considered

| Option | 優點 | 代價 |
|---|---|---|
| 新microservices／message queue／research DB | 可獨立scale同高併發 | 多一套營運、migration同failure surface；目前冇量化需要 |
| 只用自由格式Markdown／scripts | 最快開始 | Ruler、sample同結果不可機讀，容易重複或改尺救候選 |
| **現有modular monolith＋versioned JSON rulers＋append-only experiment evidence** | 同Stage 4一致、可review／hash／重播、零新服務 | Heavy jobs只可單worker；日後高吞吐量先再拆 |

## Decision

1. 四份version-controlled JSON係AU、HKJC、Tennis、NBA evaluation ruler真源；Python loader只validate，唔計domain score。
2. Ruler同candidate model必須分開release；release policy將ruler歸類`evaluation`，混合scope直接fail closed。
3. Stage 5沿用canonical JSON append-only evidence；SQLite只可做可重建index，唔新增authoritative research database。
4. Research runner係現有shared modular monolith一部分；domain adapters只呼叫各自engine，唔import或共用weights。
5. Production lock永遠優先；heavy research單worker、WARM scratch、容量預估、timeout同cleanup manifest過閘先可跑。
6. Self-review可block／defer／freeze／提出shadow review，但唔可改ruler、holdout、merge、activate model或提高注碼。

## Trade-offs And Revisit Triggers

- 接受較低research throughput，換取solo-machine可預測營運同較細故障面。
- 如果verified queue長期積壓、單worker達唔到既定SLO，或多部host需要同時執行，先獨立ADR評估外部queue／distributed workers。
- 如果SQLite index重建時間或JSON scan有量度證據成為瓶頸，先評估新index；canonical evidence格式不因index選擇改變。
