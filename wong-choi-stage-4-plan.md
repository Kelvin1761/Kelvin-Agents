# Wong Choi Stage 4 Production／Evidence Plan

## Goal

將四條已獨立運行嘅 domain engine升級成可量度可靠性、可追溯每個決定、可重播結算、可受控升級嘅 production platform；中央層永遠唔改寫 AU、HKJC、Tennis、NBA各自嘅 scoring同評估尺。

## Sequencing Decision

- Stage 4A係持續營運底座；先補齊剩餘 health、snapshot、recovery同SLO缺口，同時保持現役排程運行。
- Stage 4B由 AU做第一個 vertical slice，再接 Tennis、HKJC、NBA；唔先做一個空泛大平台。
- Stage 4C係完整 Step 4嘅最後閘：有 evidence ledger之後，先建立 champion／challenger同 human-approved promotion。
- NBA engineering唔等新季，但全平台 `production-proven` 標記要等2026-27首個有盤日、完場日及最少30個 forward settled recommendations。

## Tasks

- [ ] 1. 接納中央治理層ADR並凍結 Stage 4 baseline：四個 engine獨立、未知狀態fail closed、production prediction不可覆寫、評估尺不可同候選一齊改；先審核目前 AU `stale-baseline` engine hash，將「rollback非預期改動」或「獨立確認後calibrate」記成明確決定。→ Verify：ADR status=`Accepted`；AU baseline重新可信；architecture tests證明中央層冇import domain scoring。
- [ ] 2. 完成 Stage 4A canonical health／SLO：四線輸出同一 health schema、last-success、freshness、settlement lag、publish state、Telegram dedup同incident ID。→ Verify：`健康.sh`可機讀四線狀態；partial／stale／missing source全部阻止publish；建立30日scheduled-run reliability報表。
- [ ] 3. 完成 Stage 4A immutable snapshot／recovery：AU、Tennis補齊 prediction manifest，四線記錄source hash、odds timestamp、code commit、model version同artifact hash；演練重跑、斷網、重啟、rollback。→ Verify：同一 prediction ID不可覆寫；recovery只開新attempt；restore演練唔改舊prediction。
- [ ] 4. 完成 Stage 4A settlement／operations gate：四線 settlement只有`hit|miss|void|unverified`，`unverified>0`不得封存；Telegram清楚分operational、bet card、review。→ Verify：四線fault matrix、launchd smoke、`./檢查.sh`、`./健康.sh`全綠；AU／Tennis／HKJC下一個真實scheduled manifest通過。
- [ ] 5. 建立 Stage 4B evidence schema同append-only store：`PredictionRecord → DecisionRecord → SettlementRecord → ModelRelease`；canonical JSON係真源，SQLite只做可重建索引。→ Verify：schema versioning、unique ID、content hash、foreign-key chain、duplicate/conflict fixtures全部通過。
- [ ] 6. 逐線接入 evidence writer：AU first，之後 Tennis、HKJC、NBA；adapter只映射現有output，唔重新計分。→ Verify：每條正式建議可追到event/run/source snapshot/model release；shadow／no-bet亦有decision record；舊domain輸出byte-for-byte不變。
- [ ] 7. 建立 settlement linker同 replay verifier：用賽果連回原prediction及當時odds，禁止使用較後snapshot；歷史backfill標記`historical`，不可冒充forward。→ Verify：抽樣event可由零重播到同一decision；future-data/leakage fixture必須被block；orphan及unverified清單可查。
- [ ] 8. 完成 Stage 4C model registry／promotion gate：每個domain獨立管理`research→shadow→paper→limited→production→retired`，記錄ruler、dataset、baseline、candidate、rollback target同人手批准。→ Verify：冇足夠holdout／forward evidence、改尺、負回歸或缺rollback嘅candidate不可promotion；系統可開PR但不可auto-merge或auto加注。
- [ ] 9. 做 Stage 4 exit review：保存SLO、forward coverage、settlement completeness、replay、model-release同rollback證據，更新roadmap transition record。→ Verify：100%新production decisions有完整provenance；零stale/partial publish；四線各有一次成功restore/replay；NBA未過live gate時全平台只可標記`engineering complete / NBA evidence pending`。

## Done When

- [ ] 中央 Wong Choi可回答「今日四條線有冇安全運行、推介由邊個模型／邊批數據產生、結果如何、可否重播、下一個候選可否升級」。
- [ ] 中央層只做control、evidence、risk、governance同display；任何domain scoring改動仍要返各自engine及evaluation contract處理。
- [ ] 每次完成4A、4B、4C都更新本計劃、platform roadmap、exit audit、未解風險同下一階段owner。
