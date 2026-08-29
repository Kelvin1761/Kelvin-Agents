# Wong Choi Capability Matrix

盤點日期：2026-08-28。`✅` 已有現役入口；`🟡` 有功能但未符合共用 contract／model gate；`⏳` engineering complete、等 live gate；`—` 不適用。

| Capability | AU | HKJC | Tennis | NBA |
|---|---|---|---|---|
| Domain orchestrator | ✅ `au_orchestrator.py` | ✅ `hkjc_orchestrator.py` | ✅ `tennis_wc.cli` | ✅ `nba_orchestrator.py` |
| Discover / calendar | ✅ Sportsbet next race day | ✅ official racecard watch | ✅ provider fixture ingestion | ✅ ESPN schedule + six-stage classifier |
| Predict | ✅ evening/morning | ✅ prerace | ✅ daily/card | ⏳ pregame；等 2026-27 live coverage |
| Validate / fail closed | ✅ data contract + dashboard verify | ✅ data health + snapshot gate | ✅ readiness + betting gate | ✅ official/book/report/manifest coverage gate |
| Publish | ✅ Cloudflare + live verify | ✅ Cloudflare post-success | ✅ run-daily deploy | ✅ validated pregame/postgame deploy |
| Settle / reflect | ✅ evening reflector/archive | ✅ postrace reflector/corpus | ✅ review-date + ledgers | ⏳ postgame archive；等首個完場日 smoke |
| Health | ✅ domain + canonical 30日SLO | ✅ global + canonical 30日SLO | ✅ readiness + canonical 30日SLO | ✅ standalone + canonical 30日SLO |
| Telegram | ✅ operational/content/review | ✅ operational/content/review | ✅ health/card/performance | ✅ operational/card/performance + dedup |
| Recovery | ✅ guarded morning/deploy recovery | ✅ pending recovery + startup | ✅ guarded card/dashboard recovery | 🟡 startup single-day；未授權 multi-day backlog |
| Overlap lock | ✅ `flock` | ✅ `flock` | ✅ `flock` | ✅ `flock` |
| Structured run record | ✅ domain JSON + canonical adapter manifest；live獨立checkout已部署 | ✅ canonical adapter manifest；daily wrapper已切換 | ✅ canonical adapter manifest；card/daily wrapper已切換 | ✅ domain JSON + canonical adapter manifest；role-specific launchd已切換 |
| Immutable prediction manifest | ✅ create-only SHA-256 snapshot | ✅ SHA-256 manifest | ✅ create-only daily report snapshot | ✅ SHA-256 snapshot manifest |
| Central evidence chain | ✅ Prediction→Decision→Settlement→ModelRelease | ✅ Prediction→Decision→Settlement→ModelRelease | ✅ shadow Prediction→Decision→Settlement→ModelRelease | ⏳ shadow chain ready；等 live settlement evidence |
| Controlled model promotion | ✅ v2 Gold/Good + ranking path | ✅ v2 Gold/Good + ranking path | 🟡 registry shadow；holdout ROI/Brier未過 | ⏳ shadow；live forward gate未到 |
| Live acceptance | ✅ production | ✅ production；新季 forward gate另計 | 🟡 automation live / model shadow | ⏳ pipeline ready / production evidence pending |

中央能力：`Horse_Racing_Dashboard`係正式control-tower display，D1 `WC_LEDGER`保存實際投注；HOT／WARM／COLD狀態同verified archive catalog由中央旺財管理，兩者都不得改寫domain scoring。Telegram有read-only `/status`／`/git`／`/models`／`/evidence`／`/storage`／`/dashboard`，治理寫入只限authenticated `/approve SHA`同一次性`/bootstrap_models SHA`。

中央durability狀態：D1每日verified export、WARM archive同owner-only Google Drive COLD proof已完成；catalog 3/3 artifacts verified，當中Tennis兩個migration artifacts已逐part full-download、digest、重組、extract同SQLite quick-check。HOT source仍未刪。2026-08-29 read-only runtime scan確認AU 4/4已指向獨立production checkout；HKJC 6/6、NBA 6/6同Tennis 3/3仍指primary checkout，Central durability尚未安裝。統一transactional cutover同rollback已成candidate，等新immutable SHA批准；source retention仍要另一次scoped approval。

## Confirmed Owners and Entrypoints

| Domain | Automation owner | Scheduler / control entry |
|---|---|---|
| AU | `au_daily_auto` | `.agents/skills/au_racing/au_daily_auto/au_daily_schedule.py` |
| HKJC | `hkjc_daily_auto` | `.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py` |
| Tennis | `tennis_daily_schedule` | `tennis-wong-choi/scripts/tennis_daily_schedule.py` |
| NBA | `nba_daily_auto` | `.agents/skills/nba/nba_daily_auto/nba_daily_schedule.py` |

## Stage 2B／3B Gaps Derived from the Matrix

1. 將四線 status 映射到 canonical run states，未知值 fail closed。
2. HKJC／Tennis 補 canonical per-run manifest；AU 補 immutable prediction manifest。
3. 將 locks、retry、Telegram dedup、health 同 publish gate 以 adapter contract 驗證，唔重寫 domain engine。
4. NBA 實作 odds freshness policy；multi-day backlog 要另行授權先增加 unattended side effects。

## Adapter Contract Progress

- 2026-08-26：四線全部已有 manifest-backed adapter；HKJC／Tennis scheduler新增 opt-in `--control-json`，原有 launchd/default output不變。
- 四線共用 fault matrix驗證 success、exit 75、hard failure、missing status、duplicate attempt同新 retry attempt；未知／缺失 status一律 fail closed。
- 2026-08-26：四線daily wrapper已接入共用control-plane code。NBA舊三合一pregame launchd已拆成warmup／production／final-refresh，startup off-season manifest smoke通過。AU獨立production checkout已對齊scoped commit `40724a31`；當日deployment verifier 14/14 aligned、wrapper／adapter／health smoke通過。
- 2026-08-29：新增installed-plist＋loaded-state runtime verifier，揭示HKJC／NBA／Tennis仍由primary checkout執行，並非同一approved production checkout；統一cutover candidate會保留Tennis live data原位並提供plist＋Git雙層rollback。
