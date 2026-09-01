---
name: central-wong-choi
description: Use when the user asks for central Wong Choi status, git/release/deployment state, four-domain health, evidence provenance, model registry, controlled promotion, or Stage 4 governance across AU, HKJC, Tennis and NBA Wong Choi.
---

# Central Wong Choi

中央旺財係 governance/control plane，唔係第五個 prediction engine。AU、HKJC、Tennis、NBA 各自保留 scoring、ranking、evaluation contract 同 domain authority。

## Routing

- 想睇全局：跑 `scripts/central_wong_choi.py status`。
- 想分開睇 git、models、evidence、30日可靠性、Dashboard或storage：用對應 `git`、`models`、`evidence`、`slo`、`dashboard`、`storage` subcommand。
- 想立即做Dashboard D1 verified backup：用`dashboard-backup`；只讀remote D1，必須stable前後row counts、空SQLite restore、hash同WARM gate全過。用`dashboard-backup-status`睇freshness。
- 想裝每晚Central durability：release activation只可自動執行allowlisted `install_macos_launchd.sh`；每日悉尼03:20，同日verified local snapshot會idempotent skip。外置碟受launchd TCC／offline時必須記`deferred`而唔係抹走本機restore證據，second-device copy由有權限嘅foreground `./備份.sh`補上。
- 想將四線切去同一approved checkout：只可經allowlisted `install_production_runtime.sh`；佢會保留AU poller、transactional snapshot／restore HKJC、NBA、Tennis、Central plists，再以read-only verifier證明全部loaded及對齊。Tennis code切去production checkout，但live DB／venv interpreter／logs／Google Drive output留喺原位。
- 想驗證控制資料可復原：用 `restore-drill --destination <全新路徑>`；永不覆寫既有目的地。
- 想安全歸檔低頻資料：先用`archive-copy`，只會copy＋hash＋append manifest，唔會刪source；用`archive-restore`去全新目的地驗證，再用`archive-mirror`建立COLD第二副本。
- Connector-backed COLD copy完成full download directory digest後，用`archive-remote-proof`記append-only provider／remote ID／canonical URL；hash唔等於WARM catalog會block。
- `storage`要分開filesystem COLD root同provider-backed catalog coverage；Google Drive proof完整時唔准因local COLD root未設定而報「只有一份copy」。
- Full-history research前用`corpus-audit --domain <domain>`；任何catalog已知artifact喺HOT同WARM都missing／corrupt會exit non-zero，唔准用縮細語料出結論。Tennis另用`--active-sqlite <tennis_wc.db>`檢查live DB integrity同row-count watermarks；archived snapshot只讀，永不可代替live DB。
- 想保存改動：先 dry-run `release`，只傳今次明確 scope；禁止 `git add -A`。
- 想改任何 domain prediction/scoring：轉返該 domain skill，中央層只記錄 evidence 同 promotion decision。
- 想批准高風險 release：跟 `references/01_release_and_approval.md`；approval 必須綁 immutable commit。
- Telegram governance writes只可由configured chat經authenticated dispatcher呼叫：`/approve SHA`做recheck／merge／activate；activation成功、四線同SHA、已入main、registry空白先可`/bootstrap_models SHA`做一次baseline migration。
- 首次production bot未有`/approve`時，只可用`bootstrap_telegram_approval.sh SHA`暫停舊poller五分鐘，由candidate bot共用同一offset接收一次immutable approval；無論成功、失敗或timeout都要restore production poller。
- 想判斷 model candidate：跟 `references/02_evidence_and_model_governance.md`，再讀該 domain evaluation contract。

## Hard Rules

1. 中央層不得重算分數、改 rank、共用四線 weights 或製造跨 domain 信心分。
2. Canonical JSON evidence append-only；SQLite 只可做可重建 index。
3. Docs/tests-only 可通過 gate 後自動 merge；code/model/evaluation/automation/deployment 要白名單 Telegram approval。
4. Approval 前重新驗證 commit、origin/main、gate、scope 同 rollback target；任何一項變咗就 block。
5. Post-sync verifier／installer／deploy任何失敗都要嘗試退回captured production SHA；runtime mapping做union且runtime值優先。見到unrelated concurrent write就停止rollback、記critical event，唔准抹走。
6. Gold/Good 係 AU/HKJC primary；ranking-only candidate 必須 primary 無回歸兼過預先定義 statistical gate。
7. NBA live evidence 未齊，只可標 `engineering complete / live evidence pending`。
8. Dashboard係中央control tower；D1係實際投注ledger，append-only Evidence係模型證據，Dashboard唔准重算prediction。
9. WARM／COLD搬檔必須copy/hash/restore/second-copy先可另行批准刪本機；外置碟offline唔准靜靜縮細研究語料。
10. D1 backup只准remote SELECT/export；export期間row count變動要重試，local restore／integrity／foreign key／row count未全過唔准寫成功manifest。
11. NBA full-history ML只可使用HOT目錄加catalog-verified WARM settled-day corpus；已知archive offline必須fail closed。
12. Runtime status必須讀已安裝launchd plist及loaded state，唔可以用repo入面template或「installer曾經成功」代替；legacy scheduler仍active、domain run進行中或Tennis SQLite quick-check失敗一律block cutover。

## Output Contract

每次回覆最少講清楚：

- git：dirty／committed／pushed／merged；
- activation：未開始／已部署／失敗／rollback；
- 四線 run health 同 model release stage；
- Dashboard／D1 ledger同HOT／WARM／COLD storage狀態；
- pending approval 或 evidence gap；
- 下一個可安全執行動作。
