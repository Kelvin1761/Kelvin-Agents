# Wong Choi Stage 2B／3B Engineering Exit Audit

日期：2026-08-26（Australia/Sydney）

## Decision

**Stage 2B Unified Multi-model Platform 同 Stage 3B Unified Automation Control Plane engineering gate及 production activation全部通過。** 四個 domain已接入同一 canonical run contract；domain scoring、features、ruler、holdout完全冇合併。AU獨立 production checkout亦已部署同一 scoped commit，Stage 4B Evidence Core可以開始 implementation。

NBA production evidence gate仍然 deferred：現況只可標記 `pipeline ready / production evidence pending`，唔代表模型已證明盈利。

## Requirement Evidence

| Requirement | Authoritative evidence | Result |
|---|---|---|
| 四 domain adapter／canonical IDs | `shared_wong_choi/contracts.py`、`registry.py`、四個 adapter contract tests | PASS |
| Immutable attempt manifest／lock／bounded retry | `control.py`、`command_adapter.py`、`control_plane.py`；duplicate、terminal、exit 75 fixtures | PASS |
| Timezone／slots／missed-run／freshness | `schedule_policy.py`；Sydney DST、missed clock、shadow、unstarted-only fixtures | PASS |
| 六階段 NBA lifecycle | `nba_season.py` + NBA pipeline fixtures：OFF_SEASON、PRESEASON、EARLY_REGULAR、REGULAR_SEASON、LATE_REGULAR、POSTSEASON（PLAY_IN／PLAYOFFS） | PASS |
| NBA odds freshness | 21:00 warmup、00:30 production、06:30 final-refresh tests；started artifact byte/hash protection | PASS |
| Operational state／severity／dedup／release gate | `operational.py`；四-domain partial/stale/shadow fault matrix | PASS |
| Wrapper cutover implementation | AU、HKJC、Tennis、NBA wrapper contract tests + four-domain control CLI dry-runs | PASS（repo code） |
| Wrapper cutover runtime | HKJC／Tennis／NBA launchd指向主 repo；AU launchd指向已對齊嘅 `/Users/imac/wongchoi-scheduler` production checkout | 4/4 ACTIVE |
| NBA launchd cutover | 舊 `nba-wong-choi.pregame` 已 bootout；plist保留為 `.disabled`；warmup／production／final-refresh已載入 | PASS |
| Runtime／manifest smoke | NBA startup經新 control plane產生 `attempt-1.json`（`dormant`、exit=0）；AU production wrapper dry-run回傳 canonical v1 payload；AU adapter/control manifest smoke 9 pass | PASS |
| AU deployment verification | `deployment_verify.py` 比較 scoped source同 `/Users/imac/wongchoi-scheduler` | `aligned`：14 aligned、0 missing、0 different；`safe_to_activate=true`；dirty overlap=0 |

## Verification Snapshot

### Mandatory code gates

- `./檢查.sh --quick`：PASS。
- `./檢查.sh`：PASS，全部 suites 綠：
  - AU 493
  - HKJC 56
  - Shared racing 42
  - Shared Wong Choi 73
  - Race compliance QA 11
  - NBA 39
  - Agent scripts 10 pass／2 expected-failure
  - Dashboard Python 44 pass／1 skip
  - Tennis 448
  - Dashboard Node 69

Quick/full gate只有既有 AU `consistency_score` range warning；AU／HKJC data contract分別抽查60場／533匹同60場／768匹。今次 control-plane工作冇改 scoring，亦冇改 evaluation ruler、holdout或 golden baseline。

### Operational health

- `./健康.sh`：exit 0，`冇嚴重問題`。
- AU／HKJC／Tennis／NBA launchd全部載入；AU evening job指向 production checkout新 wrapper，最近一次 exit 0；NBA新三個 pregame labels全部 healthy／未到首次執行時間。
- NBA最新 startup run：off-season `dormant`，0日 freshness。
- 非阻塞警告：
  - AU Google Drive best-effort mirror有 File Provider permission warning；本機正本同 Cloudflare不受影響。
  - HKJC休季，最新 meeting 42日前屬季節性狀態。
  - NBA evidence ledger要等新季首個 completed postgame先建立。

## Runtime Acceptance Still Open

以下唔阻塞 Stage 2B／3B engineering closure，但係 Stage 4A／NBA live acceptance 必須保留：

1. NBA 2026-27首個有盤日：ESPN tags = Sportsbet tags = reports = snapshot manifest。
2. 首個完場日：所有 legs只可 hit／miss／void，`unverified=0`先 archive。
3. 最少30個 settled forward recommendations先建立 bootstrap baseline。
4. AU／HKJC／Tennis下一個真實 scheduled run仍要持續觀察 manifest；任何異常可即時用下列 rollback。呢項屬 Stage 4A ongoing operations，唔阻塞 Stage 2B／3B closure。

## Rollback Targets

- Shared dispatch rollback：四個 `run_*_daily_schedule.sh` 最後一行改回直接 domain scheduler；domain model code同 artifact schema冇改。
- NBA launchd rollback：bootout warmup／production／final-refresh，將 `~/Library/LaunchAgents/com.antigravity.nba-wong-choi.pregame.plist.disabled` 還原再 bootstrap。
- Control state：`~/WongChoiData/WongChoiControl` 只係旁路 manifests；唔會覆寫 prediction artifacts。

## AU Activation Record

1. 由乾淨 `origin/main`建立 `codex-wong-choi-stage23`，只包含六個 scoped commits；已 push，冇混入其他 AU model／scratch工作，亦冇自動merge。
2. 獲明確 scoped deployment批准後，`/Users/imac/wongchoi-scheduler`由 `1dbc4b5e` fast-forward到 `40724a31`；現有 `sb_archive_meeting_ids.json` runtime mapping完整保留。
3. 部署前備份位於 `/private/tmp/au-stage23-backup.UXWZXr`。
4. 實際驗證命令：

   ```bash
   python3 .agents/skills/shared_wong_choi/deployment_verify.py \
     --source /private/tmp/wc-stage23.oiqLoW \
     --target /Users/imac/wongchoi-scheduler \
     --domain au --json
   ```

5. 結果：14 files aligned、`safe_to_activate=true`；production wrapper dry-run exit 0，AU adapter/control smoke 9 pass，`launchctl`確認 evening job指向 production checkout，`./健康.sh` exit 0。

Scoped branch比較頁：`https://github.com/Kelvin1761/Kelvin-Agents/pull/new/codex-wong-choi-stage23`。Branch已push，但未聲稱PR已建立或已merge。

## Next Stage Entry

Stage 4B 第一個 vertical slice應該係 immutable evidence chain：

`PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`

先定 schema／ID／point-in-time invariant同 replay verifier；唔改任何 domain scoring，唔郁 evaluation ruler或 holdout。
