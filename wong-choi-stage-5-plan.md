# Wong Choi Stage 5 Automated Research Platform Plan

## Goal

先凍結每個domain可信嘅versioned evaluation ruler，再建立可重現、可審計、可並行嘅四線研究平台，自動完成固定語料嘅 baseline／candidate、ablation、walk-forward、leakage同統計判決；所有結果受Stage 4 promotion、approval及rollback規則約束，中央旺財永遠唔成為第五個scoring engine。

## Sequencing Decision

- Metrics readiness係Stage 5第一個hard gate：AU／HKJC凍結現役v2同cohort定義；Tennis建立point-in-time、family-specific `tennis-v1`；NBA建立`nba-v1`，但未有足夠forward settled evidence前只作描述性研究。Ruler改動同candidate model必須係兩個獨立release。
- Ruler gate後先做一條由experiment spec去final report嘅最小vertical slice，再擴展Dashboard／queue；唔會先起一個龐大空平台。
- Tennis係第一個end-to-end consumer，用嚟改善可用性但維持shadow；AU／HKJC之後驗證`PRIMARY_WIN`／`RANKING_WIN`；NBA season研究可先做歷史分段，live promotion evidence繼續等新季。
- Research可以自動排隊、重跑、淘汰候選同提出shadow proposal，但唔可以改evaluation ruler／holdout、merge model code、activate production或提高注碼。
- Production永遠優先：heavy research只可喺冇domain production lock、WARM已掛載、預估容量同timeout過閘時開始；同一時間最多一個heavy experiment，scratch／大型artifact放WARM。

## Self-review Cadence

| Trigger | Automated review | Allowed outcome |
|---|---|---|
| 每個run前／後 | Spec、ruler、dataset、PIT、leakage、reproducibility、artifact | `run／block`；完成後`reject／inconclusive／shadow review proposal` |
| 每日最後一個production job後 | Queue、failed／stale run、locks、HOT／WARM、data freshness | 安全retry、defer或freeze research；不可影響production |
| 每週一09:00 Sydney | 新實驗、失敗原因、candidate、sample增長、drift | Central Dashboard＋authorized Telegram digest |
| 每月第一個週一 | Corpus／feature／market drift、metric stability、storage成本 | Append review report；只可提出改善proposal |
| 每個ruler release後90日或incident | Metric仍否反映產品目標、source/schema/leakage異常 | Freeze相關queue並要求獨立human ruler review；不可自動改尺 |
| Sample trigger | AU／HKJC每+50 settled races；Tennis每family +200 verified PIT outcomes；NBA首30 forward settled recommendations、之後每+100 | 只觸發monitoring；未過ruler minimum sample／power不可promotion |

## Tasks

- [x] 1. 完成獨立metrics readiness review並凍結Stage 5 charter：盤點四線corpus、point-in-time coverage、baseline commit、truth debt同storage成本；AU／HKJC保留Gold／Good primary、ranking metrics同field-size／venue／going cohort guardrails；Tennis凍結Brier／log loss vs de-vig market、calibration、CLV、ROI CI、coverage同family sample gate；NBA凍結Brier／log loss、calibration、CLV、ROI CI、drawdown、coverage、odds／injury freshness同season／market cohorts。→ Verify：四線各有versioned ruler、metric direction／sample／window／bootstrap／holdout定義、known-win／regression／noise fixtures同rollback target；Tennis只准point-in-time row；NBA清楚標`descriptive only / live evidence pending`；ruler release冇candidate code；roadmap新增Stage 4→5 transition record。
- [x] 2. 建立append-only `ExperimentSpec／DatasetManifest／ExperimentRun／ExperimentDecision`合約同registry：記錄hypothesis、domain、sample hash、point-in-time cutoff、baseline／candidate、pre-registered metrics、seed、commands、parent links同artifact digest。→ Verify：duplicate idempotent、conflict fail closed、schema/hash/link tests全綠；失敗及inconclusive實驗不可覆寫或刪除。
- [ ] 3. 建立immutable dataset snapshot／resolver：由HOT讀近期、catalog-verified WARM讀歷史，固定train/dev/terminal切分、source watermark同availability time；COLD只做restore。→ Verify：同一manifest跨重跑產生同一sample hash；缺WARM、corpus縮細、future-dated row或未驗證snapshot會block，唔會靜靜改樣本。
- [ ] 4. 建立共用experiment runner、queue同domain adapter interface：同一命令跑baseline／candidate、鎖code與data version、保存stdout／metrics／runtime／resource usage，domain scoring仍由各自engine提供；production lock、單一heavy worker、WARM scratch、disk estimate、timeout同cleanup manifest全部fail closed。→ Verify：AU、HKJC、Tennis、NBA contract fixture可重跑；相同spec兩次結果digest一致；production active／WARM offline／容量不足／timeout fixtures會defer或終止而不留半成品；runner冇import或共用domain weights。
- [ ] 5. 接入evaluation／statistics pipeline：walk-forward、dev／terminal holdout、paired bootstrap CI、cohort guardrails同Stage 4 machine decision；只接受Task 1已凍結嘅ruler version，AU／HKJC支援`PRIMARY_WIN`／`RANKING_WIN`，Tennis按family判決，NBA喺live gate前禁止promotion decision。→ Verify：known-win／regression／noise fixtures判決正確；hit rate、AUC或ROI任何單一metric都不可獨自promotion；terminal不可用嚟搜尋參數；ruler version同candidate commit同時改會fail closed。
- [ ] 6. 自動化research safety gate：target／future leakage、earliest-odds、feature availability、data-quality drift、negative control，同多feature／weight改動嘅mandatory ablation。→ Verify：故意注入賽果、走地價、未來排名、constant field及bundled change fixtures全部被攔；任何fail都不可產生promotion proposal。
- [ ] 7. 建立Central research index、self-review scheduler、報告、Dashboard projection同Telegram digest：按run／daily／weekly／monthly／90-day／incident／sample cadence顯示queued／running／rejected／inconclusive／candidate、證據連結、sample size、CI、drift、storage同下一個人手決定。→ Verify：calendar同sample clock可重播；無新樣本只報進度、唔重判promotion；Dashboard只讀evidence；Telegram dedup且只向authorized chat發送；proposal只可要求`shadow review`，最終仍走Stage 4 approval。
- [ ] 8. 用Tennis跑第一個vertical pilot：按`tennis-v1`固定active-family同earliest verifiable pre-match price，分ATP／WTA、surface、tournament level、odds同coverage比較model vs market Brier／log loss、calibration、CLV、ROI CI及valid no-bet，逐項ablation。→ Verify：完整實驗可由spec一鍵重播；每個family獨立輸出`REJECT／INCONCLUSIVE／SHADOW_CANDIDATE`；非point-in-time row、pooled AUC、lifetime ROI或完成Stage 5本身都不可解鎖promotion。
- [ ] 9. 擴展至AU／HKJC ranking squeeze同NBA season research：先查舊實驗，逐個假設測Gold／Good保護下嘅Top-5 capture、competitive recall、NDCG同cohort；NBA按season／market／odds／injury freshness做歷史描述性baseline並保留新季live gate。→ Verify：至少一個AU或HKJC候選完整走完ranking gate（通過或拒絕都算平台證據）；NBA hit rate唔會被當盈利證據，synthetic／歷史結果唔會冒充forward live acceptance或產生promotion proposal。
- [ ] 10. 完成四個stage checkpoint同Stage 5 research-platform production activation（唔等於任何model promotion）：Task 1後做metrics readiness review、Task 6後做platform safety review、Task 9後做domain pilot review，最後做exit review。→ Verify：每個checkpoint都有immutable decision／風險／rollback；`./檢查.sh`、`./健康.sh`、reproducibility／fault／leakage／resource-isolation matrix全綠；至少兩個domain完成end-to-end pilot、failed experiment可檢索、Stage 4 bypass測試全拒絕；更新roadmap同Stage 6 entry decision。

## Done When

- [ ] AU／HKJC、Tennis同NBA全部有獨立versioned ruler；metric／window／holdout改動同candidate model永遠分開release，任何runner不可繞過。
- [ ] 同一experiment spec可重現相同dataset、metrics、decision同artifact digest，任何人可由report追返data／code／ruler／命令。
- [ ] Tennis完成第一個真實research loop；AU／HKJC完成至少一個ranking-squeeze loop；NBA維持`engineering ready / live evidence pending`直至新季真實證據出現。
- [ ] Self-review按run／calendar／sample／incident準時執行；production可preempt research，WARM offline或HOT壓力唔會拖垮日常automation；全部候選被拒絕仍可算平台成功。
- [ ] Central Wong Choi可安排、監察同總結研究，但任何model promotion、merge、activation同bankroll action仍必須經Stage 4 human approval。

## Proposed Goal Function Objective

完成Wong Choi Stage 5 Automated Research Platform：先獨立審核並凍結AU／HKJC v2、Tennis v1及NBA v1 evaluation rulers，再建立append-only experiment registry、immutable point-in-time dataset manifests、production-safe可重現跨domain runner、walk-forward／ablation／leakage／statistical decision gates、按run／calendar／sample／incident運作嘅self-review、Central Dashboard／Telegram visibility；以Tennis及AU／HKJC做end-to-end pilots，NBA保持live evidence gate，同時確保所有model promotion仍受Stage 4 contract及human approval約束。
