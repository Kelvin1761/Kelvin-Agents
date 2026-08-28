# Wong Choi Data Lifecycle

## Goal

將低頻歷史資料安全搬離細容量SSD，同時保持日常automation、完整研究語料、backup同restore可驗證。

## Tasks

- [x] 量度容量同最大增長源；外置碟mount／free-space、Drive TCC同SSD threshold可由中央`storage`查到。→ Verify：`central_wong_choi.py storage --scan --json`。
- [x] 凍結HOT／WARM／COLD責任同「copy→hash→restore→second copy→approval→remove」閘。→ Verify：ADR-005 accepted。
- [x] 建立append-only artifact catalog同idempotent archive executor／restore／COLD mirror；default只copy，永不自動刪來源。→ Verify：duplicate/conflict、disk-unmounted、partial-copy、hash mismatch tests。
- [x] Tennis三個migration DB snapshots（4,387,000,320 bytes）已copy到WARM、content hash一致、由WARM restore後三個SQLite `integrity_check=ok`；HOT原件保留。→ Verify：artifact `wc-artifact:5f6c9a118c80bfab16addb33`、restore event `wc-artifact-restore:15c2c38cdd1de675841435c5`。
- [ ] 為Tennis snapshots建立COLD verified copy；之後另行批准先可移除HOT本機副本。→ Verify：cold mirror event、Google Drive copy可讀、source-removal獨立approval。
- [ ] AU／HKJC／NBA／Tennis full-history readers改用multi-root catalog，外置碟唔在時fail loudly，唔准縮細語料照出研究結論。→ Verify：online/offline corpus count固定、offline full-eval exit non-zero。
- [x] 建立Cloudflare D1 betting ledger verified export：stable前後remote counts、SQL SHA-256、空SQLite restore、integrity／foreign-key／row-count gate、WARM archive同Central freshness projection。首次live snapshot含108 bets／30 settlements／30 audit rows。→ Verify：artifact `wc-artifact:a44a5a1a9a2f5e2bd4fd58ae`；`dashboard-backup-status=ok`。
- [ ] 啟用每日03:20 central durability launchd並設定COLD root；installer已納入approved release activation allowlist。→ Verify：launchd status、下一個自然日run log、Telegram、WARM／COLD皆verified。
- [ ] 將archive backlog同安全retention cutover加入自動tier；storage pressure同last verified D1 backup已加入`健康.sh`、Telegram `/storage`／`/dashboard`。→ Verify：22 GiB情境告警、unmounted disk只defer、零資料遺失。
- [ ] 做一次production restore drill同30日容量forecast，再批准retention cutover。→ Verify：抽樣AU/HKJC/Tennis/NBA artifact可由catalog完整重播。

## Done When

- [ ] SSD長期保持至少30 GiB可用，日常automation唔依賴外置碟或Drive。
- [ ] 所有離線資料有hash catalog同最少兩份verified copy；任何full-history研究唔會靜靜漏資料。
