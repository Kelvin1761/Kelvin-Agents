# Wong Choi Stage 4 Exit Audit — 2026-08-30

## Verdict

**Stage 4 complete：all engineering and hard operational gates pass。**

Stage 4 control plane、policy-based release、四線runtime、model governance、append-only
evidence、Dashboard／D1 durability同HOT／WARM／COLD lifecycle均已production運行。
2026-08-29 audit嘅兩個hard blockers已解除：production provenance由`no_data`變成
13/13完整追溯，HOT free space由低過20 GiB回升到24.25 GiB。最新nightly D1 artifact
已通過restore、WARM同Kelvin明確批准嘅owner-only Google Drive COLD gate；完整下載後嘅
directory digest亦同本機snapshot exact match。Stage 4已冇未完成hard gate。

## Requirement Evidence

| Requirement | 2026-08-30 authoritative evidence | Verdict |
|---|---|---|
| Scoped commit／push／merge／activation | Release `wc-release:6b42ffdfd2ee:2026-08-30T060653.211896_0000`有immutable base manifest；append-only events完整記錄`approval_granted → merged → activation_started → activation_succeeded`。Telegram actor係`telegram:authorised-chat`，rollback target係`eb019673`。 | PASS |
| Production Git一致 | `origin/main`、production checkout同四個production roots全部係`6b42ffdfd2ee414c9efa20fee51c8f7480851b3c`。唯一dirty path係allowlisted runtime mapping `sb_archive_meeting_ids.json`；冇unexpected dirty path。 | PASS |
| 四線runtime同Central一致 | Installed-plist verifier讀實際`~/Library/LaunchAgents`同loaded state：AU 4/4、HKJC 6/6、NBA 6/6、Tennis 3/3、Central 1/1全部aligned，attention空白。 | PASS |
| 自動release policy | `./保存.sh`只接受明確`--path`scope；docs/tests-only可gate後auto-merge，code/model/evaluation/automation/deployment只push並要求authenticated Telegram`/approve SHA`。Activation會capture checkpoint、post-sync verify同transactional rollback。今次AU health fix實際走完整chain。 | PASS |
| Gold／Good primary + ranking squeeze | `docs/model-evaluation-contract.md` v2同共用`model_evaluation_decision.py`已接入AU／HKJC gate。29個shared＋AU＋HKJC integration tests通過：任何Gold／positional-Good dev或terminal回歸即REJECT；`RANKING_WIN`要最少兩個pre-registered ranking metrics跨dev／terminal改善、至少一個terminal paired CI下界>0，且冇ranking metric CI全負。 | PASS |
| Model stage | AU／HKJC model stage係production；Tennis／NBA係shadow。中央層冇重算分數、共用weights或自行promotion。 | PASS |
| Evidence integrity | Central audit：17 prediction、17 decision、1 settlement、4 model release，零schema／link／hash錯誤。Production decisions 13，fully traced 13，provenance 100%。 | PASS |
| Live AU dashboard | Production JSON `generated_at=2026-08-30T15:58:32`，7個AU meeting、50場，Carnarvon／Casterton／Echuca／Mudgee／Strathalbyn／Townsville／Wyong全部在場；payload約8.85 MB，低過Cloudflare 25 MiB gate。 | PASS |
| Live Tennis feed | `tennis:2026-08-30`係`validation_status=valid`：78 fixtures、39 Sportsbet-priced singles、39/39 modelled、0 unmodelled priced；0 recommendations係valid no-bet。18:00 scheduled run其後成功寫入Central manifest。 | PASS（model仍係shadow） |
| NBA lifecycle | 六階段classifier、off-season dormant、pregame／postgame／health／snapshot／reflector automation均loaded。2026-08-30最新run係dormant，符合休季；2026–27首個live pregame/postgame證據仍未發生。 | PASS（engineering）；live evidence pending |
| Dashboard D1 durability | Snapshot `20260829T233815.476479Z`有stable remote row counts、SQLite restore、integrity／foreign-key／row-count gate；108 bets、30 settlements、30 audit rows。HOT restore、WARM digest同COLD digest verified，age 11.09h。 | PASS |
| HOT／WARM storage | HOT free 24.25 GiB，已高過20 GiB hard floor但低過30 GiB warning floor；WARM外置碟mounted，883 GiB可用。`./健康.sh`結論係「冇嚴重問題」。 | PASS with warning |
| Latest provider-backed COLD copy | Catalog 5/5 verified。Kelvin明確批准上載最新D1 artifact `wc-artifact:635c1b0f5f9abb4662d9fe4c`；Google Drive folder係owner-only、`shared=false`。完整下載`manifest.json`同`wongchoi-ledger.sql`後重算directory digest：`85b99f0fd1662f89d9d6e69c6f756a819ec6aab95ebbae1496c5cc5f01cc10b7`、131,020 bytes、2 files，exact match；append-only event係`wc-artifact-remote-mirror:3c8924b639798e212a191a0e`。 | PASS |

## Completed Formal Close Action

1. Kelvin已明確批准將最新D1 snapshot（131,020 bytes；含投注ledger）上載到
   `kelvin1761@gmail.com` owner-only、`shared=false`嘅Google Drive folder。
2. 兩個遠端檔案已完整下載並通過exact digest、bytes同file-count驗證。
3. Remote proof已append；`central_wong_choi.py storage`顯示D1 `cold_verified=true`、
   catalog 5/5 verified，`./健康.sh`顯示冇嚴重問題。HOT／WARM source全部保留。

## Non-blocking Ongoing Acceptance

- HOT 20–30 GiB屬warning，重型full-history research要節制；日常automation可繼續。
- AU／Tennis未夠20個30-day SLO slots，所以availability仍係provisional；呢個係樣本成熟度，
  唔係engineering failure。
- NBA保持`engineering complete / live evidence pending`，新季第一個真實pregame同postgame
  要另做live acceptance，唔可以用休季synthetic run冒充。
- Tennis／NBA唔會因Stage 4 close自動升production model stage。
