# Wong Choi Stage 5 Production-safe Research Runner — 2026-08-31

## Verdict

**Task 4 engineering checkpoint pass，等待獨立scoped code release；Task 5 evaluation／statistics尚未開始。** 新runner只執行已凍結`ExperimentSpec.commands`，唔import任何domain engine或weights，亦唔會計promotion decision、改model／ruler、merge、deploy或接觸bankroll。

## Architecture

- 沿用ADR-006 modular monolith：本機create-only JSON job／claim／outcome queue，加一個non-blocking heavy-worker flock；冇新增service、database或distributed queue。
- 四線共用pure-command adapter interface；baseline同candidate使用完全相同argv、dataset、seed、locale、timezone同Python hash seed，只改detached checkout cwd及`WC_RESEARCH_ROLE`／output path。
- Run前及heavy lock後都驗baseline／candidate full commit、clean checkout probe、verified immutable dataset、WARM mount、free capacity同所有production locks；每個command後再驗dataset、output symlink及production lock，完場再驗checkout。
- 真實subprocess各自在新process group運行；整個job共用deadline。timeout、production start或lock probe失靈會TERM後KILL全group，唔會只殺parent留下child。
- Scratch只寫WARM partial directory，成功先atomic rename；timeout、preemption、command／metrics／executor／checkout／dataset／symlink failure會刪partial並publish`cleanup.json`。成功保存metrics、stdout／stderr、wall／CPU／RSS、commits、commands、seed、dataset lineage同artifact digest。
- 成功、失敗、timeout及preemption都寫Task 2 `ExperimentRun`；queue retry同一payload／outcome idempotent，同ID異內容或偽造claim fail closed。

## TDD And Verification Evidence

- RED 1：`research_runner`未存在，test collection以`ModuleNotFoundError`失敗。
- GREEN 1：queue、四線adapter、success、production／WARM／capacity／checkout／timeout／heavy-worker基本contract 12/13；剩餘一項揭示`30`／`30.0` canonical hash不一致，正規化後13/13。
- RED 2：deterministic env、executor exception、mid-run checkout change共6項失敗；修正後四線end-to-end、same-spec digest及durable failure evidence通過。
- RED 3：偽造claim、dataset mutation、output symlink、outcome retry clock drift同production probe exception被測試捕捉；全部轉為fail closed及idempotent。
- Task 4 runner tests：32 passed；連Task 2 registry及Task 3 resolver focused gate共69 passed。
- `./檢查.sh`：1,422個Python tests passed（另2 xfailed、4 skipped），Dashboard Node 69 checks passed；ruff、AU／HKJC golden各120匹及模型說明全部通過。clean worktree冇近期評分archive，所以data-contract明確skip。
- `./健康.sh`：exit 0、冇嚴重問題；四線排程、production provenance、WARM同COLD正常。既有HOT低過30GB floor、AU Google Drive best-effort mirror permission同NBA off-season新季ledger warning保留；runner預設capacity及production-preemption gates會阻止heavy research拖垮production。

## Deliberately Deferred

- Task 5先按四份frozen ruler實作metrics、paired bootstrap、cohort、walk-forward同machine decision；Task 4只保存adapter產生嘅raw metrics。
- Task 6先加入target／future leakage、earliest odds、negative control同mandatory ablation判斷。
- Task 7先接calendar／sample queue scheduler、Central Dashboard同Telegram；目前冇安裝launchd，亦冇自動啟動heavy research。
- Task 8–9先將真實Tennis、AU／HKJC及NBA harness接入spec commands；fixture成功唔代表任何model成熟或promotion。
