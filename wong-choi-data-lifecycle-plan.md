# Wong Choi Data Lifecycle

## Goal

將低頻歷史資料安全搬離細容量SSD，同時保持日常automation、完整研究語料、backup同restore可驗證。

## Tasks

- [x] 量度容量同最大增長源；外置碟mount／free-space、Drive TCC同SSD threshold可由中央`storage`查到。→ Verify：`central_wong_choi.py storage --scan --json`。
- [x] 凍結HOT／WARM／COLD責任同「copy→hash→restore→second copy→approval→remove」閘。→ Verify：ADR-005 accepted。
- [x] 建立append-only artifact catalog同idempotent archive executor／restore／COLD mirror；default只copy，永不自動刪來源。→ Verify：duplicate/conflict、disk-unmounted、partial-copy、hash mismatch tests。
- [ ] 先處理Tennis migration DB snapshots；成功restore同第二份copy後，另行批准移除約2.9 GB本機副本。→ Verify：SQLite integrity check、SHA-256一致、cold copy可讀。
- [ ] AU／HKJC／NBA／Tennis full-history readers改用multi-root catalog，外置碟唔在時fail loudly，唔准縮細語料照出研究結論。→ Verify：online/offline corpus count固定、offline full-eval exit non-zero。
- [ ] 每晚輸出Cloudflare D1 betting ledger／audit snapshot到evidence，再去WARM／COLD；Dashboard可顯示backup freshness。→ Verify：export count/hash同D1一致、restore到空DB通過。
- [ ] 將storage pressure、archive backlog、last verified backup加入`健康.sh`同Telegram；只喺安全閘過後自動tier。→ Verify：22 GiB情境告警、unmounted disk只defer、零資料遺失。
- [ ] 做一次production restore drill同30日容量forecast，再批准retention cutover。→ Verify：抽樣AU/HKJC/Tennis/NBA artifact可由catalog完整重播。

## Done When

- [ ] SSD長期保持至少30 GiB可用，日常automation唔依賴外置碟或Drive。
- [ ] 所有離線資料有hash catalog同最少兩份verified copy；任何full-history研究唔會靜靜漏資料。
