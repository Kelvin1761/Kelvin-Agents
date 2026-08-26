# Wong Choi Platform Roadmap

## Goal

將 AU、HKJC、Tennis、NBA 四條獨立模型線，逐步升級成一個可追溯、可重播、可結算、可安全研究嘅 Wong Choi Decision Platform；共用營運與證據層，但永不合併 domain scoring engine。

## Current Stage

**Stage 2B／3B engineering complete；Stage 3B production activation 3/4（AU獨立checkout待部署）；Stage 4A reliability繼續運行。** NBA狀態係 `pipeline ready / production evidence pending`。Stage 4B可以先做 schema/design；正式 implementation等 AU activation gate完成，維持原定「先完成 Stage 2／3」次序。

## Stages and Exit Gates

| Stage | Deliverable | Exit gate（全部要過） |
|---|---|---|
| 1 Scripts / Prediction | 四個 domain 有可重跑 prediction/scoring 入口 | AU、HKJC、Tennis、NBA 各自可獨立產生 deterministic／versioned output |
| 2A Domain Engines | 多個 domain engine 各自成立 | 四線有獨立 feature、scoring、validation；禁止合併 domain ruler |
| 2B Unified Multi-model Platform | 共用 domain adapter、ID、capability registry 同 lifecycle contract | 四個 adapter contract tests 通過；control layer 可 discover/run/validate/publish/settle/health，但唔包含 domain scoring |
| 3A Automated Pipelines | 四線 pre-event/post-event automation | AU／HKJC／Tennis live；NBA engineering complete、等 2026-27 live acceptance |
| 3B Unified Automation Control Plane | 共用 run states、scheduler policy、locks、retry、recovery、health、Telegram、fail-closed publish | 四線通過同一 fault matrix；重跑冇 duplicate side effects；off-season dormant；partial/stale run 不 publish |
| 4A Production Alignment | 四條線同一套營運最低標準 | unattended run；off-season dormant；失敗不 deploy；immutable snapshot；post-event settlement/review；`健康.sh` 覆蓋四條線；quick/full checks 綠 |
| 4B Evidence Core | 共用 prediction/event/result ledger、model/data version、point-in-time contract | 每個建議可由 prediction ID 追到 source snapshot、commit、odds、結果；各 domain 有固定 evaluation contract；歷史 replay 無未來資訊 |
| 4C Controlled Production | research→shadow→paper→limited→production→retired promotion flow | champion/challenger registry；固定 holdout；risk/CLV/Brier/ROI/drawdown gate；自動 PR 但永不自動 merge／加注 |
| 5 Automated Research Platform | 可重現實驗 runner、ablation、walk-forward、leakage scan、報告索引 | 同一命令可重跑 baseline/candidate；失敗實驗照記；跨 domain 共用工具但 domain ruler 分開 |
| 6 Semi-autonomous Model Lab | Agent 提假設、跑實驗、淘汰候選、開 evidence-backed PR | Agent 無權改 ruler、holdout、production 或 bankroll；所有 promotion 有 human approval；完整 audit trail |
| 7 Wong Choi Decision Platform | 一個 control tower 管四條 production + research loops | ≥99% scheduled-run reliability；100% production predictions 有 immutable provenance；零 stale/partial deploy；多個完整賽季 forward evidence；incident recovery、portfolio exposure、模型退役全部可視化 |

## Ordered Work

- [x] NBA alignment code：daily scheduler、snapshot、reflector、archive、health、Telegram、launchd、fault tests。
- [ ] Stage 2B／3B production closure：engineering items（capability matrix、ADRs、四線 adapters、canonical IDs、run states／manifest／lock／retry、schedule/freshness、wrapper code、fault matrix）已完成；餘下 AU production checkout部署同 runtime manifest smoke。
- [x] NBA odds freshness policy：21:00 warm-up、00:30 production、06:30只刷新未開賽場次並保留 snapshots；role-specific launchd已載入。
- [ ] NBA deferred live gate：2026-27 第一個有盤日 pregame/postgame smoke、零漏場、零未核實 archive、30 個 forward settled recommendations。
- [ ] Shared evidence schema：PredictionRecord、DecisionRecord、SettlementRecord、ModelRelease manifest。
- [ ] Domain truth debt：AU point-in-time/draw audit；HKJC forward corpus；Tennis active-family revalidation；NBA settled ledger/bootstrap baseline。
- [ ] Promotion registry：shadow/paper/limited gates、candidate PR、rollback manifest。
- [ ] Research runner：固定 dataset/ruler、ablation、walk-forward、leakage、experiment report。
- [ ] Control tower：operational health、model health、portfolio risk、incidents、research queue。

## Stage Review Protocol

每次準備轉 stage，都要更新本檔 `Current Stage`，並新增一行 transition record；同一次 review 必須跑 `./檢查.sh`、`./健康.sh`，保存 baseline metrics、未解風險、rollback target 同下一 stage owner。任何 exit gate 未過，只可以延長現 stage，唔可以用改 ruler／改 holdout 當作通關。

## Transition Record

| Date | From → To | Evidence | Decision |
|---|---|---|---|
| 2026-08-25 | Stage 3 portfolio → Stage 4A | AU/HKJC/Tennis automation live；NBA 未有 scheduler/health/settled canonical history | 開始 NBA alignment，Stage 4B 暫不展開 |
| 2026-08-26 | Stage 4A readiness review | NBA full scan 修正日期、coverage、season、schema、ML fallback、settlement、release gates；fault tests 綠；未有 2026-27 live archive | 留喺 Stage 4A，第一個 live pre/postgame gate 過先進 Stage 4B |
| 2026-08-26 | Roadmap normalization | 舊 stage 將 domain engines、統一平台、domain automation、production governance 混為同一層 | 先做 Stage 2B／3B engineering closure；維持 Stage 4A；NBA live gate deferred；之後開始 Stage 4B implementation |
| 2026-08-26 | Stage 2B／3B engineering review | 四線 manifest-backed adapters／wrapper code、schedule/freshness policy、fault matrix、NBA role-specific launchd；quick/full checks同health exit 0；NBA startup dormant manifest smoke | Engineering gate pass；Stage 4B只做 schema/design；AU獨立production checkout啟用並有runtime manifest後先開始implementation；NBA live evidence gate繼續 deferred |
