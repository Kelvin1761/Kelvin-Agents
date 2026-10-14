AU Wong Choi 全模型審計計劃（全模型 → 6 維 → 每個 leaf）
Context
Kelvin 要一次過審計 AU Wong Choi：由全模型、每個維度、到每個 sub-component，答九條問題 （中性化重配權重、去噪、bug、唔合理、改善、新特徵／overlay、要唔要重建評分、數據對齊／新鮮度、 組件之間要唔要加 overlay），而且要做到「完全優化」先停。

現況（探索結果）：

Live 係 6 維唔係 7 維（「7D」只係舊名，殘留喺 pure_7d_score、clean_7d_static）： jockey_trainer 0.66266、class_weight 0.38262、stability 0.37100、preparation 0.25244、 track 0.14114、pace_perf 0.12094（scoring.py:160-167，EXP-07 後係合成係數，唔加埋等於 1）。 race_shape、form_line 只出報告。
9 個 leaf 入排名，9 個只出報告（REPORT_ONLY_FEATURE_KEYS，scoring.py:19-22）。
Overlay：wet_form（scoring.py:307）、proven_class 0.5·z（engine_core.py:792）、三條情境扣分 （engine_core.py:566-627）、班次乘數（:1035）、證據厚度安全欄（renderer.py:70-170）。
過往證據好重要： 重配份額已經五次 REJECT、0928-02 重跑 refit 都係保留現行矩陣、GBM 輸畀現行線性組合、 市場缺口同全部 leaf 正交（[[au-feature-set-is-saturated]]、[[au-market-gap-is-orthogonal-information]]）。 所以呢次審計唔可以重做已判死嘅嘢；每項先 grep docs/experiments/，有判決就引用，冇新資訊就唔重測。
已同 Kelvin 確認：

判決尺 = Stage 4 v2（Gold／good_positional primary）。賠率／市場價喺成個計劃唔再出現（2026-10-10 Kelvin 要求）： 唔做市場維度、唔做價位段內 AUC、唔用賠率做任何 overlay 或者判決。賽果（名次）係唯一標準答案。
由 origin/main 開乾淨 worktree；主 checkout 嗰批未 commit 嘅 engine_core.py 改動（頂級騎練閘只信評級表、 剷濕地重磅 −4）唔掂，當做一個獨立候選喺 worktree 入面量。
終點 = 清單上每一格都有合約判決（KEEP／REJECT／UNRESOLVABLE／§7 正確性修正／引用舊判決），加一份總報告。
交付 = 只寫報告唔 commit。改動、實驗記錄、報告全部留喺 worktree，Kelvin 睇完先決定。
進度（2026-10-10 第一輪已做，喺 worktree claude-au-full-audit-20261010，未 commit）
完成：
Phase 0 baseline（3,298 場）。
Phase 1 數據審計。
Phase 2 bug 審計。
Phase 3：中性化消融、refit、內層權重。
Phase 4a：5 個現成 leaf 硬加做新維度。
Phase 4b 盲點。
總報告 docs/audits/AU_FULL_MODEL_AUDIT_2026-10.md，實驗記錄 EXP-20261010-01。
結果：
排名 KEEP 現狀。
15 個 §7 管線修正，golden 零變化，./檢查.sh 全綠。
B7 中性點重建：jockey「冇記錄」60 → 46.86 判 RANKING_WIN。屬邊緣過閘，已實作喺 worktree，回退用 WC_AU_JOCKEY_NO_EVIDENCE=60。
未完成，要補：
未用欄位三問閘：au_unused_field_power.py 讀到 0 場，要先查 --scored 路徑。
$21+ 冷門分析：按 Kelvin 指示剷走，因為佢靠賠率定義群體。
報告矩陣表要逐格填判決。
第一輪嘅限制：Phase 4a 只係將現成 leaf 硬加做維度。race_shape、sectional、distance 要喺下面嘅 Phase R 按大咗嘅語料重新砌，唔係就咁判死。
執行紀律（每個 phase 都適用）
用 project skills：開始前 experiment-review（grep 舊記錄），每個候選 model-regression-gate + leakage-audit，多於一樣郁就 feature-ablation，數據問題 data-quality-audit。
export PYTHONDONTWRITEBYTECODE=1；每次改評分 code 之後重新 dump，再跑 au_matrix_refit.py verify（max|Δ|<0.01）。
§6 功效前置條件要喺量之前計：每個候選先計 component budget vs MDE，細過 MDE 就預先標 UNRESOLVABLE，唔准事後用嚟救。
預先登記候選清單（Phase 3 開頭寫死），terminal 每個候選只開一次；唔准換指標／換窗／換 top-K。
指標一律由 eval_metrics 攞（gold = capture-at-4）。
每個有意義嘅實驗寫 docs/experiments/EXP-20261009-xx，失敗照記。
Phase 0 — 環境同 baseline
git worktree add 由 origin/main 開新分支（名唔准有斜線）；copy .wongchoi_*_data_root marker 過去 （[[main-checkout-was-18-commits-stale]]）。
記低 commit hash、語料路徑、日期；au_dump_engine_leaves.py --out <scratch>/base.json → au_matrix_refit.py verify → au_eval.py --data base.json --output-json 做 baseline （語料用 corpus_paths.py，包埋 Archive/；印 dev／terminal 場數、切點、馬匹數組成）。
Baseline 同時出價位段內 AUC（輔助）同市場 SP 對照，令總報告有參照。
Phase 1 — 數據對齊／新鮮度（Q8、部分 Q3）
逐個來源量「有欄位 vs 有數據」同 as-of 有效性。已知要核實嘅：

項目	疑點	驗證方法
AU_Historical_Raw_Race_Results.csv	09 月起 14,722 行 Jockey／Trainer／Barrier／Time／Distance 全空；sb_results_csv.py 只寫 8 欄	搵出所有 reader（draw matrix、statistics aggregator、J/T 組合表、反思器），逐個判斷有冇食咗空欄；修 writer 屬 §7，歷史用 --fill-missing
PF backfill cache	檔名寫死 ..._2026-07-13.json，凍結	查 07-13 之後場次 pace_figure 係食即日數據定舊 cache
騎練評級表	人手，最後更新 05-16，只覆蓋 ~20%	對 2,255 人 people DB 量覆蓋率；評估由 DB 自動生成
J/T 組合表	兩份唔同步，只得兩個馬場	已知 display-only（[[au-jt-combo-table-is-display-only]]），只記錄唔測
Sportsbet／RA acceptances cache 永久	退出馬、晨價、遲出 speedmap 可能舊	對 live 場次比較快照時間 vs 開跑時間
People DB TTL 21 日	騎師狀態落後	量 TTL 內率漂移；只係顯示風險定排名風險
data_contract baseline	1,149 場、09-03、fingerprint 已過期	喺 worktree 重新 calibrate（唔 commit），比較死欄位清單
au_retest_watch.REGISTERED 空	兩個 2026-11 重測（班次標籤 dev、people as-of）冇登記	寫入候選改動
另外每個 leaf 喺乾淨窗口（2026-06-06 起）量：非空率、中性 60 佔比、場內 SD、按月趨勢（偵測「靜靜變空／常數／過期」）。

Phase 2 — Bug 同唔合理（Q3、Q4），逐維度
每項先問「如果數字相反你仍會改嗎？」—— 係就行 §7，唔係就入 Phase 3 候選。

jockey_trainer：頂級騎練 substring 閘（主 checkout 嘅未 commit 修正喺 worktree 重做並量）；評級表覆蓋率； jockey_horse_fit 中段平、SD 3.26 壓縮。
stability：form −4（form≥72 且 class<60）、consistency −4 呢類手調情境扣分逐項做方向審計 （騎師連續性三項曾經全反，[[au-adjustment-direction-audit]]）；performance_quality fallback 用 consistency 嘅合理性。
class_weight：單 leaf 再乘 0.70 內權重再乘係數，屬多餘縮放（純表述問題，排名等價，記錄唔改）； 班次乘數 entry["class"] 死但要留（[[au-dead-class-multiplier-earns-its-keep]]，引用）。
track：預設值 62.9 而唔係 60（核實係咪經驗校準）；Synthetic／空白場地靜靜當 Good（1.5%）。
pace_perf：trial 預設 56/58/60；trial 傳導率極低（引用 [[au-trial-leaf-transmission-is-negligible]]）。
preparation：由 jhf 扣返同一份證據，核實冇雙計／漏計。
Overlays：wet_form 常數同 prior 0.3758 已校過（引用）；proven_class 0.5 係咪曾經量過；證據厚度安全欄。
報告層：weight_score 顯示方向倒轉、health_score 死、confidence_score −4。
Phase 3 — 中性化、重配權重、去噪、重建（Q1、Q2、Q7）
中性化消融（swap-leaf 到 60，唔用剷走再歸一化）：9 個入排名 leaf、6 個維度、每個 overlay 逐個關。 產出「每個組件嘅邊際貢獻 + CI + 是否細過 MDE」表 —— 呢個就係 Q1／Q2 嘅答案： 中性化後 dev 同 terminal 都唔跌或者升嘅 → 去噪候選。
權重：用 au_matrix_refit.py refit（3,000 隨機向量、5 fold gate、取 median 唔取 argmax）+ walkforward 喺最新語料重跑一次，外層 6 個係數同各維度內權重（stability 0.6/0.4、jockey_trainer 三個、pace_perf）。 只做呢一次預先登記嘅 refit，唔做座標搜索（之前五次失敗嘅形狀）。過 Stage 4 先算「現行權重唔係最好」。
重建判斷：只有 leaf 有結構缺陷（例如「冇數據」同「表現差」混埋喺同一個尺、中性點錯位）先建議重建該 leaf； 全模型重建要有證據推翻 GBM 天花板結果，否則答「唔需要」並附證據。
Phase 4 — 新特徵、overlay、組件關係（Q5、Q6、Q9）
每個候選先過三問閘（來源仲有冇產生？覆蓋窗撞唔撞乾淨窗口？as-of 有冇效？），唔過就唔測。

Point-in-time speed global_add：0927-02 PROMISING 已入 shadow monitor；睇累積咗幾多新場次，夠就做正式判決。
組件關係／交互 overlay：場內計維度之間嘅殘差相關矩陣，揀預先登記嘅少量交互（例如 wet × track、 class_move × form、馬匹數 × 證據厚度）；已判死嘅（pace_map 按馬匹數縮放、休後長休打折 H1、初出用試閘 H2）只引用。
$21+ 冷門內部分辨：缺口集中喺呢度；任何候選限定喺呢個群體量。
未用欄位：WinningTime、in-running 位置、SpeedPos、Days 等，先 count 非空，再三問閘。
候選總數預先寫死（控制多重比較），寫入 Phase 3 開頭個登記表。
Phase 4a — 探索加維度（6D → 8D／9D）
原則：維度數目唔係目標。 一個新維度要過 Stage 4 先入排名，攞唔到權重就唔加（簡單而穩健 > 複雜而邊際）。 過往教訓：硬加零權重 leaf／維度三次 REJECT（race_shape、sectional、distance），form_line 第一次真正測到就係死嘅 （[[leaf-auc-gains-do-not-convert-to-ranking]]、[[au-retired-dimensions-stay-retired]]）。所以新維度要帶新資訊，唔可以係現有 leaf 重新包裝。

候選維度（逐個先過三問閘 + 量對現行 ability 嘅正交性 ρ + 單獨場內 AUC + 覆蓋率）：

候選	來源	已知狀態
速度（point-in-time speed）	WinningTime + 距離／場地標準時間	0927-02 global_add PROMISING（Gold +0.43pp CI [+0.05,+0.86]），shadow 運行中 → 最有機會
班次（class_score + 今場獎金／Group 標籤）	RA Acceptances（07a49d42 新補）	dev 冇標籤，約 2026-11 先測得到 → 預計 UNRESOLVABLE，登記重測
路程適性（distance_score）	往績分佈	AUC 0.5668 最高嘅未用 leaf，但要完整洩漏審計（似 WinRange）
步速／走位（race_shape 復活：跑法三態 + 官方 speedmap）	Sportsbet speedmap	剔走預設守中後 AUC 0.5489、ρ +0.079；未跑閘 → 值得正式測一次
場地／濕地（由 overlay 升做維度）	wet_form	結構改動，排名等價與否先驗證
市場（早更位賠）	Sportsbet 最早快照（唔准用 SP）	SP AUC 0.74 vs 我哋 0.65；但合約話賠率唔准做隱藏 proxy，一定要 Kelvin 明文決定佢係模型一部分先測，而且會令「模型 vs 市場」比較失去意義
方法（唯一正確做法，[[au-eval-dropped-candidate-dimensions]] 個坑要先避）：

確認 au_eval.py／au_matrix_refit.py 真係食到新維度（加一個已知效果嘅 sanity 維度，A/B 唔可以 bit-identical）。
新維度放入矩陣，用 consensus refit（median 唔用 argmax）同其他 6 個係數一齊重新 fit，唔係硬加。
逐個加（7D 各自一個），再試最好兩個一齊（8D）；多過一個一齊入就要 ablation 拆邊際貢獻。
Stage 4 v2 判決；過咗先考慮 9D。
如果過閘，列出要同步改嘅地方：renderer、dashboard parser、data_contract（重新 calibrate）、golden、模型說明生成器、wet overlay 縮放。
Phase 4b — 盲點補充（Kelvin 要求：行得快、冇 bug、分析表現優化）
A. 運行效率

用 cProfile 跑一個完整場次（extract → facts → logic → score → render → gate），逐步計時； 搵出熱點（重複 parse、逐匹馬重讀檔、冇 cache 嘅 lookup、Drive I/O）。
對照 control plane 全域 7200s timeout（曾經穩定切走字母排後嘅場次，[[control-plane-timeout-and-slot-collisions]]） 同 sportsbetform 冷卻窗：量一晚實際用幾耐、離 timeout 幾遠。
優化只限「輸出 bit-identical」嘅改動，用 golden_scoring 逐匹馬證明零變化。
B. Live 同回測一致性（train/serve skew）

排程跑 /Users/imac/wongchoi-scheduler 自己個 worktree：核實 live code = main（[[au-production-diverged-from-dev-line]]）。
揀近期場次，比較「賽前儲存快照」vs「依家用同一份輸入重評分」，逐匹馬差異要解釋得到 （場地 --going、退出馬重建出賽名單、早更 vs 前晚價、快照用本地時間）。回測量到嘅模型要等於 live 用緊嘅模型。
C. 靜靜失敗掃描

AST 掃引擎同抽取層：except: pass／被吞 ImportError／fs.get(k,60) or 60（將真 0 改成 60）／ 錯誤 sys.path（[[engine-package-syspath-needs-ast-scan]]）／硬寫空字串。
測試質素：fixture 用假名所以永遠綠嘅情況（[[health-gate-au-branch-was-never-run]]）；補一個真 pipeline 端到端測試。
D. 輸出層有冇幫到分析

信心級別（top-3 分差 <2／<5）：月度檢討話各級別命中率冇分別 → 量佢有冇鑑別力，冇就係唔合理項。
評級（A+…）、平手判定（<0.5）、安全欄 swap 嘅實際命中率；報告文字同排名數字一致（[[display-only-changes-leak-into-ranking]]）。
Dashboard parser 對得上引擎表頭（[[dashboard-parser-breaks-on-engine-table-renames]]）。
E. 季節／群體漂移

春季分級賽相對市場再輸 11.5pp：按月同按賽事級別分層報告，terminal 窗口組成要印出嚟，避免用春季窗口判一個夏季調出嚟嘅模型。
第二輪（Kelvin 2026-10-10 追加）
建議次序：A → V →（補語料 CSV）→ F → R → C → H。A 同 V 係之後所有實驗嘅地基。

Kelvin 決定（2026-10-10）：

地基分開送審：Phase A（登記表重構）同第一輪 §7 修正，各自做獨立 release，經 ./保存.sh --path …，等 /approve。F／R／C／H 嘅實驗結果照舊只寫報告，過閘嘅改動留喺 worktree。
v3 等 HKJC 做好先用：AU 唔實作 model_evaluation_decision 嘅 v3。AU 只預備 au_eval --mode full|walk-forward 嘅接駁同 walk-forward dump。
v3 上線之前，F／R／C 做到「診斷 + 預先登記 + dev／walk-forward 數字」為止，最終判決等 v3。
唔會再用已經用到爛嘅 v2 terminal 判 fit 類候選。
H 入面嘅 §7 項目同顯示層唔受影響，可以照做。
Phase A — 長期要求：模型要易升級、易調整
問題（第一輪實測）：加或者改一個維度，要改十幾個寫死嘅地方，漏一個就靜靜出錯。

今日實例一：試閘備戰（0.2524）喺 _matrix_reasoning 同 MATRIX_LABELS 都漏咗，所以「逐維一覽」同 dashboard 由來冇顯示。
今日實例二：「冇證據」預設值分散喺各 leaf（jockey 46.86、track 62.9、trial 56），而安全欄寫死咗「== 60」。
今日實例三：au_matrix_refit.DIMS 寫死包住已退役嘅 race_shape。
目標：加一個維度 = 加一個登記表 entry 加一個 leaf function，其他全部自動跟。

單一維度登記表 au_racing_engine/dimensions.py，每個維度一個 spec：
key、中文名、角色。
leaves 同內權重、外層係數。
每個 leaf 嘅「冇證據」值同 provenance 判定。
顯示尺、一句話說明、dashboard 路由。
由佢推導出嚟嘅消費者：
MATRIX_WEIGHTS、MATRIX_FORMULAS
ABILITY_FEATURE_KEYS、REPORT_ONLY_FEATURE_KEYS
MATRIX_LABELS、_matrix_reasoning
THIN_EVIDENCE_SCORED_LEAVES 同預設值
data_contract 欄位
explain_model
au_eval、au_matrix_refit 嘅 DIMS
dashboard（snapshot 帶埋 dimension spec）
參數同 code 分開：權重、門檻、預設值集中一處，有版本號；每個實驗性上線都有一個環境變數開關（好似 WC_AU_CLASS_SCORE_LIVE）。
Shadow 機制：新候選一律用 shadow profile 接入。每個 profile 要寫明開始日、所需場數、到期日。上線同回退都只係改登記表一個開關。
Contract tests：
登記表同所有消費者對齊。
dashboard 顯示嘅維度 = 登記表。
plug-in test：加一個假維度，證明只改登記表就會出現喺報告、dashboard、au_eval。
驗收：重構後全語料逐匹 ability 差 ≤1e-9、排名 bit-identical、golden 不變，按 §7 結構性改動處理。
同 HKJC 計劃嘅 hkjc_racing_engine/dimensions.py 用同一個設計，但兩個引擎唔合併（AGENTS.md 第 4 條）。
Phase V — 判決尺升級：Stage 4 v3（同 HKJC 計劃共用）
AU 嘅 terminal 已經用到爛：月度檢討睇過，今日再開咗 7 次，而且 terminal 正正係春季。所以下面嘅 fit 類工作唔應該再用 v2 一刀切。

改動類型	v3 判法
冇由數據學嘢（§7、預先寫死嘅值）	用全部紀錄做配對 bootstrap；6 個時間塊之中 ≥4 塊 primary 唔退步
由數據 fit 數值（權重、新 leaf、檔位矩陣、馬場調整）	walk-forward：每個賽日只用之前嘅賽日 fit，用嚟預測嗰日
最終確認	forward holdout（2026-10-11 起，冇人睇過），每個候選家族只開一次；用 Holm 調整
改把尺 = 獨立改動：改 docs/model-evaluation-contract.md 加 v3 一節；model_evaluation_decision.py 由 HKJC 計劃負責，AU 只加 au_eval --mode full|walk-forward。
驗證把尺：
A/A 測試 100% 唔過閘。
已知洩漏嘅 sire 訊號要判 REJECT。
已知真效應嘅騎師連續性修正要判得返。
AU 特有限制：fit 類只可以用乾淨段。一般由 2026-06-06 起；檔位類由 2026-08-05 起（檔位矩陣洩漏界線）。
前置：補返語料 CSV（R1、F、C 都要用）
檔位、距離、騎練研究都靠 AU_Historical_Raw_Race_Results.csv，而 2026-09 起嗰幾條欄係死嘅。

先發佈第一輪修正 #4、#5、#6。
然後對 production 跑 --fill-missing --sb-csv。
8 月有部分場次唔喺 cache 對應表，要另外補（Jockey／Trainer 現時只有 67.5%）。
冇呢步，as-of 檔位矩陣喺 9 月之後就冇數據。
Phase F — 馬匹數變化（AU 特有：4 至 18 匹）
實測（乾淨窗口 2,720 場）：

馬匹數由 4 到 18 匹，7–12 匹佔 77%，13 匹以上 280 場，6 匹以下 214 場。
HKJC 通常大約 12 匹。
馬匹數會改變「形勢」：
Gold 基準由 ≤8 匹嘅 34% 跌到 13+ 匹嘅 7%。
檔位／步速效應喺 5–8 匹只有 1.6pp，12–14 匹有 10.7pp（[[au-pace-map-is-a-four-step-ladder]]）。
做法：

逐 leaf 按馬匹數分層（≤8／9-10／11-12／13+）量場內 AUC 同方向。有 leaf 喺某一層失效或者調轉，就要做馬匹數感知重建。
改用相對量（全部 point-in-time）：
檔位 → 檔位百分位（檔位 ÷ 馬匹數）。
往績名次 → 擊敗比例（核實 [[au-field-size-extraction-gap]] 修咗未）。
步速壓力 → 前置馬數目 ÷ 馬匹數。
形勢類（檔位、步速、走位）嘅幅度隨馬匹數變：用 shrinkage 曲線（例如 k(n) = k_max · (n − n0)/(n − n0 + c)），細場自動縮向零，大場先全幅。
舊記錄：「按馬匹數縮放」喺有洩漏嘅舊檔位數據上 REJECT（[[au-draw-signal-loses-to-neutral]]），要喺乾淨 as-of 數據上重新登記。
評估：每個候選都要報馬匹數 cohort guardrail，Gold 要同時報「對比馬匹數期望值」嘅版本。
live 正確性：退出馬之後馬匹數要即時更新。第一輪修正 #1 已經處理咗檔位假陽性；要加端到端測試確認重建之後嘅馬匹數同檔位次序啱。
Phase R — 重新砌 檔位／race_shape、sectional、distance
點解要重來：

HKJC race_shape 係最大權重（27.4%），AU 係 0，呢個唔合理。
第一輪 Phase 4a 只係將舊版 leaf 硬加做維度，冇用到更大嘅語料，亦冇修佢哋本身嘅結構問題。
依家乾淨語料有 2,720 場（race_shape 退役嗰陣只有 403 場）。
共同原則：

全部 point-in-time。矩陣同統計逐日只用之前嘅賽果重建；leakage-audit 逐欄過。
「冇數據」同「表現差」分開：用缺失指示，唔可以將冇數據放喺 60 地板。
一定要馬匹數感知（Phase F），用 shrinkage 層級（全國 → 州／賽道類型 → 馬場）。
先量單獨場內 AUC、對現行 ability 嘅正交性 ρ、§6 功效。然後經登記表做新維度，同其他係數一齊 consensus refit。用 v3 walk-forward 判。
#	組件	過往點解失敗	今次點砌
R1	檔位分（新維度）	舊檔位矩陣用含測試期嘅賽果建，令回測洩漏；乾淨 walk-forward 輸畀「冇檔位訊號」；全範圍效應只有 4–6pp	as-of 檔位矩陣：馬場 × 距離段 × 檔位百分位 × 欄位／場地狀況，逐日重建；同預測起步位（跑法三態）做交互；細場縮向零。研究重點係大場、細圈馬場、短途
R2	race_shape／步速形勢	2026-08-22 因洩漏界線退役；官方 speedmap 同我哋正交（ρ +0.005）	步速壓力（預測前置馬數目 ÷ 馬匹數）× 本駒跑法；起步位準確度要再驗；已登記 2026-11-22 重驗
R3	sectional	48.8% 冇 PI，坐喺 60 地板，「冇數據」同「跑得慢」混埋；舊單邊尺嘅測試用咗壞數據	加缺失指示；用本駒 L600（唔用場級）；按距離分（>1600m 段速勝出，[[au-pace-perf-distance-crossover]]）；fade 觀測而家有 1,013 個
R4	distance	AUC 0.5668 但語義似 WinRange，未做完洩漏審計	先做 leakage audit；只由賽前往績行砌 as-of 路程記錄；加「首次增程／縮程」（借自 HKJC 4e.6）
每個都可能出現嘅結果：AUC 高但正交性低（同 form 重複）就照報 REJECT 加原因，唔會為咗湊夠 8D／9D 而上線。

Phase C — 逐馬場微調（需唔需要？）
實測：

乾淨窗口有 129 個馬場；≥40 場只有 19 個，≥80 場只有 1 個（Eagle Farm 98）。
月度檢討顯示馬場之間嘅差距全部 CI 跨零。
結論：逐馬場配一套權重做唔到，樣本唔夠，會擬合噪音。

可行做法：

只對少數形勢類項目做馬場調整：檔位、前置偏差、濕地。
用層級 shrinkage：全國 → 州／都會-省賽-鄉郊 → 賽道幾何類（細圈／大圈／合成跑道，用現成 resources/au_track_geometry.json 分組）→ 馬場。
用 walk-forward 判。上線條件：合併後有改善，而且冇一個馬場組別 CI 全負。
唔准重做：同日賽道偏差追蹤入分（HKJC EXP-0928-04 已 REJECT）。
報告層：逐馬場 leaf AUC 表照出，方便 Kelvin 睇（唔入分）。
Phase H — 由 HKJC 審計計劃借嘅項目
賽日穩定性：每個候選都報場日層面 Gold／Good SD。Kelvin 要嘅係賽日表現穩定（[[hkjc-race-day-consistency]]）。
Shadow 登記表：速度盲測、class_score 回退影子等，每個寫明開始日、場數、到期日。已判或過期嘅剷走。
賽日變動端到端測試：模擬退出馬、換騎、場地改變，確認排名、馬匹數、檔位次序同 dashboard 都會更新（第一輪修正 #1、#2 嘅回歸保護）。
仗次可靠度／可原諒失利：AU 冇 stewards 評述來源（[[au-health-score-has-no-source]]），要先查 Sportsbet 有冇事件標記；冇就記「來源不存在」，唔砌。
換騎分類：換返熟手、升級、降級分開量。AU 已經剷咗騎師連續性三項，要引用 [[au-jockey-continuity-terms-removed]]，唔重做舊版。
見習減磅、馬齡、性別：先查有冇入 Logic（HKJC 發現馬齡冇入），接駁屬抽取層 §7，之後再量。
輸出層校準：第一輪 D1–D3（信心級別、評級、安全欄預設值）按實測上名率重新校準顯示門檻；排名要 bit-identical。
反饋累積清單：Kelvin 嘅賽日反饋入清單，夠樣本先開實驗，唔准為一日調參。
AU reflector 升級（HKJC 計劃寫明要另外查）：建議要由當日失誤推導、指出邊個維度壓低咗嗰匹馬，同埋確認評緊賽前版本。
唔重做：休後長休打折 H1、初出用試閘 H2、重配維度份額（五次）、同日賽道偏差。
Phase 5 — 總報告同交付（唔 commit）
docs/audits/AU_FULL_MODEL_AUDIT_2026-10.md：一張矩陣表，行 = 全模型 + 6 維 + 2 退役維 + 18 leaf + overlays， 列 = 九條問題；每格 = 判決 + 數字 + EXP id／引用。另附：數據新鮮度表、bug 清單（已修／待修）、 建議改動按優先次序、價位段內 AUC 輔助表。
實驗記錄寫 docs/experiments/；更新 memory（新發現、index 一行）。
全部改動留喺 worktree，報告最後列出每個改動嘅檔案同對應判決，等 Kelvin 揀邊啲用 ./保存.sh --path 送審。
主要檔案
引擎：.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/{scoring.py,matrix_mapper.py,engine_core.py,renderer.py}
評估：au_eval.py、au_dump_engine_leaves.py、au_matrix_refit.py、au_feature_ab.py（同目錄 scripts/）； .agents/skills/shared_racing/{eval_metrics.py,model_evaluation_decision.py,scripts/corpus_paths.py,scripts/data_contract.py,scripts/golden_scoring.py}
數據：sb_results_csv.py、au_results_ingest.py、ra_fields.py、sb_people_stats.py、resources/AU_*_Ratings.csv
規則：docs/model-evaluation-contract.md（唔改）
驗證
每次改評分：重新 dump → verify max|Δ|<0.01 → au_eval.py 對 baseline → model_evaluation_decision 判決。
worktree 內 ./檢查.sh（全綠先算完成）；golden_scoring.py --platform au（唔加 --record，只睇逐匹馬變化）； data_contract.py --platform au --check 確認冇死欄位。
效率改動：前後計時對比 + golden 零差異；live／回測一致性：快照 vs 重評分差異表每行有解釋。
Phase A：重構前後全語料逐匹 ability 差 ≤1e-9、golden 不變、plug-in test 過。
Phase V：A/A 0% 過閘，已知案例判得返。
Phase F／R／C：每個候選都有 leakage audit、§6、walk-forward 判決、馬匹數同馬場 cohort 表。
終點檢查：報告矩陣表冇空格；每個 KEEP 有 Stage 4 輸出 JSON；每個 §7 有「唔係已證實改善」聲明。