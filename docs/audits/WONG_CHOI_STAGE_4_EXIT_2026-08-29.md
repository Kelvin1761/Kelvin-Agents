# Wong Choi Stage 4 Exit Audit — 2026-08-29

## Verdict

**Engineering deployment complete；final production exit pending。**

Stage 4 control plane、release governance、四線runtime cutover、model registry、append-only evidence、Dashboard／D1 durability同HOT／WARM／COLD catalog已部署。Stage 4尚未正式close，因為production provenance仍係`no_data`，而HOT SSD已跌穿20 GiB operational gate。

## Requirement Evidence

| Requirement | Evidence | Verdict |
|---|---|---|
| Scoped commit／push／merge／activation | Release `wc-release:cb17d2f0860e:2026-08-29T090816.199184_0000`有immutable manifest、rollback target `8b149c85aafa`，同完整`approval_granted → merged → activation_started → activation_succeeded` events。 | PASS |
| Approval gate可重現 | Commit `cb17d2f0860e31d681240a852fc513ee1264fc39`喺全新clean clone跑`./檢查.sh`全綠；AU/HKJC golden各120匹一致。 | PASS |
| Production Git一致 | `cb17d2f0860e`完成統一cutover後，AU automation fix `cfb3a9747cc3`再將`origin/main`同`/Users/imac/wongchoi-scheduler`一齊前進；production checkout只保留已知runtime data mutation `sb_archive_meeting_ids.json`。 | PASS |
| Main／production release trail | `cfb3a9747cc3`進入main同production時冇Central release manifest，舊status只顯示`pushed=true／merged_to_main=true`。本次修正加入exact-HEAD manifest tracking；未受控main／production commit會fail visible並出Telegram attention，亦唔會retroactively偽造approval。 | PASS（detector deployed with this audit） |
| 四線runtime同Central一致 | Installed-plist verifier：AU 4/4、HKJC 6/6、NBA 6/6、Tennis 3/3、Central 1/1，全部loaded／aligned，attention空白。 | PASS |
| Model governance | AU／HKJC係production；Tennis／NBA係shadow。Gold／Good係primary；ranking-only只可喺primary無回歸兼過預先指定statistical gate時接受。 | PASS |
| Evidence integrity | Append-only audit：4 model releases、1 prediction、1 decision、1 settlement，零schema／link／hash錯誤。 | PASS |
| Dashboard D1 durability | Snapshot `20260829T131349.165633Z` remote row counts前後一致；SQLite `integrity_check=ok`、0 foreign-key errors、restore row counts一致。WARM digest同Google Drive full-download directory digest均為`a9fac71cd5ef3e9784656efbe876c4ffed12314677a7efbf0336f5331414faea`。 | PASS |
| Nightly durability runtime | `com.antigravity.central-wong-choi.durability`已loaded；部署後kickstart最新exit code 0，同日snapshot走idempotent dormant path。 | PASS |
| Storage second copy | WARM mounted；catalog 4/4 artifacts有owner-only Google Drive full-download proof；所有HOT source仍保留。 | PASS |
| Production decision provenance | Reliability report：`production_decisions=0`、`fully_traced=0`、`status=no_data`。未有部署後正式production decision可證明100% provenance。 | PENDING |
| Operational health | `./健康.sh`確認data contract同automation可用，但內置SSD只餘約16–18 GiB，觸發停止重型research／backfill；AU Drive mirror另有非致命TCC warning。 | PENDING |
| NBA live acceptance | 六階段classifier、automation、snapshot及evidence integration已部署；新季首個live pregame／postgame仍未發生。 | PENDING（engineering complete / live evidence pending） |

## Remaining Exit Gates

1. 下一個合法production decision必須由真實scheduled run產生，並有model release、source cutoff、prediction、decision同settlement完整links；唔接受人造或賽後補寫決策冒充live evidence。
2. 在有至少一個production decision後重跑`central_wong_choi.py slo`，要求production provenance係100%。
3. HOT SSD恢復到20 GiB以上先解除hard block；任何source deletion必須另有scoped human approval，並先過copy／hash／restore／second-copy gate。
4. NBA只可喺2026–27首個真實pregame同postgame acceptance通過後，更新`live evidence pending`狀態。

## Safe Current Operating Mode

- 日常prediction／settlement automation繼續運行。
- 暫停重型research、full-history backfill同大型模型搜尋。
- Central Telegram繼續提供`/status`、`/git`、`/models`、`/evidence`、`/storage`、`/dashboard`；高風險release繼續用`/approve SHA`。
- 不刪HOT source，不將Tennis／NBA提升到production model stage。
