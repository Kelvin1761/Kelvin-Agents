# Wong Choi Stage 5 Immutable Dataset Resolver — 2026-08-31

## Verdict

**Task 3 engineering checkpoint pass，等待獨立code release；Task 4 runner及domain adapters尚未開始。** Resolver只接收adapter已正規化嘅JSONL，凍結point-in-time dataset同`DatasetManifest`；唔會執行domain scoring、計metric、改model／ruler、排production job或提出promotion。

## Contract

- 每行固定為`row_id／event_at／available_at／payload`，未知或缺失欄位、naive timestamp、availability早過event、重複row ID及非object payload全部fail closed。
- HOT必須實體存在並符合預先聲明嘅directory digest；WARM額外要求`wong-choi-artifact/v1` catalog、destination、domain同source／destination digest一致；COLD只可先restore，唔可直接餵research run。
- `available_at`同source watermark都不可越過terminal PIT cutoff；row availability亦不可遲過自己source watermark。`event_at`固定分入train／dev／terminal，三個split都不可為空。
- 正規化rows按event／row ID排序，rows、split、source watermark、policy同spec產生deterministic SHA-256；相同輸入重跑回傳同一snapshot及`duplicate`。
- Snapshot以partial directory寫入再atomic rename；outer／nested manifest、source／split／rows都有strict schema同digest。即使重算self-hash，任何額外欄位、內容竄改、row count錯誤、既有sample hash衝突、nested symlink或未驗證來源全部拒絕。
- 可指定previous snapshot作corpus floor；舊row消失或同一row ID歷史內容改變會分別以`corpus shrink`或`historical row mutation`攔截，唔會靜靜縮細／重寫樣本。

## TDD Evidence

- RED 1：`research_dataset`未存在，test collection以`ModuleNotFoundError`失敗。
- GREEN 1：HOT／WARM resolve、三段split、same-input duplicate、material-change new hash、future row、digest mismatch、COLD及corpus floor基本測試通過。
- RED 2：previous manifest只加尾部空白仍被接受，顯示未做到byte-for-byte immutable。
- GREEN 2：loader要求manifest完全符合canonical bytes，manifest／rows任何竄改都fail closed。
- RED 3：在previous snapshot加入未知欄位並重算合法self-hash，舊loader錯誤接受。
- GREEN 3：outer／nested manifest、source、row同split全部按exact schema、lineage及digest重建驗證；未知欄位一律拒絕。
- Resolver tests：18 passed；連Task 2 registry focused gate合共37 passed。
- `./檢查.sh --quick`：ruff、AU／HKJC golden各120匹及模型說明全部通過；clean worktree冇近期評分archive，所以data-contract明確skip。
- `./檢查.sh` final gate：1,390個Python tests passed（另2 xfailed、4 skipped），Dashboard Node 69 checks passed；全部suite全綠。
- `./健康.sh`：exit 0、冇嚴重問題；四線排程、production provenance、WARM同COLD正常。既有HOT低過30GB floor、AU Google Drive best-effort mirror permission、NBA off-season未有新季ledger等warning保留，Task 4 heavy runner啟用前必須受capacity／production lock gate約束。

## Deliberately Deferred

- 四個domain raw corpus點樣轉成固定JSONL屬Task 4 adapter，shared resolver唔會猜測domain schema或import domain weights。
- Queue、production preemption、single heavy worker、WARM scratch、容量預估、timeout、resource accounting同cleanup manifest屬Task 4。
- Evaluation statistics、leakage／ablation、自動review、Dashboard／Telegram同domain pilots屬Task 5–9。
- Task 3完成唔代表Tennis／NBA model成熟，亦唔授權model promotion、merge、activation或bankroll action。
