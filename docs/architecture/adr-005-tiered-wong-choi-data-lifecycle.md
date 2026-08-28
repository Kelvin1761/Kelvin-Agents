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
| COLD | `WC_COLD_MIRROR_ROOT`（Google Drive） | WARM嘅第二份verified disaster-recovery copy | 唔做live DB／scheduler source；容許延遲同步 |

任何本機原件只可以經以下閘移除：`copy to temp → content hash manifest → atomic publish → restore drill → second verified copy → scoped human approval → remove source`。外置碟單獨唔算backup；Google Drive單獨亦唔算runtime storage。

中央旺財提供read-only `storage`／Telegram `/storage`。真正archive executor必須idempotent、冇`--delete` default、外置碟消失時只defer唔損毀資料。完整archive研究要經multi-root catalog，禁止用`rglob`靜靜漏咗offline corpus。

Dashboard D1另有每日verified export：只讀remote、固定Wrangler版本、export前後row counts必須穩定，SQL要restore到全新SQLite並通過integrity／foreign-key／row-count gate，先可寫immutable snapshot同copy去WARM／COLD。Dashboard同Telegram只顯示呢份證據嘅freshness，唔會將backup狀態當prediction evidence。

## Trade-offs

- 保留live DB同近期資料喺SSD，換取日常可靠性；唔追求將所有嘢即刻搬走。
- Full-history研究要插住外置碟，換取大幅減少SSD長期增長。
- 先copy／驗證再刪會短暫佔兩份空間，但避免archive損毀或Drive placeholder被誤當完整檔案。

## Revisit Trigger

WARM超過70%容量、每週增長超過50 GiB、單次研究需要同時掃多部機，或者Google Drive TCC問題已有可靠background API，先重新評估NAS／object storage。
