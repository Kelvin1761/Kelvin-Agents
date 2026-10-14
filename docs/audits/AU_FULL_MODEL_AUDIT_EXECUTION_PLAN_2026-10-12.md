# AU Wong Choi 全模型審計：整合執行版

版本：2026-10-12，Australia/Sydney。完整保留 10-11 覆核整合版，補上執行清單與盲測保護。

本文件係完整計劃；各項是否已完成，以隔離 worktree 嘅 requirement ledger 及審計報告證據為準。不能將計劃驗收要求當成已取得嘅結果。

**準備度：可以開始 Phase 0 唯讀盤點及建立隔離環境；候選實驗必須先通過 G0–G3。** 本文件係執行計劃，不代表已跑評估、驗證第一輪結果或授權 production release。

取代原計劃嘅執行順序、判決版本及驗收要求。原計劃保留供追溯：

- [完整原文](AU_FULL_MODEL_AUDIT_PLAN_ORIGINAL_2026-10-11.md)
- [執行前覆核與程式證據](AU_FULL_MODEL_AUDIT_PLAN_REVIEW_2026-10-11.md)

## 執行入口：依次交付九個工作包

| 次序 | 工作包 | 可覆核交付／過閘條件 |
|---|---|---|
| 1 | G0／Phase 0：鎖版本、資料及 baseline | SHA／profile／來源 manifest、完整組件 inventory、baseline 及排序差異；保留舊版本 |
| 2 | G1／V：評估地基 | 完整賽日 OOS、ID/hash 配對、fallback、Holm／cohort、日期邊界與 null tests |
| 3 | G2／Phase 1：來源與副本資料修復 | 欄位覆蓋、identity／PIT lineage、補數 diff／衝突、eligible 清單；無證據欄位保持 FLAG |
| 4 | G3／A：登記表及 consumer 接駁 | 全語料分數／完整排名等價、plugin／缺資料邊界測試；AU 與 HKJC 分開 |
| 5 | Phase 2／第一輪 15 項：正確性覆核 | 每項獨立錯誤證據、回歸測試、修正／未解決狀態；B7 獨立且預設停用 |
| 6 | Phase 3／4：中性化、refit、新資訊／交互 | 先引用舊實驗並登記 family／功效；再用合資格 OOS 證據判決，合併改動拆 ablation |
| 7 | F → R → C：馬匹數、形勢重建、馬場 | field-size／venue guardrail、逐日衍生統計、稀疏來源 disposition；不以診斷取代增量驗證 |
| 8 | 4b／H：速度、營運、輸出及 reflector | 完整輸出等價、真正 production branch E2E、不可變快照／refresh、顯示與版本對齊 |
| 9 | Forward／最終驗收 | 預定揭盲規則、全組件 × 九問矩陣、EXP／hash／patch／rollback、未解決原因與重測條件 |

第 5／8 包嘅獨立正確性與唯讀工作可在地基階段處理。候選實驗逐項核對 G0–G3，不因部分測試通過而全體放行。最後先跑交付檢查並整理總報告。

**盲測保護：** 本輪不讀取或揭示現有 speed／class 盲測嘅真實候選成效、累積狀態或揭盲結果；只覆核來源 code、預登記規則及合成測試。需要正式揭盲時，另依已凍結 family 規則處理。本輪新 leaf 賽果診斷窗口固定為 **2026-08-05–2026-09-26**；來源、數值等價及營運診斷可以核對其他日期，但不能藉此擴大候選 outcome 窗口。

## 1. 目標、範圍與完成定義

由全模型 → 現役六維 → 退役／報告維度 → 每個 leaf → 每個 overlay → 安全欄／顯示／dashboard，回答九問。

| 編號 | 必答問題 | 工作包 |
|---|---|---|
| Q1 | 中性化之後應否重配權重？ | Phase 3、F、R |
| Q2 | 有冇噪音或可移除組件？ | Phase 2、3 |
| Q3 | 有冇 bug 或靜靜失敗？ | Phase 1、2、4b、H |
| Q4 | 有冇唔合理設計、預設值、方向或顯示？ | Phase 2、A、H |
| Q5 | 有咩改動經證據支持會改善分析？ | Phase 3、4、F、R、C |
| Q6 | 要唔要新特徵、新維度、新 overlay？ | Phase 4、R |
| Q7 | 要唔要重建 leaf／評分模型？ | Phase 2、3、R |
| Q8 | 數據有冇對齊、過期、洩漏或缺失？ | Phase 1、V、資料修復 |
| Q9 | 組件之間要唔要交互 overlay？ | Phase 4、F、R、C |

另外涵蓋：執行速度、容易升級／調整、馬匹數差異、逐馬場調整、賽日穩定性、退出馬／換騎／場地變化、train/serve skew、dashboard 及 reflector。

完成係清單每項有可追溯證據狀態、九問矩陣沒有無解釋空格，以及總報告。不以「完全優化」作無限重試條件，不保證一定有候選贏。

| 狀態 | 用途 |
|---|---|
| KEEP_CURRENT | 現狀保留；列明舊判決或目前證據限制 |
| HISTORICAL_WIN | 已通過本次合約歷史證據；仍須核對適用嘅 forward 要求 |
| REJECT | 觸發已登記拒絕規則；寫原因 |
| UNRESOLVABLE | 功效／PIT／樣本不足；列需要乜資料先再測 |
| PENDING_FORWARD | 候選已凍結，前瞻證據未到預定揭盲點 |
| CORRECTNESS_§7 | 獨立證明正確性修正；不是已證實改善 |
| NO_SOURCE／N/A | 無來源或該問題不適用；必須附理由 |
| CITED_PRIOR | 引用舊 EXP 判決；不重開舊 terminal |

## 2. 不可混淆嘅版本、授權及邊界

- 覆核時本機 `origin/main` = `0328f13a9564c787837e3c4aa1cfff19235c9b0c`；並非宣稱遠端最新。開跑時確認及鎖定實際 SHA，記錄 remote ref 時間。
- 主 checkout 同第一輪 audit worktree 有其他未提交工作，不重設、不掃入、不直接當乾淨 baseline。
- 第一輪 worktree HEAD = `e508754ab9ca40db059eefcbced8fc1986c164f6`。保存它嘅 patch、報告、EXP 和原始評估 artifacts；不把它嘅「全綠／golden 零變化」當本輪驗證。
- AU／HKJC 評分引擎分開。共用合約／工具可用 `--platform`；不合併模型。
- 新執行範圍不使用賠率、市場價、市場維度、SP 對照、$21+ 群體或價位段 AUC。名次係標準答案；原始舊實驗保留但不成為新候選篩選依據。
- 本輪產出留喺隔離 worktree；不 commit／push／merge／activate，不對 production CSV apply。A／§7 若之後獲明確 release 指示，拆 exact-scope 交付，使用 `./保存.sh --path … --expected-result …`，按當時 policy 執行。不要假設一定等 `/approve`。
- B7、純重構、管線修正、顯示校準、評估器修正分開 patch/profile；同一檔案亦要拆開變更，`--path` 不能隔離混合 hunk。

## 3. 共通證據紀律

1. 開始每個假設先用 experiment-review 搜索 `docs/experiments/`、舊計劃及 harness；引用實際 EXP，不只引用無法定位嘅 memory wikilink。REJECT 方向只有可說明嘅新 PIT 來源／結構假設才重新登記。
2. 每個候選做 model-regression-gate + leakage-audit；多個 leaf／weight／交互一齊郁做 feature-ablation；數據異常走 data-quality-audit。合約係裁判真源；skill 內舊 v1 說法不覆蓋現行合約。
3. `export PYTHONDONTWRITEBYTECODE=1`；改評分後重新 dump，不重用舊 Python process／cache 當 candidate。按 repo 指引處理 bytecode。
4. 固定同一語料版本、日期窗、race/runner IDs、seed、排除規則、環境及 profile。不能以改窗／指標／top-K／holdout 去救候選。
5. 所有指標由 canonical `eval_metrics` 提供。Gold = 實際前三全部喺模型 Top 4；Good = 模型第一、第二揀都上名。不混用頭馬捕捉或 gold_strict。
6. 新候選按鎖定 SHA 嘅 Stage 4 v3。`fixed_rule` 只適用於未由評估資料學出嚟嘅規則；任何 fit 過嘅值、門檻、gain、tier、標準時間或 shrinkage 均用 `walk_forward_oos`。
7. AU fit 評估只用 **2026-08-05 起**可證明 PIT 嘅乾淨段。06-06 起資料可描述性盤點，不能混入 fit 判決。未清 provenance FLAG 就不通過 leakage audit。
8. v3 bootstrap 以賽日為單位、2000 次；六個連續時間塊、primary/ranking 閘依現行合約。Cohort、Holm 和 forward 條件由 wrapper 明確執行，不能只相信 mode 字串。
9. §6 係逐個 ranking metric 嘅功效前置，不係一刀切所有候選／primary。預先量 component budget 與合約定義嘅 CI 半寬；全數非資訊性才按 §6 記 UNRESOLVABLE。新資訊不能因 live 權重為零就當預算為零。
10. §7 要獨立錯誤證據、適用嘅無顯著退步檢查、leakage PASS 及「不是已證實改善」聲明。現行 §7 嘅 SP cohort 與禁賠率範圍衝突，須独立記錄適用處理，不得靜靜改合約或與候選一齊改尺。
11. 每個有意義實驗用執行當日 `EXP-YYYYMMDD-NN-<slug>.md`，更新 INDEX；如有既有 memory／handoff 索引，加入已核證發現與證據連結，不寫未證實改善。記完整重跑命令、SHA、dataset/profile hash、樣本與日期、CI／cohort、判決 JSON 路徑。大 dump 留持久 scratch 並校驗，不只留會消失嘅 `/tmp` 路徑。

## 4. 開跑閘與依賴次序

| 閘 | 必須完成 | 未完成可做乜 |
|---|---|---|
| G0：baseline | 鎖版本、隔離改動、凍結語料／開關、建立完整盤點 | 唯讀探索與文件整理 |
| G1：评估 | 逐日 OOS producer、ID/hash pairing、fallback、Holm、cohort、驗證案例 | 描述性診斷；不報新 WIN |
| G2：資料 | 補 CSV 副本驗收、PIT lineage、來源三問、乾淨樣本清單 | 無受影響來源嘅工作包 |
| G3：接駁 | Phase A 等價、真 production path／安全欄對齊、候選 family 預登記 | 重構與整合測試 |

依賴次序：**Phase 0 → V／資料盤點 → 副本資料修復 → A → Phase 3／4 預登記 → F → R → C → forward → 總報告**。2／4b／H 嘅唯讀或獨立 correctness 工作可在地基階段處理；不得越過依賴開始 fit 候選。

## 5. Phase 0 — 版本、隔離、baseline 與全組件盤點

### 0a. 隔離與保存

- 檢查 worktree inventory，重用適合嘅乾淨 worktree；否則由已鎖 main SHA 開新 worktree，branch 用 `codex/` 前綴。不沿用「branch 名不能有斜線」舊限制。
- 將第一輪 §7、B7、現有主 checkout 騎練閘／濕地重磅候選各自保存成可辨認 patch；不混入 baseline。
- Baseline B7 設 `WC_AU_JOCKEY_NO_EVIDENCE=60`，明記 class_score live 開關及權重，所有 speed／PF／shadow 開關逐一列入 manifest。
- data-root markers 只指向研究副本；不要把 production markers 原樣 copy 後做 backfill／calibrate。保留已存在賽前不可變快照。

### 0b. 資料與基準輸出

- 用 `corpus_paths` 包括 Archive；保存不可變 source manifest：檔案 SHA256、race ID、runner ID、日期／時區、來源及 captured/available-at、排除原因。
- 分開 `historical_diagnostic` 同 `pit_fit_eligible` 語料；不得將今日重新評分歷史輸出稱為當年 live 預測。
- `au_dump_engine_leaves.py --out …` → `au_matrix_refit.py verify --data …` → baseline JSON。研究 replica max|Δ| <0.01，但另外比較逐匹分數與完整排序，解釋近乎平手差異。
- 正式 serving baseline 必須用完整 Facts enrichment、root cache／外部資源、field normalization、overlays 同最終安全欄。只複製 meeting Markdown／Logic 並不足夠：PF cache 會按 Facts 上層目錄尋找；`WC_PF_BACKFILL=0` 不會關閉所有 enrichment cache reads。每個來源 path/hash/as-of 要登記，驗證 fresh process 與跨 root bulk cache 行為；逐日 producer 用同一 serving bundle，不能用 stored-context scorer dump 冒充 live baseline。
- Baseline 報 Gold／Good／ranking、月份、馬匹數、馬場類、going、PIT 覆蓋；印出賽日、場數、runner 數及組成。v2 terminal 僅保存舊判決背景，不作新實驗 reveal。

### 0c. 盤點真源

建立 `component_inventory`，逐项列：key、位置、實際數據依賴、公式／gain、是否貢獻排名、是否計證據、是否顯示、缺失值／provenance、相關 overlay／安全欄。

現役六維名稱為 stability、pace_perf、jockey_trainer、class_weight、track、preparation；係數由鎖定 code 讀出，不能當加總為 1 嘅份額。race_shape、form_line 及任何退役／報告組件照列。leaf 數目由實際依賴推導，不用原文「9+9／18」作硬編碼。

**G0 驗收：** baseline manifest、dump、replica 差異表、完整 inventory、第一輪改動分流清單。

## 6. Phase V — 驗證與補齊現有 v3

本機鎖定 ref 已有 `evaluate_full_record` 同 `au_eval --stage4-mode v2|fixed_rule|walk_forward_oos`；不再平行建 `--mode full|walk-forward` 另一套裁判。

- Producer 按完整賽日 fit：所有 training dates < prediction date；同日任何賽果不進 fit。需要同日資訊嘅研究另立 methodology，不能偷渡。
- 每筆預測輸出 race/runner ID、輸入 hash、profile hash、fit cutoff、來源可用時間、baseline/candidate ability 及完整排名。
- weights、內層權重、missing calibration、people tier、檔位矩陣、標準時間、going adjustment、shrinkage、threshold、特徵篩選全部在各自 training prefix 內建立。固定種子及搜尋 budget。
- 不直接沿用按場數嘅舊 walkforward。無候選時輸出已登記 baseline fallback；不跳過測試窗。warm-up 範圍與缺資料處理事先鎖定。
- 用 race ID 配對及核對 runner roster／input hash，禁止只靠同場數、同日期或相同 list position。
- Wrapper 明確執行 §6、cohort guardrail、候選 family Holm；定義 p 值計算及 family，未校正嘅判決不當可上線 WIN。
- 驗證：A/A 不報 WIN；預登記 null seeds 測試假陽性；跨日 cutoff／同日隔離測試；已知非洩漏舊案例作 regression test。sire 洩漏靠 provenance 閘拒絕，不期待 KPI 統計識別洩漏。
- 不為重現某個「已知真效應」而調裁判；舊案例重判不同可報原因，不能反過來 fit v3。

**G1 驗收：** 預測格式／manifest、逐日 OOS 檢查、日期邊界與 fallback 測試、Holm／cohort 結果、判決 JSON。

## 7. Phase 1 — 數據對齊、新鮮度與副本修復

| 來源／問題 | 必做檢查 |
|---|---|
| AU_Historical_Raw_Race_Results.csv | 逐月欄位非空、唯一鍵、identity join、Distance／Barrier／Weight／Jockey／Trainer／Margin／Time；查全部 readers |
| PF backfill cache | 07-13 固定檔名是否實際 freeze、逐場來源／日期、是否 race-level timing 被誤當本駒 |
| 騎練評級表 | 更新日期、people DB 覆蓋、名字 matching；自動 tier 屬新 fit 候選 |
| J/T 組合表 | 两份一致性、覆蓋；display-only 引用舊判決，不硬加入分 |
| Sportsbet／RA acceptances／speedmap | 快照時間、TTL、退出馬／換騎、正式發布時間；無歷史 captured-at 就 FLAG |
| People DB | 名字被空字串覆蓋、21 日 TTL、rate 漂移、是否有 as-of 版本 |
| data_contract | fingerprint、死欄位、欄位消失、overlay presence；新 baseline 不掩蓋異常 |
| retest／shadow | 實際 registration、owner、開始／到期／揭盲門檻；活動項目與已結束歷史分開 |
| 未用欄位 | WinningTime、in-running、SpeedPos、Days、馬齡／性別／見習減磅等來源與 PIT |

每個 leaf 按月及乾淨窗口量非空率、fallback/provenance 佔比、場內 SD；不只數等於 60。

第一輪 CSV writer／merge／health 修正 #4–6 先在研究副本重做及驗收。`--fill-missing --sb-csv` 先 dry-run、備份、衝突表、before/after count；8 月 67.5% 覆蓋只作待核證舊觀察。

後補賽果可作標籤及未來日期可用嘅往績，不證明 people stats／career summary／speedmap 當日已知。來源三問：仲有冇產生、覆蓋乾淨窗、可證明落注時可用？任何一問失敗不進候選。

`au_unused_field_power.py --scored` 讀到 0 場時，先核對根目錄、meeting index、Formguide 命名及 Archive 覆蓋；零樣本係 harness 問題，不能判欄位無用。它嘅全 root speed-standard 路徑須改成 cutoff-aware 才可研究 speed。

**G2 驗收：** 新鮮度／覆蓋表、PIT lineage、補數 diff／備份、eligible corpus manifest、每個來源 PASS／FLAG／NO_SOURCE。

## 8. Phase 2 — 逐維 bug、方向與合理性

先問：「若績效方向相反，我仍能獨立證明並修正它嗎？」只有可證明錯誤走 §7；合理性假設走候選。

| 組件 | 必查項目 |
|---|---|
| jockey_trainer | 頂級騎練 substring 閘／評級表來源、缺記錄語義、jhf 中段壓縮、已移除騎師連續性引用 |
| stability | form／consistency 情境 −4、方向、performance_quality fallback、混合證據與雙計 |
| class_weight | rating 內外缩放、class_score live 特例、班次乘數依赖；等價表述不當改善 |
| track | 62.9 baseline 來源、Synthetic／空白誤當 Good、wet penalty／prior |
| pace_perf | trial 56／58／60 來源、PF／PI／L600 lineage、trial 實際傳導 |
| preparation | 同 jhf 證據有冇雙計／漏計、頂級騎練 gate、顯示接駁 |
| overlays | wet_form、proven_class、情境扣分、class multiplier、厚度安全欄嘅完整作用鏈 |
| 報告／安全欄 | weight 方向、health 來源、confidence −4、swap、tie-break、grade 語義 |

B7：46.86 係 dev-fit 候選，不係 §7／fixed_rule。第一輪完整結果與 Stage 4 JSON 未補齊前記「待核證」，不能引用全場 AUC 單項當 RANKING_WIN。新研究另登記 OOS family；預設停用。

## 9. 第一輪 15 項修正：逐項重驗與分流

| # | 工作項 | 驗收重點 |
|---|---|---|
| 1 | refresh 原抽／密集檔位比較 | 退出馬不假陽性；已開跑場次不可改寫賽前版本 |
| 2 | going refresh 被 Facts 覆寫 | 官方有效時間與重評分輸入一致 |
| 3 | 對手索引重複 subprocess／大檔讀取 | 多次計時、Facts bytes 相同、缺來源可觀察 |
| 4 | CSV writer 丟欄／Margin 錯寫 | 真實來源 fixture、所有 readers 可讀 |
| 5 | fill-missing 合併只追加 | 副本 dry-run、唯一鍵、衝突及備份 |
| 6 | production corpus health 路徑／吞錯 | 真 branch E2E、錯誤不能靜靜回 [] |
| 7 | people name 被空值覆蓋 | refresh 不抹掉有效 identity；PIT 版本保留 |
| 8 | refit／eval split 不一致 | 日界線及逐日 OOS；不沿用已受污染 terminal |
| 9 | retest 未登記 | 活動項完整、到期／樣本觸發、歷史留底 |
| 10 | dry wet-form presence／stale contract | 保留死欄位攔截；重新 calibrate 不掩蓋缺失 |
| 11 | preparation 冇 reasoning／顯示 | engine、report、dashboard 顯示一致 |
| 12 | parser 標題错配 | leaf 唔跌入上一維；schema backward compatibility |
| 13 | consistency −4 錯標籤 | 文字描述與實際條件一致 |
| 14 | 對手索引失敗冇警告 | warning／health 路徑可觀察且可重現 |
| 15 | class_score 過時註解 | 生成說明與 live profile 一致 |

黃金樣本不涵蓋嘅分支另加測試；「golden 零變化」不能取代 full-corpus／live 影響評估。

## 10. Phase A — 易升級、易調整嘅維度登記表

目標：新維度有獨立 spec + leaf 實作，消費者自動接駁；不能藉重構改模型。

- 在 AU package 建 `dimensions.py`，與 HKJC 設計可相似但實作分開。
- Spec：key、中文名、formula/leaves、內外係數、display gain／尺、reasoning、dashboard schema route、missing value／provenance、profile/version。
- 分開 `contributes_to_score`、`counts_as_evidence`、`shown_in_report`。class_score 入排名但不改厚度計數係既有特殊規則，必須保留。
- 推導 MATRIX_WEIGHTS／FORMULAS、labels／reasoning、feature keys、data_contract、explain_model、eval/refit dims、snapshot specs；避免 import cycle。
- 權重、預設值、門檻可集中但先保持原值／順序／rounding／clip／overlay 相對尺度。不能順便重校安全欄。
- Shadow profile 默认不影響 live；新增 shadow entry 不改 live coefficient budget、不重歸一化。開關、開始／到期／樣本門檻、profile hash 全部記錄。
- Plugin test 加假維度後報告、dashboard、eval 均讀得到；production 未啟用時分數與排序完全不變。

**G3 部分驗收：** 全語料逐匹 ability 差 ≤1e-9、完整排名／tie-break／安全欄 swap 相同、golden 不改、全部 consumer 對齊及邊界測試通過。模型說明只改生成器，不手寫生成檔。

## 11. Phase 3 — 中性化、去噪、權重與重建判斷

- Inventory 每個入分 leaf、六維及 overlay 做 isolated neutralisation；不剷掉再歸一化。常數 60 消融與 provenance-aware「移除資訊」分開記，不能混當同一實驗。
- 產出邊際 Δ／CI／排名翻轉／§6 資訊性／cohort 表。未有證據不當「冇用」。旧已判候選直接引用，只有新假設進一次預登記研究。
- 外層／內層 refit 各有 family；固定搜尋算法、3000 向量／seed／objective／fold 策略，consensus median。全部在 OOS training prefix；不再開舊 v2 terminal。
- 重建 leaf 只針對可指出嘅結構缺陷；全模型重建先引用既有 GBM／refit 證據。新資訊可能有用，不能把旧資料上 GBM 失敗解讀成永久理論天花板。
- 保留原始 baseline；失敗 model patch 不自動保存／上線。

## 12. Phase 4 — 新資訊、維度、交互與候選登記

每個 family 登記：假設、舊 EXP、來源／PIT、全部 arm 或組合挑選算法、搜尋 budget／seed、baseline/profile、metrics/cohort、§6、Holm family、停止／forward 規則、rollback。

必須有四種對照：現行 baseline、refit-only、新特徵固定接入、新特徵 + refit。多個新資訊合併要 ablation；「挑最好兩個」係選模程序，要在 training prefix 內做，不能用全期／forward 選。

候選池只係診斷範圍，未完成 preregistration 不得直接測：

- PIT speed/global_add：引用 EXP-20260927-02，只核對 shadow 規則／來源 captured-at，保持真實盲測狀態封存；標準時間及 going correction 同樣 cutoff-aware。
- class_score／官方獎金／Group：核對 RA 標籤捕獲窗及現行 0.15 live 特例；舊重測日期只係提醒，不保證到日就有功效。
- race_shape／speedmap、sectional、distance：交 Phase R，以新增来源／結構假設解釋點解重試。
- wet_form 維度化：先驗證是否純代數等價；若改相對幅度／fit 則獨立候選。
- wet × track、class_move × form、馬數 × evidence：預登記少量交互，避免用全期相關矩陣選完再宣稱 OOS。
- WinningTime、in-running、SpeedPos、Days 等：先 count 再來源三問；career summary 後補不當 PIT。

AUC／與 ability 嘅相关只作診斷，不以高 AUC／低相關直接判 WIN，亦不以低正交性直接代替增量評估。維度數目不是目標。

## 13. Phase F — 馬匹數感知

- 逐 leaf 在 ≤8／9–10／11–12／13+ 分層量方向、AUC、覆蓋及增量；不因單一細 cohort 點估計轉負就立即重建。
- 原抽 barrier、有效相對位置、實際 runner 數分欄保存。若用 percentile，基於有效起步位 rank 計 `(rank-1)/(n-1)`，處理 n≤1；退出馬後不能直接以原 barrier/n 冒充 percentile 或物理起步位。
- 往績擊敗比例須有當場有效 field-size／名次及 DNF／dead heat 處理；步速壓力用賽前預測前置馬數／馬數。
- shrinkage 對 n≤n0、分母／範圍定義完整；若 c/n0 等由資料 fit，逐日 OOS。
- Gold 馬數期望值版本只作預登記輔助指標，不能取代 canonical primary。report 應說明 expectation 定義及有效場數。
- 退出馬 E2E 核對 roster、馬數、檔位語義、完整排名、dashboard、快照時間。

## 14. Phase R — 重建 draw／race_shape／sectional／distance

AU 0 權重不因 HKJC 高權重而自動不合理。舊方向重試前必須列新增 PIT 資訊／結構修正；不只憑語料變大。

| Family | 新假設與實作範圍 |
|---|---|
| R1 draw | 逐日 as-of 矩陣；有效檔位 percentile、距離／going／賽道分組；預登記跑法交互；避免高維 cell 樣本耗盡 |
| R2 race_shape | 賽前前置壓力 × 本駒跑法；官方 speedmap captured-at、起步位準確度；引用舊 REJECT 及重測條件 |
| R3 sectional | 缺失 provenance／indicator 與本駒 L600 分開；拒用 race-level timing 當本駒；距離條件與 fade 需 OOS 驗證 |
| R4 distance | 先清 WinRange／賽後 summary 洩漏；只用當時過去賽績；首次增／縮程獨立 arm |

每個 family 先做單項，再加入 F／層級 shrinkage；拆 ablation。全國 → 州／賽道類 → 馬場嘅層級、最少樣本、fallback、超參數選擇全部事先登記及逐日重建。

新維度 sanity test 驗證真引擎／eval/refit／renderer／dashboard 都接到訊號；不接受 bit-identical A/B 作候選無效證據，先排除被忽略或 cache。

## 15. Phase C — 馬場調整

- 重量場數及獨立賽日數；原文 129 馬場／19 個 ≥40 場只作舊觀察。低樣本不 fit 每馬場整套權重。
- 只研究預登記形勢項：draw、前置偏差、wet；分組先核對幾何資源準確性。
- 層級 shrinkage 用過去資料，group／venue fallback 明確；完整 walk-forward、cohort CI、family 校正。
- 稀疏 cohort 記 UNRESOLVABLE，不能以 CI 很寬稱為安全；樣本／guardrail 門檻事先登記。
- 同日偏差入分引用舊 REJECT；若沒有獨立新來源／假設不重做。
- 報告提供逐馬場 leaf AUC／覆蓋／賽日数，不把描述差距當可調權重證據。

## 16. Phase 4b／H — 速度、穩定、輸出與營運完整性

- **性能：** 凍結輸入 cProfile；extract、retry、冷／暖 cache、Drive I/O 另量 wall-clock，多次取中位數。檢查 7200s timeout／slot／cooldown 是否仍適用；性能改動要求完整輸出及排名等價。
- **Live/研究一致性：** 核對 scheduler 真正 active SHA/profile，不能只看分支名；比對不可變賽前 snapshot 與相同輸入重評分，逐差異解释 going／roster／換騎／cutoff／tie-break／swap。
- **靜靜失敗：** AST + targeted tests 查吞例外／ImportError、真 0 被 `or 60` 改寫、sys.path package 目錄、硬寫空字串；真 production branch 及缺來源 E2E。
- **輸出校準：** confidence、A+…grade、tie threshold 分開驗證、時間外校準；語义與排名一致。安全欄 missing-count／swap 屬排名改動，不當純顯示，top1 指標亦必須量。
- **Dashboard：** snapshot spec/schema、標題、dimension/leaf route、向後相容及賽日更新測試。
- **季節與群體漂移：** 月份、級別、going、field-size、venue 覆蓋；賽日 Gold／Good SD 連同平均、場數組成、CI 一齊報，不以降低平均換 SD。
- **H 特有項：** stewards／Sportsbet 事件標記先來源三問；換騎熟手／升降級引用已移除舊連續性；馬齡、性別、見習減磅接到 Logic 先驗輸入，入分另登記。
- **Reflector：** 確認評嘅係賽前不可變版本，逐維 contribution/counterfactual 說明失誤；歸因不當因果證明，不由單日自動調參。
- **反饋與 shadow：** Kelvin 賽日反饋累積，達預定樣本先實驗；每個 shadow 有 owner、開始日、場數／賽日／覆蓋／到期／揭盲點。停用已結束活動項，保存全部歷史 manifest。

## 17. Forward 驗證與最終交付

Forward 起點不能只硬寫「10-11」：先核證 AU 賽果／候選成效是否已被其他 review 看過。候選算法、搜尋範圍、fallback、profile hash 凍結後才收 prospective predictions。

- 每 family 定明最少場數、獨立賽日、覆蓋、最早／最遲 reveal 日；一次正式揭盲。資料不足記 PENDING_FORWARD，不反覆看候選收益後改參數。
- 已存在 speed／class shadow 必須保留原 profile／規則；改 profile 不沿用舊 forward 樣本當新候選盲測。常規營運結果可用，不等於候選收益可反覆揭盲。
- 歷史 WIN、前瞻確認、release 決定三者分開；未揭盲有明確重測條件，仍可完成本輪歷史審計報告。

總報告 `docs/audits/AU_FULL_MODEL_AUDIT_2026-10.md` 在隔離 worktree 完整更新，不覆寫／遺失第一輪版本：

1. 行 = inventory 全組件，列 = Q1–Q9；每格有狀態、指標／CI（適用時）、EXP／artifact 或 N/A 理由。
2. 來源新鮮度／PIT／死欄位、bug 已修／待修、所有候選与 family／Holm／cohort、baseline 與 OOS manifest。
3. 性能、live/研究差異、顯示／dashboard、賽日穩定性，以及優先次序、rollback／開關。
4. 每個 patch 的檔案與對應判決；第一輪 §7、A、B7、新候選彼此分開，讓後續 release 可 exact-scope。
5. 所有尚缺資料、forward 狀態、重測條件／日期；不把等待當成已證實改善。

改 code 後跑 `./檢查.sh --quick`，交付前 `./檢查.sh`。模型邏輯變更先確認意圖與證據，再按 repo 要求更新 golden／calibration／生成模型說明；保留可退回 baseline，不能用覆蓋 snapshot 清掉 regression。A／性能重構 golden 不重新 record。

### 開始執行時嘅第一份交付

先完成 **G0 package**：已鎖 SHA、隔離 worktree 路徑、環境/profile manifest、凍結資料清單、實際組件 inventory、baseline JSON／排序差異，以及 G1–G3 待辦表。這份地基完成後才可報「準備好開始候選實驗」。

## 18. 主要實作入口與核對工具

所有路徑相對於已鎖定嘅隔離 worktree；執行前核對該 SHA 嘅 CLI/help，不假設主 checkout 同版本。

| 責任 | 主要檔案 |
|---|---|
| AU 引擎／登記表 | `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/{scoring.py,matrix_mapper.py,engine_core.py,renderer.py,dimensions.py}`；dimensions.py 為本輪擬建 |
| dump／評估／refit | 同 scripts 目錄嘅 `au_dump_engine_leaves.py`、`au_eval.py`、`au_matrix_refit.py`、`au_feature_ab.py`、`au_unused_field_power.py` |
| 合約／指標／判決 | `docs/model-evaluation-contract.md`、`.agents/skills/shared_racing/{eval_metrics.py,model_evaluation_decision.py}` |
| 語料／健康／golden | `.agents/skills/shared_racing/scripts/{corpus_paths.py,data_contract.py,golden_scoring.py}` |
| 數據修復 | `.agents/skills/au_racing/{sb_results_csv.py,ra_fields.py,sb_people_stats.py,claw_sportsbet_form.py}`、auto scripts 嘅 `au_results_ingest.py`；各 rating resources |
| 排程／refresh | `.agents/skills/au_racing/au_daily_auto/{au_daily_schedule.py,au_healthcheck.py}`、auto scripts 嘅 `au_auto_orchestrator.py` |
| dashboard／說明 | `Horse_Racing_Dashboard/backend/services/parser_au.py`、`.agents/skills/shared_racing/scripts/explain_model.py`、`Wong Choi 模型說明/更新模型說明.sh` |
| reflector | `.agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py` 及其實際依賴 |

候選邏輯修改後：新 dump → replica verify → 真引擎完整排序比較 → OOS producer/wrapper → 合約判決／Holm／cohort → EXP。`verify <0.01` 不取代排序一致性或 §7／候選證據。

工作副本核對 `golden_scoring.py --platform au`（純重構不加 `--record`）、`data_contract.py --platform au --check`，以及 meeting-level dead-field gate；需校準時先保留旧 fingerprint／coverage 比較，不能只令警告消失。
