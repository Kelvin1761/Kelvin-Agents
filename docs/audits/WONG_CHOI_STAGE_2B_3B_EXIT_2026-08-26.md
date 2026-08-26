# Wong Choi Stage 2B／3B Engineering Exit Audit

日期：2026-08-26（Australia/Sydney）

## Decision

**Stage 2B Unified Multi-model Platform 同 Stage 3B Unified Automation Control Plane engineering gate 通過。** 四個 domain喺本 repo已接入同一 canonical run contract；domain scoring、features、ruler、holdout完全冇合併。Stage 4B Evidence Core可以開始設計，但 Stage 3B production activation要完成下述 AU deployment gate先算全線落地。

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
| Wrapper cutover runtime | HKJC／Tennis／NBA launchd指向本 repo；AU launchd指向獨立 `/Users/imac/wongchoi-scheduler` checkout | 3/4 ACTIVE；AU DEPLOY PENDING |
| NBA launchd cutover | 舊 `nba-wong-choi.pregame` 已 bootout；plist保留為 `.disabled`；warmup／production／final-refresh已載入 | PASS |
| Runtime manifest smoke | NBA startup經新 control plane執行，`attempt-1.json` terminal state=`dormant`、exit=0 | PASS |
| AU deployment preflight | `deployment_verify.py` 比較本 repo同 `/Users/imac/wongchoi-scheduler` | OUT OF SYNC：13 missing + 1 different；dirty overlap=0 |

## Verification Snapshot

### Mandatory code gates

- `./檢查.sh --quick`：PASS。
- `./檢查.sh`：PASS，全部 suites 綠：
  - AU 494
  - HKJC 56
  - Shared racing 42
  - Shared Wong Choi 67（其後四-domain operational matrix targeted rerun：71 pass）
  - Race compliance QA 11
  - NBA 39
  - Agent scripts 10 pass／2 expected-failure
  - Dashboard Python 44 pass／1 skip
  - Tennis 448
  - Dashboard Node 69

Quick/full gate同時指出 AU data-contract baseline engine hash過期，同 `consistency_score` range提示。呢個係同一 dirty worktree入面另一批 scoring改動嘅 evidence debt；本次 control-plane工作冇改 scoring，亦冇擅自 recalibrate ruler。

### Operational health

- `./健康.sh`：exit 0，`冇嚴重問題`。
- AU／HKJC／Tennis／NBA launchd全部載入；NBA新三個 pregame labels全部顯示 healthy／未到首次執行時間。
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
4. AU production launchd仍指向獨立 `/Users/imac/wongchoi-scheduler` checkout；要先經批准保存／部署同一版本，先可聲稱四線 runtime cutover完成。
5. HKJC／Tennis wrapper cutover要觀察下一個真實 scheduled manifest；任何異常可即時用下列 rollback。

## Rollback Targets

- Shared dispatch rollback：四個 `run_*_daily_schedule.sh` 最後一行改回直接 domain scheduler；domain model code同 artifact schema冇改。
- NBA launchd rollback：bootout warmup／production／final-refresh，將 `~/Library/LaunchAgents/com.antigravity.nba-wong-choi.pregame.plist.disabled` 還原再 bootstrap。
- Control state：`~/WongChoiData/WongChoiControl` 只係旁路 manifests；唔會覆寫 prediction artifacts。

## AU Activation Procedure

1. 只保存本次 Stage 2B／3B scoped files，唔可以 `git add -A`混入其他 session工作。
2. Push branch並由人手review／merge PR；唔自動merge。
3. `/Users/imac/wongchoi-scheduler` fast-forward到含 control plane嘅 `origin/main`，保留現有 health／Telegram／meeting-ID runtime changes。
4. 跑：

   ```bash
   python3 .agents/skills/shared_wong_choi/deployment_verify.py \
     --source /Users/imac/Antigravity-repo \
     --target /Users/imac/wongchoi-scheduler \
     --domain au --json
   ```

5. 只有 `status=aligned`、`safe_to_activate=true`先重裝／reload AU launchd；再做 control-plane dry-run、manifest smoke同 `./健康.sh`。

Preflight時主 checkout位於 `codex-hkjc-self-recovery`，相對 main已有18個 commits，另有大量其他 session未提交工作；repo現有 `保存.sh`會執行 `git add -A`，所以今次唔可以直接用佢。獲批准後應由乾淨 `origin/main`分支建立 scoped commit／PR，或者先由負責人確認現有18個 commits可一併merge；未確認前唔可以推成 Stage 2B／3B PR。

## Next Stage Entry

Stage 4B 第一個 vertical slice應該係 immutable evidence chain：

`PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`

先定 schema／ID／point-in-time invariant同 replay verifier；唔改任何 domain scoring，唔郁 evaluation ruler或 holdout。
