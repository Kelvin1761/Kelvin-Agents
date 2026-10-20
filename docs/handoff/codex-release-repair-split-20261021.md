# 交接俾 Codex：拆細 `codex-release-repair-20261014`

- 日期：2026-10-21
- 寫嘅人：Claude Code（Kelvin 指示：「第 2 步交俾 Codex」）
- 狀態：**未開始**。工作保存喺 `origin/codex-release-repair-20261014`，冇丟失。

## 發生咗咩事

隊列入面有兩個 release manifest，已經喺 2026-10-21 記做 `release_superseded`。
`actor` 係 `claude-code:queue-cleanup`，原因有寫入 event：

| commit | 分支 | 處理 |
|---|---|---|
| `2ed4feac796a` | codex-cleanup-completed-20261014 | 係 0332 嘅子集：41 個獨特檔入面 39 個完全一樣，剩低 2 個（tennis `README.md`、`tennis_daily_schedule.py`）喺 0332 有更新版本 |
| `0332c0a38981`（連父 commit `9ff8ffbe`） | codex-release-repair-20261014 | **入面有真工作，但唔可以當一個 release 上**（原因見下面） |

**呢兩個都唔係 reject。** 0332 入面有工作喺 main 同 10-14 之後任何一條 Codex
分支都搵唔到，例如 `shared_wong_choi/scheduler_window.py`（悉尼 22:00–01:00
靜默時段）同 release 複查輸出。呢啲要由你拆細之後重新發佈。

## 點解唔可以直接 refresh

對比基準：`rollback_target` 係 `f10e221d212c`，`origin/main` 係 2026-10-21 嘅版本。

- **太大**：234 個檔，加咗 197,377 行，刪咗 424 行。大部分係 `docs/audits/**`
  入面嘅 JSON（`hkjc-race-weight-oracle-20261013/results.json` 一個檔已經有
  135,631 行）。要先決定呢啲應唔應該放入 git，定係應該放資料根或者外置碟。
- **跨晒所有 domain**：AU、HKJC、NBA、tennis、dashboard，加埋共用 control plane。
  policy 分類係 `deployment`。
- **16 個檔同 main 有衝突**（`git apply --check` 失敗）：
  `.agents/scripts/inject_hkjc_fact_anchors.py`、
  `.agents/scripts/tests/test_wongchoi_external_run.py`、
  `au_daily_auto/README.md`、
  `au_sportsbet_performance_quality_candidate.py`、`au_sportsbet_raw_field_audit.py`、
  `test_no_stale_engine_constant_copies.py`、
  `central_wong_choi/install_production_runtime.sh`、`nba_daily_auto/README.md`、
  `validate_nba_output.py`、`shared_wong_choi/runtime_launchd.py`、
  `test_research_review_cursor.py`、`Horse_Racing_Dashboard/generate_static.py`、
  `docs/plans/2026-10-14-open-source-borrowing.md`、
  `tennis-wong-choi/scripts/install_macos_launchd.sh`、
  `tennis_wc/betting/ledger.py`、`wong-choi-stage-5-plan.md`
- **大約 11 個檔似乎會倒退 main**：release 刪走嘅行，喺 `0116c740`（09-05 舊 base）
  去 `f10e221d` 之間係 main 新加嘅。括號入面係行數。呢個係逐行比對得出嘅粗估，
  **要逐段核實**：
  `au_daily_schedule.py` (3)、`test_au_daily_schedule.py` (2)、
  `run_hkjc_daily_schedule.sh` (3)、`command_adapter.py` (1)、`control_plane.py` (3)、
  `process_runner.py` (1)、`test_research_review_cursor.py` (7)、
  `static_template.html` (4)、`run_tennis_daily_schedule.sh` (1)、
  `test_research_adapter.py` (7)、`wong-choi-stage-5-plan.md` (1)
- **會改生產行為**：靜默時段令排程夜晚唔跑。呢個係營運決定，要 Kelvin 明確批准，
  唔可以夾喺「保存工作」嘅 release 入面一齊上。

## 建議做法

1. 由最新 `origin/main` 開 worktree（記得抄 `.wongchoi_*root` marker）。
2. 按 domain 或者功能拆成細 release，每個用 `./保存.sh --path …` 加
   `--expected-result`：
   - 先做冇衝突、冇倒退嘅部分。
   - 16 個衝突檔逐段手動合併，**唔好整個檔覆蓋**。
     2026-09 試過咁做，倒退咗 `scrape_hkjc_horse_profile.py` 嘅修正。
   - 11 個疑似倒退嘅檔，只保留 release 新加嘅行。
   - `scheduler_window.py` 同佢嘅接駁要**自己一個 release**，等 Kelvin 批先上。
   - 先決定 `docs/audits/**` 嗰批大 JSON 放邊度，再決定入唔入 git。
3. 而家自動 rebase 已經上線（見 `AGENTS.md`「過期自動 rebase」）：唔同 domain
   嘅細 release 唔使再互相排隊；但係掂共用 package 嘅仍然要串行。
4. 做完喺呢份文件加一行「完成」，然後刪走 `origin/codex-release-repair-20261014`
   同 `origin/codex-cleanup-completed-20261014`。

## 重現分析用嘅命令

```bash
git diff --numstat f10e221d212c 0332c0a38981 | sort -rn | head
git diff f10e221d212c 0332c0a38981 -- <file> > p.diff && git apply --check p.diff
```
