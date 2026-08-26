# Wong Choi Capability Matrix

盤點日期：2026-08-26。`✅` 已有現役入口；`🟡` 有功能但未符合共用 contract；`⏳` engineering complete、等 live gate；`—` 不適用。

| Capability | AU | HKJC | Tennis | NBA |
|---|---|---|---|---|
| Domain orchestrator | ✅ `au_orchestrator.py` | ✅ `hkjc_orchestrator.py` | ✅ `tennis_wc.cli` | ✅ `nba_orchestrator.py` |
| Discover / calendar | ✅ Sportsbet next race day | ✅ official racecard watch | ✅ provider fixture ingestion | ✅ ESPN schedule + six-stage classifier |
| Predict | ✅ evening/morning | ✅ prerace | ✅ daily/card | ⏳ pregame；等 2026-27 live coverage |
| Validate / fail closed | ✅ data contract + dashboard verify | ✅ data health + snapshot gate | ✅ readiness + betting gate | ✅ official/book/report/manifest coverage gate |
| Publish | ✅ Cloudflare + live verify | ✅ Cloudflare post-success | ✅ run-daily deploy | ✅ validated pregame/postgame deploy |
| Settle / reflect | ✅ evening reflector/archive | ✅ postrace reflector/corpus | ✅ review-date + ledgers | ⏳ postgame archive；等首個完場日 smoke |
| Health | ✅ standalone healthcheck | 🟡 embedded gates + global health | 🟡 `HEALTH_JSON` in text log | ✅ standalone health mode + global health |
| Telegram | ✅ operational/content/review | ✅ operational/content/review | ✅ health/card/performance | ✅ operational/card/performance + dedup |
| Recovery | ✅ guarded morning/deploy recovery | ✅ pending recovery + startup | ✅ guarded card/dashboard recovery | 🟡 startup single-day；未授權 multi-day backlog |
| Overlap lock | ✅ `flock` | ✅ `flock` | ✅ `flock` | ✅ `flock` |
| Structured run record | 🟡 domain JSON + canonical adapter manifest code；live獨立checkout待部署 | ✅ canonical adapter manifest；daily wrapper已切換 | ✅ canonical adapter manifest；card/daily wrapper已切換 | ✅ domain JSON + canonical adapter manifest；role-specific launchd已切換 |
| Immutable prediction manifest | 🟡 final output exists；未有 canonical immutable manifest | ✅ SHA-256 manifest | 🟡 DB prediction rows；未有 immutable run manifest | ✅ SHA-256 snapshot manifest |
| Live acceptance | ✅ production | ✅ production；新季 forward gate另計 | ✅ production | ⏳ pipeline ready / production evidence pending |

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
- 2026-08-26：四線 daily wrapper code已接入共用 control plane；HKJC／Tennis／NBA runtime path已生效。NBA舊三合一 pregame launchd已拆成 warmup／production／final-refresh，startup off-season manifest smoke通過。AU live launchd使用獨立 production checkout，待已批准保存／部署後先啟用。
