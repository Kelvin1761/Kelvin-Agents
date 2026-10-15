# EXP-20261015-14 — Sportsbet-only 速度欄位盤點與計算定義

狀態：**SOURCE INVENTORY／DESIGN COMPLETE，未fit、未A/B、未發布模型。**
日期2026-10-15；基準 `9f0360c7d57a72f6aedc86241a0aaf63302364c0`。
用戶更正：本輪充分利用Sportsbet來源，其他時間供應商研究擱置。
這份是研究規格，不是人手改寫「Wong Choi 模型說明」。

## 範圍及來源紀律

- 唯一實驗輸入：Sportsbet Long Form原始cache及其賽前往績。
- 不讀RQ／Tasracing／Racenet逐駒時間，不用外部時間bundle補空。
- source parser沿用現役`claw_sportsbet_form.py`；reader不建立fetcher、沒有網絡請求或生產寫入。
- 此次盤點不是整個Sportsbet mobile／API的完整schema審計，不能以Long Form缺欄位便斷言所有產品沒有。
- 原有外部全程A在正式code仍存在；這輪未改動。未來Sportsbet-only試驗必須明確把它設0，
  不可將外部來源A的成績或12.5%／16.15%覆蓋率算成Sportsbet結果。
- 先定義、再鎖候選及測試；本輪沒有用Gold/Good來選feature／權重。

## 實際盤點

輸入mapping用scheduler的`sb_archive_meeting_ids.json`，只讀target date 2026-10-15／16。
46/46頁cache齊，542個runner block（馬次，含不同race重複報名；不等於542匹實際出賽馬）。
修正後parse共4794條往績；試閘1233、目標日或未來277條排除，餘3284條較早正式賽occurrence。
514個區塊有唯一最近正式賽，28個沒有可見較早正式賽；後者不當成已證實初出。
以下是當前兩天頁面樣本，不能外推全歷史覆蓋，也不是模型命中率。

| 欄位 | 最近正式賽有值／514 | 全部區塊有值／542 | 語義 |
|---|---:|---:|---|
| Winning Time | 514（100%） | 94.83% | 該場頭馬時間，非每駒完成時間 |
| Sectionals 600m | 478（92.996%） | 88.19% | 同歷史賽事共用末段環境；leader／winner及起止鐘reference未certify |
| margin | 514（100%） | 94.83% | 本駒終點負距；冠軍歸0，非時間 |
| finish／field | 514（100%） | 94.83% | 終點名次／出賽數；非標準結果仍需另flag |
| 800m position | 475（92.41%） | 87.64% | 剩800m時名次，非L800秒數或落後馬位 |
| 400m position | 493（95.91%） | 90.96% | 剩400m時名次，非L400秒數或落後馬位 |
| settled position | 250（48.64%） | 46.13% | 早段定位名次，非速度 |
| 1200m position | 109（21.21%） | 20.11% | 位置；短途不適用，缺值不代表落後 |

原文raw標籤：Winning Time4754、Sectionals600m3797、Finished4794。
修正前parser全部往績取到WinningTime4750、L6003797、Finished4788；原文存在不等於parser取齊。
raw drill證實空白騎師`Jockey , Weight kg`令`[^,]+?`跨到下一條run找非空名字，6處匹配吞掉
第二個Finished，並把後仗騎師／負磅歸到前仗。
候選修正允許空騎師，並禁止RE_RUN越過下一個Finished錨；修正後Finished4794、
WinningTime4754、L6003797與本樣本原文標籤完全一致，跨run match 6→0。
共恢復4條trial及2條較早正式run；不是新增供應商或估算時間。
同一46頁raw hash不變，latest514個欄位presence及數值逐筆不變；沒有聲稱因此提升排名。
原4788條中4783條逐字段相同，5條錯配記錄被替換；另恢復6條，詳見parser-run-parity.json。
global parse與runner-assigned runs數一致，無孤兒配對。

嚴格按(場地,日期,場號,途程)分組、不同馬名比較、只用較早正式賽：
- WinningTime：417場可比，416場共用同值；1場source衝突（Bathurst 2026-09-13 R3 1200m，
  70.330 vs70.420）。往後benchmark須整場隔離，不平均、不挑多數或頭馬行補值。
- L600：391/391場同值。這是race-level重複的證據，不是逐駒split覆蓋。
- 原文Finishing Time／Runner Time／Elapsed Time／FinishTime／L800／L400／L200標籤均0。
  這只描述這46頁；未認證的欄位不以頭馬鐘、名次或margin偷偷補成實測。

原文live頁亦已直接核對：
https://www.sportsbetform.com.au/453244/3450705/
同一較早Illawarra Grange 2026-10-01 R4 1200m，Charlie Hustle第6及King Julian第8，
頁面共用WinningTime1:10.160及L60034.500。不同finish／margin不會令這兩個欄位成為own time。

主站亦直接展開一個已完成賽事的Fast Form往績核對：
https://www.sportsbet.com.au/horse-racing/australia-nz/hawkesbury/race-1-11046741
Angel Hair的2026-10-01 Illawarra Grange往績為第4/9、負3.9L，顯示`Time: 01.10.16`及
`Last 600m: 0:34.50`，與Long Form同一場頭馬1:10.160／場級34.500一致。
因此主站樣本的`Time`標籤不能直接解讀為本駒finish time；這不是完整API schema證明。

## 正式命名與可以／不可以計的量

### 1. 賽事全程背景（observed race context）

`race_avg_kmh = 3.6 × D / T_winner`。
只代表頭馬全程平均速度；1200m與2000m不能直接比km/h當實力。
更可比較的定義：`race_total_residual = −(log(T_winner / D) − prior_par(course, exact_distance, going, class))`。
標準只能由Sportsbet同一歷史event去重後、target前已可用資料估，數值衝突整場隔離。
場地layout／surface不合併；缺地況保留unknown，不能默認Good。
稀疏cell收縮／fallback需先登記規則，不能看結果揀最有利的場地或距離格。
par標準、樣本數及fallback層級需隨輸出一併記錄。

### 2. 本駒相對表現（observed relative result，非秒數）

分開保留終點負距、名次／出賽數、班次及上面賽事全程背景，聯合估下次出賽表現。
`finish_percentile = (finish − 1)/(starters − 1)`僅限有效1≤finish≤starters且starters≥2。
`beaten_lengths`冠軍0；負值／非標準finish／極端負距要flag，不無條件clip成正常跑績。
不先把負距硬轉秒：`T_winner + 0.17×margin`若將來研究，名稱必須是estimated total，
而且不是唯一canonical數據、不和實測逐駒時間混在同一coverage。
本輪不採用該公式、不挑換秒係數；模型可否從context＋相對表現學到額外訊號尚未測。

### 3. L600賽事背景（observed race context）

L600只作獨立的歷史賽事末段背景；與全程背景分開保留、共同建模。
`T_winner − L600_race`未證明兩個鐘有相同跑線／起止reference，
所以暫不稱為實測頭段時間，更不能當本駒頭段速度。
即使差值數學上合理，也不代表物理上可識別本駒用力多少。

### 4. 途中位置（observed ordinal position）

`p800_fraction = (p800 − 1)/(starters − 1)`，p400同理；0領放、1包尾。
用來描述跑法及位置變化。800m第8與第1之間可能相差兩個或十個馬位，
所以不能用「名次差 × 固定馬位」假造實測落後距離、分段時間或疊數。
1000/1200有p800不代表有L800鐘；沒有L600個體鐘亦不能從p400補成L600鐘。
2000−800與1400−800的頭段長度問題，在此來源不能以km/h轉換解決缺失的個體計時。

### 5. 已有PF代理（existing heuristic，不是新發現）

現役`_pf_aggregates`有`own_l600_delta = l600_delta + margin×0.17`。
這是負距修正的L600環境代理，**不是Sportsbet量到的本駒L600**。
source marker `sportsbet_race_context`和現役note有區分來源，internal own名稱不代表實測。
新試驗須與它做增量／ablation，避免重複加margin兩次；不為了新名詞再加同一訊號。

## 時間可用性與品質

- 每條input的previous_date必須<target日，trial排除；latest缺值不跳舊場冒充latest。
- 去重key包含場地／日期／race／distance與horse；source衝突不last-write-wins。
- sample prior margin範圍0–246.86，finish最小−5；有非標準完成狀態，不能全部當正常完賽速度。
- cache mtime不證明賽前capture。本盤點只證明當前能讀到哪些欄位，availability仍FLAG。
- 每頁receipt留URL、SHA及mtime診斷；mtime不拿來清除historical PIT FLAG。
- 不引入市場價、賽後目標賽名次、今天累積生涯表或失手體檢作feature／擇參。

## 下一階段測試規格（尚未執行）

先搜尋已有試驗：EXP-20260831-07/-09、EXP-20260927-02、EXP-20261013-10/-11。
舊試驗已測過WinningTime、0.17換秒、名次×馬位、WT−L600；不能換名重做並說是新signal。
其「Sportsbet資料已用盡」結論也不能當數學證明；clock-reference／proxy問題仍要明示。

先做「單次正式往績」的來源及par正確性檢查，再預登記一個聯合context／margin方向。
只有定義及品質驗證完成才開始下面測試：

1. **純訊號**：所有其他leaf中性60、overlay0（外部A亦0）。先測race total context／margin／
   兩者合併；同一observed cohort、同一上名／落第pairs，不能以不同coverage AUC冒充增益。
2. **增量**：對Sportsbet-only基準做單項與組合ablation，分清係多用時間還是再用一次margin。
   接現役前另保留已知良好production score對照；不靜靜撤掉既有分數令候選看似贏。
3. 路程、場地、地況、班次先用target前Sportsbet資料建標準；不可先fit全池再切fold。
   使用既定clean-era exclusions及完整日期walk-forward；真正holdout不調參。
4. 原Gold／Good primary、五ranking metric、按日bootstrap2000 seed7、六時間塊、家族Holm。
   field-size／距離／地況／venue cohort均報；結果好才走原有發布閘。
5. 原始實測欄位、代理欄位及缺值／品質狀態分開存；本輪定義未fit，所以沒有新weight或KPI成績。

## 可重現性與交付

命令：
```bash
PYTHONDONTWRITEBYTECODE=1 WC_SB_CACHE_ONLY=1 python3 scratch/au_sportsbet_time_inventory.py \
  --mapping /Users/imac/wongchoi-scheduler/.agents/skills/au_racing/data/sb_archive_meeting_ids.json \
  --cache /Users/imac/wongchoi-scheduler/.agents/skills/au_racing/.sportsbet_cache \
  --target-date 2026-10-15 --target-date 2026-10-16 --out <artifact-root>/inventory.json
```
Artifact根：`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/Sportsbet-only-inventory/`。
輸入mapping／parser／reader SHA及逐頁SHA在inventory；cache會更新，重跑前必須驗證原hash。
六項inventory tests驗證strict cutoff、trial、distinct event分組、conflict保留、surface、latest缺值不回填；
另外五項parser regression tests驗證空騎師、每match只一個Finished、缺metadata不借後仗、缺鐘不回填。
`./檢查.sh --quick`及完整`./檢查.sh`結果與delivery manifest在artifacts。
候選code包含scratch reader／tests及一個Sportsbet parser邊界修正；
正式評分公式、golden、dashboard、來源refresh及排程無修改。候選未merge／部署。
修正前inventory.json／before-parser-fix.json、修正後after-parser-fix.json及parser-fix-proof.json分開保存；
raw HTML與mapping已freeze並核對原hash，命令可把mapping/cache參數改為artifact根的
`frozen-mapping.json`／`frozen-cache`，不需依賴會更新的生產cache。
