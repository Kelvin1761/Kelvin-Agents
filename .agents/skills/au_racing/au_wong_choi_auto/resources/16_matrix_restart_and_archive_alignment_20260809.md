# AU scoring-matrix restart and archive-alignment follow-up (2026-08-09)

## Direction

今輪按用戶方向，明確唔做「保住 Top 2、只執第 3/4 slot」rerank。所有實驗都由
horse ability evidence／scoring matrix 本身出發；比較基準係已加入
`performance_quality_score` 嘅 805 場 current-runtime snapshot。

## Matrix diagnosis

現役主要能力訊號喺完整 805 場嘅 feature-alone within-race AUC：

| Signal | All | 1–8 runners | 9–12 | 13+ |
|---|---:|---:|---:|---:|
| stability matrix | 0.6226 | 0.6265 | 0.6232 | 0.6196 |
| jockey/trainer matrix | 0.6273 | 0.6427 | 0.6280 | 0.6184 |
| performance quality | 0.6124 | 0.6288 | 0.6106 | 0.6075 |
| form | 0.6105 | 0.6134 | 0.6149 | 0.6012 |
| official rating | 0.5848 | 0.5972 | 0.5682 | 0.6081 |
| pace-performance matrix | 0.5891 | 0.5951 | 0.5814 | 0.5998 |

大場表現差唔係因為 matrix 冇 spread 或某一條主訊號變成常數；係同一批能力訊號
喺 13+ runners 場更難分開第三匹上名馬。Rating／pace 喺大場反而相對更有用，唔支持
用 field-size rerank 去鎖 slot。

## Structural performance-quality experiments

以零改動必須 rank-exact 嘅 differential harness，固定 production observed cohort
（887 horses／98 covered races）測試：

- historical field-size credit (`log2(starters / 10)`)：development 同 terminal day
  方向反轉；較大 credit 全面變差；reject。
- beaten-margin distance scaling (`margin × (1400 / distance)^gamma`)：大場 AUC 有改善，
  但 terminal Pass／winner@3 下跌；reject。
- target-distance weighted run quality：development 有輕微改善，但 terminal
  Gold／Good／Pass 或 AUC 不穩；reject。

結論：`-margin + 4 × log10(prize/50000)` 保持簡單版本，唔疊 starters／途程參數。

## Research archive alignment bug

七個 research tools 仍然假設 meeting 係 `root / meeting_name`，完成後移入
`Archive/` 嘅場次會靜靜消失。舊 unused-feature scan 因此只讀 684 場。

新增共用 `sb_backfill_archive.scored_meeting_index()`：

- recursive discover `Meeting_Auto_Scoring.csv`；
- 現場見到 122 meetings，其中 34 個喺 `Archive/`；
- 同名 direct／archive snapshot 直接 fail，禁止靜默揀一份；
- unused-feature、candidate-dimension、feature-A/B、leaf-power、people-going、
  dump-leaves、leaf-substitute 全部共用同一 resolver。

修正後 feature scan 由 684 升至 955 場；candidate evaluation 有 942 場可用。

## Leakage guard

完整 scan 一度見到 `Ave $` AUC 0.635、`up_place_rate` 0.582，但兩者來自 Sportsbet
career overview。同一 overview 嘅 J/H、WinRange 已有逐匹證據會包含 target race；
所以 outcome-derived `Ave $` 同 1st/2nd/3rd-up record 一律禁止用作歷史驗證。
Live report 可以顯示，但唔可以用 post-race archive 證明預測力。

保留嘅候選必須由已按日期截斷嘅 run rows 重建：

- `dist_place_rate`：942 場，62% runners 有值；terminal Gold -0.70pp、
  champion -0.70pp，reject。
- `jh_pre_place_rate`：942 場，28% runners 有值；terminal Gold +0.70pp、
  Good +1.41pp、Pass +1.41pp，但 champion／winner@3 無升，覆蓋稀疏，未通過
  現行 promotion gate；保留 research-only，唔入 production。

再用 current-runtime snapshot 保存嘅 point-in-time 正式策騎／上名 counts，測試將
`jockey_horse_fit_score` 改成 empirical place-rate（prior 0.457；shrink K 2/4/8；
blend 25/50/75/100%）。12 個候選喺 development 594 場嘅 Top-5 AUC 全部負數
（-0.0008 至 -0.0038），Pass／Top-3 precision／winner@3 普遍同跌，毋須打開
terminal holdout。Standalone AUC 較高並不代表有 incremental value；現役 fit 保留。

## Career identity misalignment

新 Sportsbet Racecard 寫 `Career: 45 : 5-7-7`。舊 parser 只截到 `45`，下一層又要求
數字後面即刻有 `:`，結果 805 場入面：

- 947 runners 被錯標 `DEBUT`；
- 其中 945 runners 明明已有正式賽績；
- 問題集中 2026-08-05 至 2026-08-07。

修正：

- Racecard parser 保留完整 career record；
- Facts／builder／runtime parsers 同時接受完整 record 同 integer-only legacy value；
- 1–5 starts 正確標 `EARLY_CAREER`；
- 已有正式賽績但 Racecard 冇 Last 欄，唔再寫「初出馬」；
- explicit stale `DEBUT` 唔可以蓋過非零 career starts。

完整 805 場真引擎 A/B：Gold、Good、Pass、champion、winner@3、winner@5、Top-3
precision 全部 **0.00pp**；45 runners 分數改動、6 races rank 改動，Top-5 AUC
`-0.000071`。呢個係 identity／narrative correctness fix，唔列作 performance gain。

另測試移除 mature-career class heuristic：Good +0.25pp、champion +0.12pp，但
all/dev/holdout AUC 都向下，已撤回，唔 ship。

## Current conclusion

Production ranking 保留 performance-quality upgrade；本輪冇新增 rerank 或 matrix
參數。最有價值嘅改動係修正 archive research population、封鎖 mutable overview
leakage，同修正 947 匹 career identity。下一個真正有機會再提高 Gold／Good 嘅方向，
仍然係新增 point-in-time、可重播而且同現有 form/rating/PF 正交嘅能力 evidence，
例如完整 trip-adjusted sectionals 或 opponent-strength normalization。

## Legacy coverage and ability-peak follow-up

再獨立測試「舊 Formguide 冇 `starters` 欄就完全唔用」係咪過度保守。只保留嚴格
`run_date < meeting_date`、header margin、正數 prize，候選覆蓋由 98 場擴到 408 場。
完整 805 場雖然 Top-5 AUC `+0.00519`、Pass `+0.99pp`、winner@3 `+2.24pp`，但
Gold `-0.37pp`、champion `-0.37pp`，早／中／後三個時間窗亦唔一致；0.25／0.50／
0.75 blend 全部仍然令 Gold 下跌。按 Gold／Good 優先閘，**reject**，完整 schema gate
保持不變。

為免平均近績只量到「穩定」而唔係「能力上限」，亦測咗最近四仗最好一仗（max）同
最好兩仗平均（top-2 mean）：

- max 喺現役完整證據 cohort：Top-5 AUC `-0.00326`，Gold／Good／Pass 全跌；
- top-2 mean 喺現役 cohort：Top-5 AUC `-0.00118`，Gold／Good／Pass 全跌；
- 擴闊 legacy coverage 後 top-2 mean 全樣本只有 Gold `+0.12pp`、Good `+0.50pp`，
  但 Pass `-0.12pp`，三段時間窗方向不穩，bootstrap CI 跨 0。

所以冇以「peak ability」名義偷偷換走穩定、可重播嘅 recency-weighted mean。最新完整
舊版對比（career identity correctness fix 一併計入）係 Gold `+0.87pp`、Good
`+0.87pp`、Pass `+1.37pp`；Top-5 AUC `0.68640 → 0.69276`，paired bootstrap
CI `[+0.00296, +0.00982]`。全套 regression：**444 passed**。

## Sportsbet L600 semantic alignment

原始資料重審發現 `Sectionals 600m` 係 **race-level** 賽事末段時間，唔係每匹馬自己嘅
個體末段。1,067 份 Formguide 共 9,230 個歷史 race keys；其中 3,589 個 key 有兩匹
或以上馬重疊，**3,589/3,589（100%）數值完全相同**。舊報告將
`pace_figure_score` 寫成「本駒實測段速」係資料語意錯位。

直接中性化 leaf 嘅 true-runtime ablation：

| Window | Gold | Good | Pass | Champion | Winner@3 | Top-3 precision |
|---|---:|---:|---:|---:|---:|---:|
| dev 594 | +0.34pp | **-2.86pp** | -0.34pp | -1.01pp | 0.00pp | -0.17pp |
| holdout 211 | +0.47pp | **-0.95pp** | **-2.37pp** | +1.90pp | +1.90pp | -0.16pp |

即係佢作為「曾經面對咩速度考驗」嘅 race-context proxy 仍有 incremental value，直接
剷走會明顯傷 Good／Pass；但唔可以繼續冒認為個體能力實測。Production 計分保持不變，
顯示同 reasoning 已改名做「速度考驗背景／L600 環境分」，並明講 Sportsbet 數值係
race-level。下一個結構升級應該取得真正逐駒 sectional，或者將 PI／走位／輸距整合成
可驗證嘅 trip-adjusted 個體速度，而唔係再調呢個 proxy 嘅 weight。

## Source-aware PF correction

再由完整 runtime 追查 provenance，發現 805 場其實混合兩種 L600 語意：

- 舊 Racenet：逐駒 `competitorFormBenchmark`，包含 runner-level L800/L600/L400/L200；
- 2026-08-05 起 Sportsbet：歷史賽事 race-level `Sectionals 600m`。

最新 100 場 Sportsbet Formguide 落入 Logic 後仍被硬標成 `racenet_formguide_cfb`，係真實
provenance misalignment。修正後 Sportsbet PF token 明確寫
`Source: sportsbet_race_context`；舊檔則用 `WinOdds:` fingerprint 恢復來源。Engine
note 依來源分流：Racenet 可寫「逐駒 benchmark」，Sportsbet 只可寫「所在賽事環境」。
scoring arithmetic 同排名完全不變。

固定語意 A/B 亦證明唔應因命名錯誤粗暴剷 leaf：只對最新 100 場中性化 Sportsbet
context，Good／Pass 各跌 4.00pp、Top-5 AUC 跌 0.00709；以 PI 取代則 Pass 跌
5.00pp。保留訊號係因為佢有 race-context incremental value，唔係將佢冒認為個體速度。

## Structural trip / opponent follow-up

以 Sportsbet raw cache 嚴格 `run_date < meeting_date` 重建個體走位與對手線，development
594 場先行，未通過者一律冇打開 holdout：

- closing gain（400m／800m／settled 至終點）：普遍拖低 Good／Pass；後上追過慢馬並不
  等於 placing ability；reject。
- late control（400m position、finish percentile、sustained-front）：同現役 form／pace
  重疊，所有候選未過 Gold／Good／Pass gate；reject。
- point-in-time opponent strength（歷史 top-3 對手喺該仗之前嘅近四仗表現）：最佳整體
  候選只得 2/5 folds 同時守住 Gold／Good／Pass；recent／strongest variants 更差；reject。
- point-in-time formline franking（歷史賽事之後、今次賽前，當時 top-3 對手有冇再
  贏／上名）：win/place/best-finish、winner-only、mean/recent/best 共 15 個預先定義
  版本全部拖低 Pass，多數亦拖低 Good；最佳只得 0–2/5 folds 通過；reject，holdout
  未打開。

舊 Racenet 完整 split 另有一個有方向性嘅 shadow：
`closing_600 = L600 benchmark delta - finish-time delta`。完整-profile cohort development
Gold `+0.17pp`、Good `+0.51pp`、Pass `+1.52pp`、Top-5 AUC `+0.00494`，但只有 3/5
folds 同時無倒退，而且完整 split 集中早期 archive，近期 confirmation coverage 不足。
擴到只要求 L600 + finish-time 後，Gold／Good 穩定性消失。結論係保留 shadow，唔升
production；真正下一步係累積 source-labelled、完整逐駒 split forward window。

## Matrix aggregation and overlap follow-up

錯誤分解顯示，喺 model Top 4 只捉到兩匹實際 Top 3 嘅 373 場，最高分漏馬相對最弱
錯選馬嘅平均總分差係 `-5.62`；主要表面分差來自 stability `-1.92`、
jockey/trainer `-1.42`、pace-performance `-0.84`。呢個係按模型選出嘅 cohort，帶有
selection bias，唔可以直接解讀成「邊個維度過重」。所以後續只喺 development 測結構
假設，未有用呢個分解直接調權重。

先測「人／情境分過重、馬匹自身能力分過輕」：將 jockey/trainer 單獨減 10–100%，
或者將 jockey/trainer、race-shape、track 一齊減 10–100%，釋放權重按現有比例歸還
stability、pace-performance、class/rating。最輕微嘅 jockey/trainer -10% 已令
development Good `-0.84pp`、Pass `-1.68pp`、Top-5 AUC `-0.00163`；其餘幅度更差，
跨五個時間段亦冇一致性。即係現有 matrix 唔係靠簡單「能力加權、情境減權」就會改善。

再測四種非線性 horse-ability aggregation，全部保持 context contribution 不變：

| Variant | Gold | Good | Pass | Top-5 AUC | 三項同時不跌 folds |
|---|---:|---:|---:|---:|---:|
| peak capacity | -0.51pp | -3.37pp | -2.02pp | -0.00713 | 0/5 |
| floor reliability | +0.84pp | -1.01pp | +1.18pp | +0.00177 | 1/5 |
| median corroboration | 0.00pp | -1.52pp | -0.34pp | +0.00014 | 1/5 |
| range balanced | +0.51pp | -2.19pp | -1.52pp | -0.00073 | 1/5 |

高峰／下限／多訊號互證都冇同時改善 Gold、Good、Pass，reject，holdout 未打開。

維度重複亦冇見到嚴重問題。場內中心化後最高 pairwise correlation 只係 stability vs
jockey/trainer `+0.255`，其次 jockey/trainer vs class/rating `+0.245`；其餘大多低於
`0.15`。Development leave-one-dimension-out（剷走後其餘權重正規化）六個版本全部令
Good 下跌：stability `-5.05pp`、pace-performance `-2.86pp`、race-shape `-3.03pp`、
jockey/trainer `-4.71pp`、class/rating `-3.37pp`、track `-0.17pp`。Track 最接近可簡化，
但仍同時令 Gold `-0.84pp`、Pass `-1.18pp`；所以暫時冇任何維度可安全移除。

最後，將近績名次階梯改為連續 field-percentile 呢個結構方向只有 786/8,249 匹有真實
field-size，並集中喺最新 source era；development 冇足夠覆蓋，無法在不偷看 terminal
holdout 嘅情況下驗證。保留為 forward shadow，等累積 source-labelled 新樣本後再判斷，
唔用「只喺最新資料先存在」嘅訊號反推 production。

## Six-dimension ranking contract alignment

現役 `MATRIX_WEIGHTS` 已經只有六個 ranking dimensions，`form_line` 只係 report-only；
但 code/report 仲有兩個殘留錯位：

1. 核心分析揀「最強／最弱維度」時掃晒 `matrix_scores`，會將零權重 `form_line` 當成
   正式 ranking 維度；
2. renderer 嘅 `_zero_weight_dimensions()` 只掃 `MATRIX_WEIGHTS.items()`，所以已經從
   registry 移除嘅 `form_line` 反而永遠唔會被標成「參考·不入排名」。

修正後，最強／最弱只會從六個現役權重 key 揀；report-only set 同時包括「不在權重
registry」及「顯式 0 權重」兩類。所有用戶可見字眼改為「六維排名＋參考維度」。
`pure_7d_score`／`base_7d_score` 欄位名暫時保留，只作 archive／CSV compatibility，
其數值定義明確係六維 base score。呢個修正唔改任何排序，但移除咗一個會誤導日後
debug／加權決策嘅假第七票。

## Incremental ability and third-horse cohort audit

為咗避免只睇 standalone AUC 又再將重複訊號塞入 matrix，後續所有候選用現行最終分做
直接 incremental A/B，development 594 場先行，Gold／Good／Pass 要共同守住。

### Long-term point-in-time ability

只由 `run_date < meeting_date` 正式往績重建 Bayesian-shrunk career place/win rate，唔讀
mutable career overview。覆蓋 7,653/8,249 匹至少一場，composite standalone AUC
`0.6100`；但將三分一 stability vote 改用佢後，Gold `-0.84pp`、Good `-1.52pp`、
Pass `-2.53pp`、Top-5 AUC `-0.00716`，只有 1/5 時間窗三項同時不跌。訊號健康但同
form／rating／connections 高度重複，reject，holdout 未開。

### Report-only feature incremental audit

將每個 report-only leaf 逐一作 5% 結構維度，現役六維同比例縮至 95%。八個候選全部
未能共同守住 Gold／Good／Pass：

- distance：Gold `-0.67pp`、Pass `-0.51pp`；
- health：Gold `-0.67pp`；
- confidence：Gold `-0.51pp`、Pass `-0.51pp`；
- formline：Good `-0.67pp`；
- consistency：Gold／Good 各 `-1.01pp`、Pass `-1.85pp`；
- sectional：AUC `+0.00242`、Gold `+0.51pp`，但 Good `-0.17pp`、Pass `-2.02pp`；
- weight：AUC `-0.00142`；
- class：Gold `-1.18pp`、Good `-1.01pp`、AUC `-0.00430`。

即使 sectional 改善部分 pairwise ordering，都明顯交換走 Pass，唔符合 promotion gate。

### Evidence reliability shrinkage

現役 ranking-evidence coverage 平均 83.0%、中位 81.8%。測試將能力離差按 coverage
線性或平方根收縮；平方根版本 Good `+0.67pp`、AUC `+0.00076`，但 Gold
`-0.34pp`、Pass `-0.17pp`，只有 2/5 folds 三項同時不跌。低覆蓋確有少量
over-confidence，但全局收縮亦壓走真能力，reject。

### Two-hit Top-4 target structure

Development 594 場 Top-4 命中分佈：0匹 25 場、1匹 192、2匹 **279**、3匹 96。
正正命中兩匹嗰 279 場，第三匹實際上名馬嘅 model rank：

- rank 5：85（30.5%）；
- rank 6：67（24.0%）；
- rank 7：44（15.8%）；
- rank 8+：83（29.8%）。

Target 並非集中大場：two-hit target rate 1–8 runners 54.8%、9–12 runners 49.5%、
13+ runners 37.4%；乾地 52.0%、濕地 43.6%。279 匹 target 全部都係
`performance_quality_score:fallback`，反映新 performance-quality 證據集中最新 source
era，未覆蓋舊期主要 miss population。呢個結果支持累積 forward evidence，唔支持按
field size／going 做 slot rerank。

### Winning-margin semantic counterfactual

賽績表會將頭馬顯示成例如 `1 (-6.5L)`；cache 原值係正數 winning/beaten-margin 幅度，
現行 quality formula 用 `abs(margin)`。嚴格測試兩個自然語意版本：頭馬 margin 歸零、
或者頭馬按勝距給有限 credit。擴闊 point-in-time development cohort，winner-neutral 同
現行版本場數指標一樣；winner-credit AUC 轉負兼再傷 Good。現役 strict cohort 再做單一
correctness impact audit，winner-neutral 相對同 cohort absolute-margin 令 Gold 約
`-0.95pp`，Good／Pass無改善，winner@5 約 `-0.95pp`。因此唔用語意直覺推翻已驗證
regularizer；要重建真正 winning-margin ability，需先有更長、source-labelled development
window。

### Forward evidence capture

為咗令下一個 confirmation window 唔再依賴可能賽後刷新嘅 archive page，
`_performance_quality_digest()` 而家除咗 raw/count，亦會保存實際入過公式嘅逐仗
point-in-time evidence：`date`、`finish_pos`、`margin`、`prize`、`starters`、`distance`
同該仗 `quality` contribution。資料會 round-trip 到 horse `_data` 同
`stability_detail.performance_quality.runs`，但完全唔加入新分數或改動現行 formula。

呢個 transport 令未來可以預先定義並獨立驗證 winner-margin、distance-adjusted margin、
source-era 同完整 schema coverage，而唔使由賽後頁面反推。完整 AU auto／daily／shared
regression：**445 passed**。

## Gold / Good / Pass contract audit

重新由全 AU codebase 開始掃描，主 evaluator 雖然已經係新定義，但一批仍可直接執行嘅
research／rescore scripts 仲保留舊 ruler：`Good = Top3 任兩匹`、`Pass = Top3 任一匹`，
部分亦仍將舊 `3/3` 當成 Gold。呢個會令同一個 matrix candidate 喺唔同工具出現相反
結論，屬於 evaluation data misalignment。

新增薄 adapter `au_metric_contract.ranked_performance()`，所有 row-shape 轉換集中喺一處，
真正定義仍由 `shared_racing/eval_metrics.py` 單一維護。以下工具已統一：

- weight improvement、bugfix impact、rescore/eval、target-gap；
- cached walk-forward、Phase-5、formline、formguide、JT impact、archive rescore；
- AU ML matrix diagnostics、AU/HKJC gap report、unified reflector labels。

現役輸出而家只用：Gold＝實際前三全部喺模型 Top4；Good＝模型第 1、2 都入實際前三；
Pass＝模型 Top3 任兩匹入實際前三。共享 compatibility aliases 暫時只留畀 archive caller，
唔會再出現在新 AU markdown／JSON。新 adapter 加咗直接 regression cases，連同全套測試
現時 **448 passed**。

用修正後 ruler 重跑 805 場 current runtime，baseline 完全冇變：Gold `17.02%`、Good
`25.71%`、Pass `47.20%`、Top-5 AUC `0.6928`；證明今次只修正評估一致性，冇加工
production ranking。

## Ability-signal time drift audit

再按五個完整日期窗口量每條訊號嘅場內 AUC，避免將早期有效性當成永久不變。兩條最強
horse-ability spine 保持健康，而且最新窗口反而增強：

| Signal | Full | W1 | W2 | W3 | W4 | W5 (latest) |
|---|---:|---:|---:|---:|---:|---:|
| jockey/trainer matrix | 0.6271 | 0.6553 | 0.6153 | 0.6317 | 0.6121 | 0.6394 |
| stability matrix | 0.6226 | 0.6164 | 0.6157 | 0.6163 | 0.6096 | 0.6473 |
| performance quality | 0.6123 | 0.6056 | 0.6004 | 0.6126 | 0.5921 | 0.6460 |
| form | 0.6105 | 0.6059 | 0.6185 | 0.6045 | 0.6071 | 0.6128 |

相反，兩條 context 維度出現明顯衰減：track `0.5603 → 0.5032`、race-shape
`0.5312 → 0.5128`。但呢個未足夠支持直接刪除：五個窗口逐段 leave-out 方向不一致；
最新窗口剷 track／shape 各自雖令 Pass `+0.91pp`，同時令 Gold分別 `-1.37pp`／
`-0.91pp`。兩個一齊剷就 Gold `+0.46pp`、Pass `+0.46pp`，但 Good `-0.46pp`，而
較早窗口明顯倒退。

所以暫時唔做 source-era conditional weight，亦唔為最新一段過擬合。結構結論係：

1. 最新 performance gain 真係來自較接近馬匹能力嘅 stability／performance-quality spine；
2. track／shape 值得列入 forward drift monitor，但未夠證據剷走；
3. 下一個可升級方向應該係擴大 source-labelled individual ability evidence，而唔係再疊
   一層 rerank 或按時期切換權重。

## Sportsbet record-field alignment audit

由最新 track signal 接近隨機再向上追 provenance，發現 Sportsbet 原始 cache 同
Formguide 其實有完整紀錄，例如：

- `Track: 1: 0-0-0`；
- `Distance: 27: 3-5-4`；
- `Good: 18: 3-2-2`、`Soft: 20: 1-4-4`、`Heavy: 7: 1-1-1`。

真正斷點係 `inject_fact_anchors._enrich_stats_from_formguide()` 用 `\S+` 取值，遇到
record 內部空格就只寫 `1:`／`18:` 落 Facts。更嚴重係 engine 之後將整條 compound
line 丟入 permissive number parser：`1: | 同程: 27: | 同場同程: 0:` 會被解讀成
同場 starts=1、wins=27，製造不可能嘅「同場有實際上名支持」。

資料層修正改為只接受完整 `starts:wins-seconds-thirds` schema，並喺 Facts boundary
正規化成 `1:0-0-0`；partial token 一律當缺失。Engine safety 同時只會讀 compound
track row 第一個 segment，舊 malformed archive 唔再跨欄借用 Distance 數字。

修正並冇順手啟用新 Good-going scoring。雖然 Facts leading segment 係 Good record，
但將佢首次直接加入 track branch 屬模型規則變更；805 場 A/B 未過 terminal gate，
所以保留為 report evidence，Soft／Heavy 仍沿用既有明確 label contract。

### Corrected-record runtime A/B

固定同一 805 場、8,249 runners，結果只喺 scoring 完成後 join。按日期切 development
594／terminal holdout 211，並另做五個時間 fold：

| Variant | Dev Gold | Dev Good | Dev Pass | Hold Gold | Hold Good | Hold Pass | 判決 |
|---|---:|---:|---:|---:|---:|---:|---|
| 舊錯位 parser | 16.16% | 26.26% | 46.63% | 19.43% | 24.17% | 48.82% | baseline |
| 只做 field-safe defensive parse | 16.33% | 25.93% | 45.96% | 18.48% | 24.17% | 49.29% | correctness only；performance 不升級 |
| 完整 Track + Good/Soft/Heavy 全啟用 | 16.33% | 25.93% | 45.79% | 21.33% | 23.70% | 49.76% | Gold 升、Good／winner@5 跌；reject 新規則 |
| 完整 record、保持舊 going parser | 16.16% | 26.26% | 46.46% | 21.33% | 23.70% | 49.29% | 資料正確；未達 performance promotion gate |

全體 805 場「完整 record、保持舊 going parser」相對舊錯位 baseline：Gold 約
`+0.50pp`、Good `-0.12pp`、Pass持平、winner@5 約 `-0.50pp`。因此今次以 bug fix
身份保留完整資料同 field isolation，但唔宣稱為 performance candidate。

### Matrix simplification / refit outcome

完整 record 揭示 going record 同時入 `track_score` count-based branch，再入獨立
Bayesian-shrunk wet overlay，確有重複計算。移除 track 入面 going branch後，terminal
holdout Gold `+1.42pp`、Good `+0.95pp`、Pass `+1.90pp`，但 development Gold
`-1.01pp`、Good `-0.51pp`；時間穩定性不足，reject。完全移除 same-track／track
record branches亦更差。

最後用 corrected-evidence snapshot 重新搜索 10,000 組六維權重，只用 dev + 4/5 fold
選候選。130 組過閘後嘅 consensus 雖令 dev Pass `+1.75pp`，terminal holdout 卻令
Gold `-4.96pp`、Good `-1.65pp`、Pass `-4.13pp`。即係現階段唔可以借資料修復重配
matrix；production 六維權重保持不變。

結論：呢次查到嘅係真正資料錯位，而唔係第三／第四 slot 問題。修復會令未來 evidence
可審計，亦阻止不可能嘅同場勝出數進入理由；但任何利用新完整 record 改排名嘅方案，
仍要等 source-labelled forward window 再驗證先可升級。AU auto／daily／shared regression
現時 **439 passed**；另有 syntax compile、`git diff --check` 同 Seymour 真實 Formguide →
Facts smoke test 通過。

## Missing-third cohort / new ability evidence follow-up

按用戶方向，後續冇做「保 Top2、只執第 3/4 slot」rerank，而係直接比較 805 場內：
模型 Top4 只中兩匹實際 Top3 時，被漏 actual-Top3 馬同 Top4 false-positive 馬嘅能力 leaf。
呢個 cohort 有 369 場／740 對；development 276 場／554 對，terminal 93 場／186 對。

結果顯示漏馬唔係被某條強訊號局部壓低：form、performance quality、consistency、rating、
jockey 等幾乎全部都將 false-positive 評得更高。唯一 development／terminal 都略為偏向漏馬
嘅係 weight_score（pair win `52.8%`／`54.0%`），但佢全樣本 within-race AUC 已驗證只有
`0.480`，而且 84.9% runners 恰好中性 60；重新加入 matrix 會將 cohort selection effect
誤當全局能力訊號，所以唔升級。

另測兩個真正 matrix candidates：

- historical HC missing-rating fallback：87 場／804 馬有 coverage。最佳輕量版 development
  Gold `0.00pp`、Good `-0.17pp`；terminal Gold `-0.47pp`、Good `+0.47pp`，Gold／Good
  互換，reject；
- weighted within-race rank consensus：development Pass 最多 `+0.67pp`，terminal Good／Pass
  各 `-1.42pp`，reject。

所以現有 evidence 支持「要新 individual ability data」，唔支持 slot rerank、Borda、重新加入
負磅，亦唔支持將舊 HC 直接當今仗 official rating。

## HC semantic alignment and point-in-time boundary

再追 Formguide provenance，確認 crawler `HC:106` 係**該馬當仗 handicap rating**；同一場
唔同馬有不同 HC，所以絕對唔係 `BM106` race class。舊 Facts writer 卻將有 HC 寫成
`BMxx`，冇 HC 更武斷寫成 `Maiden/SW`。現改為：

- `HC106`：明確歷史 horse rating；
- `正式`：正式賽但 HC 缺失；
- `試閘`：trial；
- record parser 將新 `HCxx` 保存為 `historical_rating`，而 legacy `BMxx` 唔自動猜測，避免
  genuine race-class 手寫資料再次受污染。

呢個修正唔改 production ranking；佢移除錯誤解說，亦令未來 HC forward dataset 有清楚 schema。
Target-gap report 同步移除舊 `minimum` 內部名，統一叫 Pass；Gold 文字修正為「實際前三全部
落入模型 Top4」。

最後發現 post-race refresh safety 原本唔完整：Performance Quality 有 `run_date < meeting_date`
閘，但 dossier form、jockey history、recent shape 同 live PF parser 未共用同一條 boundary。
現時三個入口都統一嚴格 censor target-date／future rows：Facts dossier writer、Formguide digest、
PF token parser。現有 805 場 snapshot 掃描係 0 個 non-pre-race row，所以基準數字冇受污染；
但用含 2026-08-01 賽果嘅 post-race Formguide 重跑 2026-08-01 meeting smoke，修正前會收當日
row，修正後第一行正確退回 2026-07-18，證明 archive rerun 唔再滲入賽果。

最新 AU auto／daily／shared regression：**444 passed**；syntax compile、`git diff --check`、
dated post-race refresh smoke 全部通過。

## Individual completion-time ability matrix

按「改善 horse ability matrix、唔做第 3/4 slot rerank」方向，重新審計 PF 語意後確認：
Racenet `race_time_diff` 係逐駒相對 benchmark 嘅完成時間；同一歷史賽事唔同馬數值會按
實際完成時間不同。Sportsbet `Sectionals 600m` 則仍然係 race-level context，絕對唔可以
混入個人能力。候選因此只接受：

- source = `racenet_pf_historical_backfill` 或 `racenet_formguide_cfb`；
- run date 嚴格早過 meeting date，而且 90 日內；
- run distance 距今場不超過 100m；
- 全場至少 3 匹有同口徑 evidence；
- `abs(race_time_diff) <= 8`，再作場內 z-score（clip ±2.5）。

805 場共有 579 場／4,098 匹符合；PF transport 現保存每仗 `run_date` 同 `distance`，令
forward test 可直接重播上述 point-in-time eligibility。候選唔新增第七維，只喺既有
`pace_perf` 內比較個人完成時間同現有 L600 context/trial。

兩個最有代表性版本：

| 結構 | Dev Gold | Dev Good | Dev Pass | Hold Gold | Hold Good | Hold Pass | 5-fold 三項全不跌 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 75% 現有 pace + 25% 個人時間 | 0.00pp | +0.67pp | +0.34pp | 0.00pp | +0.47pp | 0.00pp | 4/5 |
| 25% 現有 pace + 75% 個人時間 | 0.00pp | +0.17pp | +1.01pp | +0.47pp | +0.95pp | +0.95pp | 2/5 |

第二個版本 terminal winner@3 `+1.42pp`，方向吸引；但正式 promotion gate 未過：Top-5
AUC dev `+0.00050`、holdout `+0.00322`，holdout paired-bootstrap 95% CI
`[-0.00477, +0.01159]`。第一個較穩版本 AUC dev `+0.00231`、holdout `+0.00051`，CI
同樣跨零 `[-0.00373, +0.00488]`。只計真正 active terminal races 亦只有 96 場，CI 更闊，
證明唔可以用「全體被無資料場稀釋」作理由繞過閘。

多仗聚合（兩仗平均、recency weighted、best-2、true median-3、mean-3）亦測過：平均版本
令 terminal Gold 跌，best-2 令 Pass 跌，median/mean 跨時間窗不穩；全部 reject。

另外用 **不讀賽果** 嘅 1,546 個去重 PF runs 擬合 tempo 背景，`race_time_diff` 同
`Tempo QRank` correlation `0.578`，斜率約每 1.0 QRank `+3.691s`。呢個證明個人完成時間
確實受歷史賽事步速影響；但 tempo-residual 版本雖令 dev Gold `+0.67pp`，同時令 dev
Good `-0.17pp`、Pass `-0.51pp`，terminal Good `-0.47pp`，所以亦 reject。

結論：Racenet 個人完成時間係目前最有潛力嘅新 ability evidence，亦比 slot-rerank 合理；
但現有 confirmation window 未足以正式改 ranking。保留為 source-gated forward shadow，
production matrix／weights 不變，等新賽事累積後以同一預先定義 gate 重驗，唔事後改門檻。
