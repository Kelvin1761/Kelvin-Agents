# Wong Choi Platform Roadmap

## Goal

將 AU、HKJC、Tennis、NBA 四條獨立模型線，逐步升級成一個可追溯、可重播、可結算、可安全研究嘅 Wong Choi Decision Platform；共用營運與證據層，但永不合併 domain scoring engine。

## Current Stage

**Stage 2B／3B complete；Stage 4A／4B／4C engineering candidate已完成；Stage 4D storage／Dashboard foundation已完成，durability cutover進行中。** AU／HKJC可登記production；Tennis因holdout ROI／Brier未過只可shadow，NBA因2026-27 live evidence未齊亦只可shadow。中央旺財擁有control tower／Dashboard，但唔係第五個預測模型。

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
| 4D Data Durability + Central Dashboard | HOT／WARM／COLD lifecycle；Dashboard納入中央旺財，連接analysis、evidence同D1 betting ledger | archive copy/hash/restore/second-copy gate；SSD pressure可見；Dashboard不可重算prediction；D1可export/restore；offline cold corpus唔會靜靜縮細研究 |
| 5 Automated Research Platform | 可重現實驗 runner、ablation、walk-forward、leakage scan、報告索引 | 同一命令可重跑 baseline/candidate；失敗實驗照記；跨 domain 共用工具但 domain ruler 分開 |
| 6 Semi-autonomous Model Lab | Agent 提假設、跑實驗、淘汰候選、開 evidence-backed PR | Agent 無權改 ruler、holdout、production 或 bankroll；所有 promotion 有 human approval；完整 audit trail |
| 7 Wong Choi Decision Platform | 一個 control tower 管四條 production + research loops | ≥99% scheduled-run reliability；100% production predictions 有 immutable provenance；零 stale/partial deploy；多個完整賽季 forward evidence；incident recovery、portfolio exposure、模型退役全部可視化 |

## Ordered Work

- [x] NBA alignment code：daily scheduler、snapshot、reflector、archive、health、Telegram、launchd、fault tests。
- [x] Stage 2B／3B production closure：capability matrix、ADRs、四線 adapters、canonical IDs、run states／manifest／lock／retry、schedule/freshness、wrapper、fault matrix同 AU production checkout activation全部完成。
- [x] NBA odds freshness policy：21:00 warm-up、00:30 production、06:30只刷新未開賽場次並保留 snapshots；role-specific launchd已載入。
- [ ] NBA deferred live gate：2026-27 第一個有盤日 pregame/postgame smoke、零漏場、零未核實 archive、30 個 forward settled recommendations。
- [x] Shared evidence schema：append-only PredictionRecord、DecisionRecord、SettlementRecord、ModelRelease manifest；四線 writer 已接入 publication／settlement 前置閘。
- [ ] Domain truth debt：AU point-in-time/draw audit；HKJC forward corpus；Tennis active-family revalidation；NBA settled ledger/bootstrap baseline。
- [x] Promotion registry：research→shadow→paper→limited→production→retired、forward evidence、human approval、rollback manifest。
- [ ] Research runner：固定 dataset/ruler、ablation、walk-forward、leakage、experiment report。
- [x] Control tower foundation：Git／release／deployment／四線 run health／model stage／evidence／30日 SLO／Telegram approval；portfolio risk同research queue留Stage 5。
- [x] Central Dashboard ownership：四線analysis同中央health/evidence projection；D1 `WC_LEDGER`保存實際投注，Dashboard永不做第五個scoring engine。
- [ ] Storage durability cutover：Tennis 4.387 GB snapshots WARM copy／restore已過；D1 108 bets／30 settlements／30 audit live export、空DB restore同WARM已過；尚欠COLD mirror、nightly production activation同multi-root readers。
- [ ] Tennis maturity workstream（Stage 5首個consumer）：維持shadow；用固定untouched forward gate逐family判斷，唔用完成平台stage當作model promotion。

## Stage Review Protocol

每次準備轉 stage，都要更新本檔 `Current Stage`，並新增一行 transition record；同一次 review 必須跑 `./檢查.sh`、`./健康.sh`，保存 baseline metrics、未解風險、rollback target 同下一 stage owner。任何 exit gate 未過，只可以延長現 stage，唔可以用改 ruler／改 holdout 當作通關。

## Transition Record

| Date | From → To | Evidence | Decision |
|---|---|---|---|
| 2026-08-25 | Stage 3 portfolio → Stage 4A | AU/HKJC/Tennis automation live；NBA 未有 scheduler/health/settled canonical history | 開始 NBA alignment，Stage 4B 暫不展開 |
| 2026-08-26 | Stage 4A readiness review | NBA full scan 修正日期、coverage、season、schema、ML fallback、settlement、release gates；fault tests 綠；未有 2026-27 live archive | 留喺 Stage 4A，第一個 live pre/postgame gate 過先進 Stage 4B |
| 2026-08-26 | Roadmap normalization | 舊 stage 將 domain engines、統一平台、domain automation、production governance 混為同一層 | 先做 Stage 2B／3B engineering closure；維持 Stage 4A；NBA live gate deferred；之後開始 Stage 4B implementation |
| 2026-08-26 | Stage 2B／3B engineering review | 四線 manifest-backed adapters／wrapper code、schedule/freshness policy、fault matrix、NBA role-specific launchd；quick/full checks同health exit 0；NBA startup dormant manifest smoke | Engineering gate pass；Stage 4B只做 schema/design；AU獨立production checkout啟用並有runtime manifest後先開始implementation；NBA live evidence gate繼續 deferred |
| 2026-08-26 | Stage 2B／3B → Stage 4B entry | Scoped branch已push；AU production checkout對齊 `40724a31`；14/14 deployment files aligned；wrapper dry-run、adapter/control smoke、launchd pointer同global health全部通過 | Stage 2B／3B production closure完成；開始 Stage 4B Evidence Core implementation；NBA live evidence gate維持 deferred |
| 2026-08-27 | Stage 4 release candidate | Evaluation ruler獨立 commit；Stage 4 control/evidence/release platform；clean full gate全綠；實際 restore drill hash一致；30日SLO可計（少於20 slots明確標provisional） | Engineering exit pass；等 immutable release approval、production activation、model bootstrap同Telegram/runtime smoke後先關閉Stage 4 |
| 2026-08-27 | Stage 4D scope review | SSD只剩約22 GiB；外置APFS有約888 GiB；Tennis DB snapshots約2.9 GB；Dashboard已有D1/KV betting ledger；Tennis holdout ROI -6.61%、Brier輸市場 | Stage 4加入data durability同Central Dashboard ownership；Tennis bootstrap由production降為shadow，Stage 5以Tennis做首個research-platform consumer |
| 2026-08-28 | Stage 4D live durability proof | Tennis三個DB snapshots 4.387 GB copy/hash/restore/SQLite全過；live D1 108 bets／30 settlements／30 audit export、空DB restore、WARM hash全過；nightly scheduler idempotency smoke全過 | WARM同D1 gates完成；HOT原件不刪；等COLD設定、production activation同multi-root readers先關閉Stage 4D |
