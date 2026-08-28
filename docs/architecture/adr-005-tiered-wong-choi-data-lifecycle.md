# ADR-005: Wong Choi Hot／Warm／Cold Data Lifecycle

## Status

Accepted — Stage 4D, 2026-08-27.

## Context

內置SSD只有約228 GiB，2026-08-27已用90%、只剩約22 GiB；repo約8.6 GB。到2026-08-28 Tennis有三個migration DB snapshots共4.387 GB（live DB另計），Wong Choi data約1.9 GB。外置APFS硬碟有約884 GiB可用，但未必長期mount；Google Drive喺launchd／Codex process亦會受File Provider TCC同placeholder影響。

## Decision

採用三層、catalog-backed lifecycle，唔用symlink假裝所有資料永遠online：

| Tier | 位置 | 內容 | 可用性要求 |
|---|---|---|---|
| HOT | 內置SSD | live run、production checkout、mutable DB、最近分析、中央evidence/index | scheduler必須可用；少於30 GiB告警、少於20 GiB攔重型research/backfill |
| WARM | `/Volumes/Kelvin Hardisk 1/WongChoi-Archive` | 已結算raw archive、DB snapshots、可重現experiment artifacts | full-history research前必須mount；日常prediction唔可依賴 |
| COLD | `WC_COLD_MIRROR_ROOT` filesystem mirror，或owner-only Google Drive provider copy | WARM嘅第二份verified disaster-recovery copy | 唔做live DB／scheduler source；容許延遲同步 |

任何本機原件只可以經以下閘移除：`copy to temp → content hash manifest → atomic publish → restore drill → second verified copy → scoped human approval → remove source`。外置碟單獨唔算backup；Google Drive單獨亦唔算runtime storage。

中央旺財提供read-only `storage`／Telegram `/storage`。真正archive executor必須idempotent、冇`--delete` default、外置碟消失時只defer唔損毀資料。完整archive研究要經multi-root catalog，禁止用`rglob`靜靜漏咗offline corpus。

Dashboard D1另有每日verified export：只讀remote、固定Wrangler版本、export前後row counts必須穩定，SQL要restore到全新SQLite並通過integrity／foreign-key／row-count gate，先可寫immutable snapshot同copy去WARM／COLD。Dashboard同Telegram只顯示呢份證據嘅freshness，唔會將backup狀態當prediction evidence。

Provider-backed COLD唔依賴macOS File Provider folder。Connector完成全量download後，必須用同WARM catalog一樣嘅filename／bytes／content digest重算整個artifact；Central只接受exact match、canonical provider URL同append-only proof。分享權限未核實嘅Drive folder唔准放backup。

## Implementation Status（2026-08-29）

- Tennis四份snapshots共5,633,789,952 bytes已copy去WARM，digest一致並由全新temp restore做四個SQLite `quick_check=ok`。兩個artifact亦已上載去Kelvin owner-only Google Drive；因connector有512MB upload同64MB IPC frame限制，payload用tar+gzip後分32MiB ordered parts，每片完整download SHA-256一致、manifest SHA一致、重組後artifact digest一致，四個restored SQLite再次`quick_check=ok`。
- Dashboard D1 snapshot `20260828T123834.213236Z`已通過stable row counts、SQLite restore、integrity／foreign-key同WARM hash gate；owner-only My Drive copy亦經full-download directory digest核對，Central status顯示`cold_provider=google_drive`。
- Shared Drive試建hierarchy冇上載任何backup；正式COLD只放喺Kelvin owner-only嘅`WongChoi Private Backup`。Central `storage`／Telegram分開顯示filesystem COLD root同provider-backed catalog coverage，真實狀態係3/3 catalog artifacts有Google Drive proof。
- HOT source removal仍未獲獨立批准，亦未執行。AU／HKJC／NBA directory readers同Tennis SQLite audit已catalog-aware；offline已知artifact會fail closed，唔會靜靜縮細研究語料。

## Trade-offs

- 保留live DB同近期資料喺SSD，換取日常可靠性；唔追求將所有嘢即刻搬走。
- Full-history研究要插住外置碟，換取大幅減少SSD長期增長。
- 先copy／驗證再刪會短暫佔兩份空間，但避免archive損毀或Drive placeholder被誤當完整檔案。

## Revisit Trigger

WARM超過70%容量、每週增長超過50 GiB、單次研究需要同時掃多部機，或者Google Drive TCC問題已有可靠background API，先重新評估NAS／object storage。
