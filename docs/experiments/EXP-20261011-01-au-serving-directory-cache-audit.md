# EXP-20261011-01 — AU serving directory／PF cache／source clock audit

日期：2026-10-11（Australia/Sydney）。平台 AU；隔離 worktree `/Users/imac/.codex/worktrees/au-full-model-audit-20261011/Antigravity-repo`，locked baseline `0328f13a9564c787837e3c4aa1cfff19235c9b0c`。沒有 candidate KPI／holdout／shadow reveal。

判決：**DIAGNOSTIC／算法接駁 verified；historical PIT FLAG**。不是模型改善、不是 Stage 4 WIN、不是 release。

問題：Markdown-only serving copies 保留相同 Logic／Facts，是否等於原目錄完整 serving 環境？每個 fresh prediction worker 是否保留正式評分及安全欄？來源時鐘是否只能從 Sportsbet 裸時鐘推斷？

舊證據先查：`docs/audits/au-full-model-20261011/SERVE_ADAPTER.md` 保留首個 frozen original vs copied-directory failure；`serve_directory_read_trace.json` 定位上層 PF cache；PF cache target dates 全部 ≤2026-07-08。原技能／模型合約保持原樣，沒有因本次診斷改判決尺。

## 方法及實際樣本

原凍結 AU corpus + frozen Sportsbet cache，固定 race/runner IDs／baseline flags（B7=60、class_score live=1、PF opt-in=0、cache-only、disable deploy）。完整來源 `source_manifest.json`／`sportsbet_cache_manifest.json` 與 `environment.json` 綁定；execution manifest 保存所有 auto／engine script hashes。

原目錄 fresh meeting process：427 meetings／3,385 races／34,473 runners，無 skipped/failed case。Scoring memory API 禁用 output writers；拒絕 file write opens；runtime reads 前後 hash 重驗。與先前 research copies 逐 ID 配對，未用名次／收益篩選。再每場 fresh process 跑 OOS adapter internal worker，全 3,385 場與 meeting scorer ability／final ranking 精確相等。

原 serving baseline dataset SHA256：`bbf573f599ab6bbdfa9d8b9331a073876cdfa79713e50bfa5435d866498486af`。
Research unlabelled replica input SHA256：`1182694724911552546d30d37897ce2f2a80b79c57518798f842e6bb2d56ba91`。
原研究 copy dataset SHA256：`3dae4e1694e305ae66273ddd93677e0efab875db14e066228d5911a791c71d9e`。

## 結果及失敗保留

全期 4,658 匹 pace_figure_score／ability 改變，450 場 full ranking／404 場有序 Top4／283 場有序 Top2 不同；只有 pace_figure_score 改。2026-08-05 起 2,579 場／25,474 runners 完全相同。根因是 original root PF cache 存在，Markdown-only copy root 沒有；`WC_PF_BACKFILL=0` 不禁 enrichment 讀該 cache。不是「候選改善」。此前 mixed-context 911／717 是另一比較，不能混當本數字。

研究 replica max |Δ|0.0039，零 >0.01；只有 numeric tolerance，不代替 final production rank 驗證。13,984 observed frozen source files 全 hash 符合凍結 manifests；13 worktree resources hash 與當前 Git blob 相同，沒有歷史部署／capture PASS。Runtime inventory在 imports 後開始，不能稱完整 import-source coverage。

RA main/scheduler cache 338 檔 hash 相同，46,265,409 bytes；單獨凍結，不改 baseline profile。330 唯一 exact URL + 日期 binding，329 有 explicit Last Published timezone stamp，2,568 local race clocks。350/493 immutable snapshots 精確 date/venue matched，2,678 race/snapshot pairs：22 pairs 的現存 RA revision 發布在 capture 後（3 snapshots），不能回填成當時版本；2 pairs capture at/after inferred scheduled start（10/10 Eagle Farm、Caulfield R1），缺 actual off-time 就只 FLAG。

## Commands／artifacts

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/build_original_serving_baseline.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/compare_original_serving_baseline.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/verify_original_baseline_adapter.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/verify_original_serving_replica.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/freeze_ra_clock_sources.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/ra_explicit_publication_audit.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/align_ra_snapshot_clocks.py
```

Snapshot builders 故意拒絕覆寫既有 v1 output directories；重現需保留既有 evidence，再用新 output version／manifest，不刪掉 baseline 清 warning。所有 code hashes、output identities、差異及失敗在同 report dir：`original_serving_baseline_execution.json`、`original_source_vs_markdown_copy.json`、`original_baseline_adapter_equivalence.json`、`original_serving_replica_verification.json`、`original_serving_runtime_assets.json`、`ra_cache_clock_source_manifest.json`、`ra_explicit_publication_audit.json`、`ra_snapshot_clock_alignment.json`。

## 下一步與限制

正式候選前清 field-level PIT：舊 capture version／resource部署、官方 venue clock、roster/scratch timeline、import/source coverage；actual fitted adapter／算法及 empirical §6／完整 registry plugin 仍未完成。不能以「329有官方發布時間」概括所有欄位 as-of。現存 blind shadow 不讀其 candidate performance。沒有 production mutation、參數採用、commit／push／release。
