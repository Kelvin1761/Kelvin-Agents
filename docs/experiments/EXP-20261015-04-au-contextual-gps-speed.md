# EXP-20261015-04 — AU 情境速度與 total − L800 頭段

狀態：COMPLETED／PROMISING DIAGNOSTIC／NOT SHIPPED；PIT availability FLAG。

基準 production `7a962be5`；凍結 EXP-20261015-03 同一份 fresh engine dump。
資料根、來源、hash 沿用原實驗 artifact，再擴官方 GPS 來源至 2025-01-01—2026-10-14
索引上全部 706 CSV（舊316係其中一部分）。不複製完整語料。

## 假設與 HKJC 參考

用戶要求先構造完整速度訊號再比較，特別係逐駒 total−L800 嘅頭段速度。
已讀 AU/HKJC Auto、model-regression-gate、leakage-audit、feature-ablation、
experiment-review，以及 EXP-20260831-07、EXP-20260927-02、EXP-20261013-10/11、
EXP-20261015-03。今次新增嘅係真逐駒 GPS：唔重做頭馬／名次代理。

HKJC `get_standard_time` 用 venue/surface × distance × class；Facts 將完成時間
對標準，再作步速修正。現行 `raw_dev − (estimated winner_time − standard)`
代數上等於 estimated beaten-margin seconds；唔可以聲稱已獨立量到真頭段步速，
亦唔照搬香港權重、官方標準秒數或模型。

### 量 outcome 前嘅來源升級

官方 ZIP 其實係逐場 XML，包含 `Horses/HorseSummary/FinishTime`、分段、
TrackCondition（精確rating）、RailPosition、RaceName及horse code。擴至同一706
meeting來源嘅XML：用本駒FinishTime並要求同完整分段總和差≤0.05秒；唔用root嘅
race FinishTime。以XML條件取代Formguide broad going，class由官方race title辨識；
標準參考可以用全部官方完整field，唔再限Formguide覆蓋到嘅歷史頭馬。
環境模型加rating（ridge20）及venue×2m rail band（ridge40）；複雜移欄文字保留，
分格只係粗環境代理，唔當完整跑道幾何。呢個係來源驗證後、未跑candidate outcome
之前鎖定嘅修訂；六arm／gain／時間窗／判決規則不變。
索引其中 2026-03-08 Sunshine Coast Poly Track 只有CSV、冇ZIP；明文記錄為
CSV-only，保留完整逐駒split資料但rating／rail未知，唔靜靜剔除或虛構精確條件。

## 鎖定構造（未看本次 candidate outcome 前）

- 本駒 full time = 完整互不重疊 GPS splits 總和；L800 = 最後四個200m split 總和。
  early = full−L800；early distance = actual distance−800。≤800m冇頭段訊號。
  split不足／零值／當日或未來／試閘／join衝突全部缺值，唔估。
- 標準擬合單位係每場 GPS field median（最少3匹完整追蹤），唔用頭馬時間。
  每個 prediction date D 只 fit `<D`。response 用 log(seconds/metre)，分別 fit
  total 同 early；全局 log(distance) 二次項＋venue/surface＋地況族＋
  venue×400m-distance-band＋venue×going＋class nuisance。ridge pseudo-count
  依次 20／40／30／40／20；intercept弱懲罰，3次Huber IRLS（3% log-time）。
  class用MDN/BM≤64/BM≤78/BM高/CL≤3/CL高/Group/Open/unknown；最終速度標準
  固定共同class reference，唔將「高班同樣時間」扣分；class只協助估環境效應。
- 歷史場地當日 variant：同一舊賽日／場地至少3場其他賽事嘅 class-adjusted
  median residual；leave-one-race-out、n/(n+3) shrink、clip ±5% log-time。
  唔用 target 當日其他場，更唔用 target 賽果。
- A context_total：相對上述標準及variant嘅逐駒 full-time 速度。
- B early800：相對 early 標準及variant嘅逐駒頭段速度。
- C tempo_correction：past-only、within-horse fixed-effect ridge 回歸，估 race-field
  early pace（及平方）同個體 full residual嘅關係；剔走馬匹固定能力影響，最少
  100 repeat-horse observations。用實測field early，唔用頭馬速度；係統計修正假設，
  唔冒充已識別因果／蝕位／跑線。
- 每匹 target 馬只用最近6條可匹配正式賽往績；90日half-life；途程轉移權重
  exp(−abs(log(old_distance/current_distance))/.25)；地況族不同×.5（未知不亂配）。
  weighted average後每個分量場內標準化、clip z±3，**再**乘
  sum(weight)/(sum(weight)+3) shrink。單仗保留但低信心，缺值0。
  shrink必須放喺z之後，避免全場稀疏時又被z重新放大；呢個係量outcome之前嘅設計核對。
- 六個固定arm：A、B、C、A+B、A+C、A+B+C；組合取分量平均，避免只因幅度較大。
  A+C係完整步速修正時間，A+B係全程＋頭段，最後一個係三者。階梯做消融。

## 評估鎖定

沿用 AU v3 contract，唔改把尺。乾淨段 2026-08-05—10-14；前30個完整賽日只做
warmup，之後每7賽日一個OOS窗。所有標準／馬匹特徵都按各自target date建立。
gain {0,.25,.5,1,2}只用該窗之前訓練日期，Gold及Good點估計不回歸、五個時間fold
至少四fold place objective不輸嘅非零gain取中位數；冇合格就0，不argmax。
train目標place=(Gold,Good,Pass,Top3 precision)。六arm都報，唔按OOS揀贏家。

先報A/B/C feature coverage、場內判別力及與現有pace/form/PQ重疊，再作排名比較。
Gold／Good／Pass、五個已登記ranking metric、六時間塊、field-size四桶、going、
venue、distance及career-start分層；paired date bootstrap2000、seed7，六arm×兩primary
一個Holm家族。A/A零差；未有power budget/MDE證據唔判RANKING_WIN。

來源今天回補，當時publication/capture未認證，繼承PIT FLAG；所有已睇過日期只可作
historical diagnostic，唔冒充未開forward holdout，唔解封既有speed shadow terminal。
即使正面都唔直接部署；獨立保存研究程式及證據。

## 實作與來源驗證

研究入口 `scratch/au_contextual_gps_speed_20261015.py`；來源／數學／PIT測試
`scratch/test_au_contextual_gps_speed_20261015.py`。全部模型／權重／解說生成器／
dashboard／scheduler／ledger原封不動，唔將研究候選裝入production。

- 706 meeting sources：705個ZIP/XML（28,166,817 bytes），一個CSV-only；原始706 CSV
  13,319,167 bytes。每個source有URL及SHA256，唔靠今日再抓同一URL假設內容不變。
- 5,431場來源，5,256場有≥3匹完整GPS；49,613條完整逐駒FinishTime＋L800。
  175場不完整／短於等於800m／試閘等不合規；5,047場有精確rating。
- 首個target 08-05只用之前4,695場；最後target 10-14只用之前5,250場。
  其餘6場source係10-14本身，所以唔會入當日features。
- Swanfels，2026-10-08 Ipswich R1：total101.81s−L800 47.35s＝early54.46s；
  對應賽程標記距離1666−800＝866m，early15.9016m/s。XML亦有實際走線距離，
  今次未將多跑米數／跑線當額外加分，唔將標記距離冒充GPS實際走線距離。
- 原CSV一些header用YYYYMMDD而唔係YYYY-MM-DD，已按原明確日期正規化；
  XML source則直接讀EventDate。header race FinishTime完全冇入本駒分數。
- 早期CSV-only prototype只作source預檢；candidate outcome首次量度用嘅係以上
  已鎖定XML版。之後只補diagnostic AUC CI及清未用程式，重跑確認所有gain、排名
  及paired effects完全一樣，冇按OOS結果改構造。

## 樣本與覆蓋

同一baseline dump，完整清潔日期2,496場／24,085 runner appearances／71日。
前30日（1,003場）warmup；真正逐窗OOS係
**2026-09-04—2026-10-14，1,493場／41個完整賽日**。
每步七賽日，只用之前資料揀gain；六窗。

全段A/B/C各5,431 appearances有值；OOS各3,145 appearances。
OOS有411場可以喺有GPS嘅馬之間同時比較上名與未上名馬。唔將冇GPS嘅中性值
混入feature判別力；排名比較仍保留全部同一份1,493場及原runner roster。

## 先問有冇訊號（diagnostic，唔係model improvement）

| 特徵 | OOS場內AUC（pair-weighted） | 賽日cluster 95% CI | ρ現有pace | ρform | ρPQ |
|---|---:|---|---:|---:|---:|
| A 修正全程速度 | **0.60725** | [0.58479,0.63060] | +0.204 | +0.317 | +0.365 |
| B total−L800頭段速度 | **0.54085** | [0.52323,0.55950] | −0.096 | +0.148 | +0.073 |
| C 步速修正項 | 0.48691 | [0.46889,0.50603] | +0.128 | −0.046 | −0.010 |

相關係每場先z後合併嘅Pearson，唔係全池把場次難易度當馬匹能力。
confidence shrink後實際加分訊號AUC依次0.60704／0.54315／0.48398。
以上CI係raw feature診斷、未作多重比較；唔用嚟判primary或promotion。
**頭段有辨識訊號，而且同現有pace重疊少；但唔等於應該直接加進ability。**

唔可以將呢個AUC同EXP-03嘅0.5666直接相減報「改善」：兩次覆蓋、aggregate及AUC
權重定義唔一樣。今次係獨立、完整日期向前嘅診斷。

## 真正排名比較

| pipeline | Gold | Good位置 | Pass | 相對baseline |
|---|---:|---:|---:|---|
| 現役baseline | 288 | 393 | 749 | — |
| A 修正全程速度 | **289** | **396** | **752** | +1／+3／+3 |
| B 頭段 | 288 | 393 | 749 | 所有窗冇合格gain，fallback0 |
| C 步速修正 | 288 | 393 | 749 | 所有窗冇合格gain，fallback0 |
| A+B | 288 | 393 | 749 | 所有窗冇合格gain，fallback0 |
| A+C 完整步速修正 | 289 | 392 | 753 | +1／−1／+4 |
| A+B+C | 288 | 393 | 749 | 所有窗冇合格gain，fallback0 |

A六窗gain：2、2、1.125、1.125、1、1；A+C固定由每窗訓練選出1。
中位gain可以唔喺原grid（例如.25及2嘅中位係1.125），唔係argmax。
其他arm係訓練安全條件未放行，**唔可以將OOS零差當作B/C冇訊號或程式未接通**。
所有component feature已非空、有場內散佈；零差原因係明確gain0。

### A完整效果與不確定性

| metric | 差 | 賽日cluster95% CI |
|---|---:|---|
| Gold | +0.0670pp | [−0.1435,+0.3026]pp |
| Good位置 | +0.2009pp | [−0.1317,+0.5583]pp |
| Top3 capture@5 | +0.000447 | [−0.000664,+0.001495] |
| 實際前三平均模型名次（低較好） | −0.002009 | [−0.005472,+0.001108] |
| NDCG@5 | +0.000956 | [+0.000042,+0.002022] |
| Top5 pairwise AUC | +0.000704 | [+0.000039,+0.001411] |

primary六arm×兩指標Holm後全部p=1；唔判PRIMARY_WIN。
ranking個別未校正CI有正面，但冇power budget/MDE及完整多重比較通關證據，
**唔判RANKING_WIN**。來源availability FLAG亦獨立阻止promotion。

A六時間塊Gold Δ pp：−0.433、+0.364、0、+0.420、0、0；
Good：+0.433、+0.727、0、−0.420、+0.366、0。兩primary各5/6非負，仍唔代表顯著。

### A分層（變化場數，描述性）

| field | N | Gold Δ | Good Δ | Pass Δ |
|---|---:|---:|---:|---:|
| ≤8 | 452 | +2 | +1 | +2 |
| 9–10 | 514 | −1 | +1 | +2 |
| 11–12 | 373 | 0 | 0 | 0 |
| 13+ | 154 | 0 | +1 | −1 |

Good地860場：+2／0／+3；Soft578場：−1／+3／0；Heavy40場、Synthetic15場零差。
短途770場：0／0／+3；中距離548場：+1／+3／0；長途175場零差。
場內全馬≥6starts627場：+1／+2／+4；有0–5starts馬866場：0／+1／−1。
冇按以上cohort重新揀門檻或權重；完整venue等分層保存在artifact JSON。

消融比較係各自訓練gain嘅pipeline：A→A+C令Good少4場；A→A+B則退回baseline。
因gain及fallback亦有改變，唔將佢冒充「固定相同係數下B/C嘅純因果邊際」。
可以支持保留較簡單A作候選，但唔支持現在把B/C加進live排名。

## 判決

**A：PROMISING DIAGNOSTIC／NEEDS MORE TESTING。** 已有獨立速度訊號，加入現有
模型嘅後段點估計亦正面，但Gold/Good CI跨零，多重比較未過。
**B：有raw early-speed訊號，但冇訓練合格加分幅度。** 唔強行入ability；亦唔判頭段無用。
**C及組合：未支持採用。** A+C嘅Good點估計回歸；唔因Pass升就蓋過primary。

machine promotion decision全部 `REJECT/leakage_audit_failed`，因歷史來源availability
未認證，唔將FLAG改成PASS。未來有賽前凍結source／prediction嘅獨立日期先可以
做最後確認；今次冇解封或改既有speed shadow terminal，亦冇新增背景排程。
**live保持不變；研究分支保存。**

## 驗證及重現

11個新增測試＋原6個來源測試PASS：逐駒FinishTime/root header分離、L800拆法、
≤800m無頭段、legacy日期、source缺值、共同class reference、future-source invariance、
leave-one-race-out variant、距離轉移、低證據shrink及target-date排除。
A/A所有metric零差；fast place metrics同canonical完全一致；baseline合成誤差<0.00011。
quick及full repo checks另存log；無golden record／calibrate／模型說明改動。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_contextual_gps_speed_20261015.py fetch --cache /private/tmp/au-context-speed-official --prior <EXP03-artifact>/official
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_contextual_gps_speed_20261015.py fetch-xml --cache /private/tmp/au-context-speed-official
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 scratch/au_contextual_gps_speed_20261015.py build --cache /private/tmp/au-context-speed-official --root "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing" --baseline <EXP03-artifact>/au-runner-time-baseline.json --out /private/tmp/au-context-speed-features-xml.json
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 scratch/au_contextual_gps_speed_20261015.py evaluate --features /private/tmp/au-context-speed-features-xml.json --out /private/tmp/au-context-speed-results-final.json
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -m unittest discover -s scratch -p test_au_contextual_gps_speed_20261015.py -v
```

原ZIP/XML、CSV、manifest、features、逐窗predictions、全部分層／CI及固定baseline
保存喺本次Codex artifact `AU-contextual-speed-research/`。repo只收濃縮記錄及程式。
[官方來源索引](https://www.racingqueensland.com.au/industry/thoroughbred/thoroughbred-sectionals)。
