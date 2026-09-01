# Wong Choi Data Lifecycle

## Goal

將低頻歷史資料安全搬離細容量SSD，同時保持日常automation、完整研究語料、backup同restore可驗證。

## Tasks

- [x] 量度容量同最大增長源；外置碟mount／free-space、Drive TCC同SSD threshold可由中央`storage`查到。→ Verify：`central_wong_choi.py storage --scan --json`。
- [x] 凍結HOT／WARM／COLD責任同「copy→hash→restore→second copy→approval→remove」閘。→ Verify：ADR-005 accepted。
- [x] 建立append-only artifact catalog同idempotent archive executor／restore／COLD mirror；default只copy，永不自動刪來源。→ Verify：duplicate/conflict、disk-unmounted、partial-copy、hash mismatch tests。
- [x] Tennis三個migration DB snapshots（4,387,000,320 bytes）已copy到WARM、content hash一致、由WARM restore後三個SQLite `integrity_check=ok`；第四個pre-surface snapshot（1,246,789,632 bytes）亦已WARM copy、restore同`integrity_check=ok`；HOT原件保留。→ Verify：artifacts `wc-artifact:5f6c9a118c80bfab16addb33`、`wc-artifact:bdcad6e5e530b9e857b170a5`；restore events `wc-artifact-restore:15c2c38cdd1de675841435c5`、`wc-artifact-restore:10ec79aaeb563837b7268e87`。
- [x] Tennis兩個artifacts已建立owner-only Google Drive COLD：32MiB ordered parts逐片full-download SHA全過，manifest SHA全過，重組後5,633,789,952 bytes／4 files artifact digests全過，四個restored SQLite `quick_check=ok`；HOT仍保留。→ Verify：events `wc-artifact-remote-mirror:9209eb0b56ee775a00f0e9eb`、`wc-artifact-remote-mirror:2b2c3595569d188502888a5d`；source-removal仍要獨立approval。
- [x] 建立catalog resolver同`corpus-audit`：每個已知artifact必須由HOT或WARM至少一份content hash完整，兩份missing／corrupt會exit non-zero；AU／HKJC meeting research reader已接入，並按logical meeting name去重。→ Verify：HOT fallback、WARM fallback、雙失聯fail-closed、跨root duplicate tests；真實Tennis 4.387GB audit兩份verified。
- [x] NBA settled-day ML reader已合併HOT同catalog-verified WARM day folders；Tennis mutable SQLite已有active-vs-snapshot audit，snapshot只讀且不可當live DB。真實active DB同4份snapshots `quick_check=ok`，active counts 4690 matches／5552 results／9503 odds沒落後snapshot watermarks。→ Verify：NBA HOT／WARM merge test／known archive offline fail-closed；`corpus-audit --domain tennis --active-sqlite ...`。
- [x] 建立Cloudflare D1 betting ledger verified export：stable前後remote counts、SQL SHA-256、空SQLite restore、integrity／foreign-key／row-count gate、WARM archive、owner-only Google Drive full-download digest同Central freshness projection。首次live snapshot含108 bets／30 settlements／30 audit rows。→ Verify：artifact `wc-artifact:a44a5a1a9a2f5e2bd4fd58ae`；`dashboard-backup-status=ok`、`cold_provider=google_drive`。
- [ ] 啟用每日03:20 central durability launchd並設定COLD root；installer已納入approved release activation allowlist。→ Verify：launchd status、下一個自然日run log、Telegram、WARM／COLD皆verified。
- [ ] 將archive backlog同安全retention cutover加入自動tier；storage pressure、D1 backup同catalog artifact COLD coverage已加入Central、`健康.sh`、Telegram `/storage`／`/dashboard`。→ Verify：19 GiB情境繼續critical；provider-backed COLD 3/3可見；unmounted disk只defer；零資料遺失。
- [ ] 做一次production restore drill同30日容量forecast，再批准retention cutover。→ Verify：抽樣AU/HKJC/Tennis/NBA artifact可由catalog完整重播。

## Done When

- [ ] SSD長期保持至少30 GiB可用，日常automation唔依賴外置碟或Drive。
- [ ] 所有離線資料有hash catalog同最少兩份verified copy；任何full-history研究唔會靜靜漏資料。
