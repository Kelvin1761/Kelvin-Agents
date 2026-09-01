# Wong Choi Stage 5 Ruler-locked Research Evaluation — 2026-08-31

## Verdict

**Task 5 engineering checkpoint pass，等待獨立scoped code release。** 四個domain而家可將同一不可變dataset上嘅baseline／candidate observations做嚴格配對、walk-forward development fold、terminal holdout、paired bootstrap、cohort guardrail同machine decision；系統只會產生reject、inconclusive、descriptive或shadow-review proposal，唔會promotion、merge、activate model或改注碼。

## Decision Contract

- Evaluation只接受Task 1 frozen ruler原檔SHA、完整pre-registered metric set、固定bootstrap seed同Task 3 dataset manifest／artifact digest；domain、row count、split、row identity、event time、fold、cohort或metric任何不一致都fail closed。
- `evaluate_run_artifact`先核對Task 4 registry登記嘅整個artifact SHA及metrics digest，再以Task 3 immutable rows逐行核對event／split／cohort／fold；兩邊一齊偽造row ID都會被攔。多command outputs必須全部納入，未知schema／duplicate JSON key／non-finite constant不可靜默接受。
- Dev／terminal必須係chronological whole-date partitions，development folds順序不可重疊，事件不可超過dataset cutoff；同時保存baseline／candidate絕對均值、candidate絕對CI及paired delta CI，唔可以只報相對增長。
- AU／HKJC直接重用Stage 4 `model_evaluation_decision.evaluate_candidate`，保留Gold／Good primary先行及兩個獨立ranking signals規則；中央層唔重寫domain scoring或weights。
- Tennis逐family判決，未達600 rows、CI跨零或只得ROI增長一律inconclusive；candidate雖比baseline好但Brier／log loss仍輸市場，或絕對ROI仍負，一律REJECT。市場相對primary同ROI downside CI、calibration／CLV／coverage guardrails及cohort都過先可成為統計上嘅`SHADOW_CANDIDATE`；呢個標籤唔等於通過Task 6安全／power gate。
- NBA喺現有`descriptive_only` ruler下任何正面結果都不可proposal；明確primary／guardrail／cohort regression仍會如實標`REJECT`，避免描述性狀態掩蓋退步。
- Aggregate regression由primary／guardrail contract判決；cohort regression只代表aggregate未跌但某個subgroup有統計支持嘅額外傷害。
- Report先fsync temporary再atomic create-only publish；`ExperimentDecision` content-addressed，同report隔一小時再送會保留首次timestamp而回duplicate。發佈時run／ruler／metrics lineage再核對；成功候選只映射至`shadow_review_proposal`，仍受Stage 4 human approval。

## TDD And Verification Evidence

- RED：模組未存在時collection以`ModuleNotFoundError`失敗。
- 第一輪GREEN 10/12；兩個失敗揭示aggregate primary regression被錯誤優先標成cohort regression，修正判決責任後12/12。
- 加入dataset manifest／artifact lineage、NBA regression、single-ROI non-promotion、subgroup regression及bootstrap reproducibility fixtures後15/15通過。
- Task 2–5 focused integration：84 passed；`./檢查.sh --quick`通過ruff、AU／HKJC各120匹golden同模型說明freshness。clean worktree冇近期評分archive，所以data-contract明確skip。
- 第二輪獨立反例：baseline market gain −0.10、candidate −0.05曾錯判`SHADOW_CANDIDATE`；absolute Brier／log loss／ROI、split／fold chronology及run ruler mismatch共7個RED測試，修正後21/21。
- 第三輪串接：四domain真實Task 4 runner fixture輸出直接經artifact／dataset驗證後評估及append decision；artifact tampering、兩邊配對偽造row、不同重試timestamp共7個RED測試，修正後Task 5合共27 passed。
- 最終focused integration（Tasks 2–5）：96 passed；quick gate全綠。兩個evaluation檔案已用ruff formatter正規化，冇更改任何domain engine／ruler。
- Release環境檢查曾因真實Tennis production job運行而由runtime-installer test defer；冇停job、冇改installer或skip gate，等job結束後Task 3／4各自full gate及clean approval gate通過。
- Production checkout `健康.sh` exit 0：四線schedule及provenance正常，AU 60場／599匹同HKJC 60場／768匹data-contract樣本通過。HOT剩25GB、AU Drive mirror permission、NBA off-season ledger等warning保留；另最新D1 snapshot（2026-08-30 19:20 UTC，早於Task 3／4 release）restore verified但WARM／COLD pending，已獨立標attention，今次純research release唔修改backup／retention流程。

## Prior Scoped Releases

- Task 3 `98702c5249aa999717ee34d5a36cb43447703702`：四個指定檔案，full gate、scoped push、standing-approval六條件、clean full gate、merge及四domain activation aligned全部通過；rollback `9b2af3909547`。
- Task 4 `38059dbc3366e559c375229b3681fd5dcaeab0e9`：runner／tests／audit三個檔案，同一流程通過，四domain aligned；rollback `98702c5249aa`。兩個release都冇installer／Dashboard deploy／production scheduler或model改動。

## Deliberately Deferred

- Task 6先接target／future leakage、earliest odds、negative control、constant-field drift、mandatory ablation同ruler要求嘅pre-registered power readiness；Task 5嘅`safety_passed`只係要求literal True嘅接口，唔係安全或power證據本身。未有可驗證嘅Task 6結果之前不可由production scheduler傳True或發出真實candidate proposal。
- Task 7先接self-review scheduler、Central Dashboard同authorized Telegram digest；目前冇安裝新production scheduler。
- Task 8–9先用真實Tennis、AU／HKJC及NBA harness做pilot；fixture通過唔代表任何candidate model已改善或可promotion。
