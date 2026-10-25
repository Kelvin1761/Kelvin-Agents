# EXP-20261025-01 NBA 市場殘差與動態分鐘／每分鐘產出消融

基準commit：619b71a3ae7847aa66adb813de3282313804177f。新研究不改正式機率／選腿／EV／SGM建構。

## 已搜索與新假設

EXP-20261021-02～08、20261022-03、20261023-06、20261024-03：靜態分鐘、L5、季初乘數及未勝市場RF已試，唔原樣重試。新假設係「對齊同一批歷史賽事嘅短期分鐘變化／每分鐘產出變化，能否喺真實盤線上增加市場＋L10以外資訊」。不引入事後角色／首發資料，分鐘變化只係歷史角色proxy，唔聲稱知道今場分鐘。

## 資料與時間界線

唯讀來源：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023/verified_dataset_v2/dataset.csv`，SHA256 `16b378cd914d1d684609760eb0edbeb6d4648d52a7b5552faba10fd45c3a7e0d`。重用現有 `load_and_prepare` 對獨立賽前證據、原始盤線／特徵、標籤及source hash驗證。MIN亦額外驗證日期對齊／newest-first／嚴格早於目標US日。

固定原24日期切法：前19日dev，尾5日（2026-05-17、06-03、06-05、06-08、06-10）已見terminal完全不評估／不擇參。dev用既有TimeSeriesSplit(n_splits=5)按完整日期前推。所有歷史結果曾看過，五fold只叫歷史OOS診斷，不能作確認；新的forward確認協議需在採用前另定。

現役C曾擬合部分歷史窗，故只作明標描述性背景，不作本輪採用裁判。市場1/price含vig及原始L10作固定baseline；B係每fold重新擬合市場＋L10，避免把已見C當乾淨OOS基準。

## 固定四組（產生任何候選預測前登記）

- B：stat截距＋logit(clip(1/price,.02,.98))＋logit(clip(L10 hit,.05,.95))。
- B+M：加 M＝clip(mean(MIN前3)/mean(MIN前10)−1,−1,1)。
- B+R：加 R＝clip((sum(stat前3)/sum(MIN前3))/(sum(stat前10)/sum(MIN前10))−1,−1,1)。
- B+M+R：兩項一起，檢查邊際貢獻；不加交互項、網格或其他模型。

所有模型用同一complete-case cohort：至少5條日期對齊歷史，MIN及stat同長、非負有限，分母>0。新日期／錯序／MIN==0而stat>0列不安全；零分鐘且stat0可留在對齊序列，不能假造有出場。資料不足留原因，不用標籤決定特徵資格。

模型：固定ridge logistic，市場斜率懲罰中心1，其餘斜率0；stat截距不懲罰；目標weighted平均log-loss＋0.01/2×斜率平方偏差。每event總權重相同，每event內player/stat unit相同，每unit梯級行相同；只用train計算新特徵平均／SD，SD=0記為死特徵並輸出0。scipy L-BFGS-B固定maxiter2000、ftol1e-12；不做模型／正則搜索。基準與候選都在同一fold重新fit。

## 指標與判決

沿用現有 `_metrics`，主Brier、次log-loss；另報equal-game／unit-weighted Brier、整體及p≥.7/.8校準、逐stat、每fold、同球員梯級機率倒序數（診斷，不修正以救結果）。按US賽日cluster bootstrap 2000次／seed20261025，Δ=候選−B，並同市場比較。完整合併消融需比較BM−B、BR−B、BMR−BM／BR；不因argmax自動揀模型。

值得前瞻嘅診斷訊號（不是採用）：相對B之ΔBrier CI上界<0、log-loss不差、至少4/5 fold點估計不差、相對市場CI上界≤0；同時報原始結果，不用換窗／門檻救候選。多重比較只作診斷；未另定forward確認功效及調整前一律promotion_allowed=false。

功效限制：15個左右OOS日期，並非數千個獨立盤口。假設日差SD .01，要以雙邊5%／80%power辨識ΔBrier .002，約需196個獨立日；此係示例而非已估實際SD。今輪只做可行性，不能確認細收益。沒有歷史真實SGM價，唔報SGM ROI或盈利改善；新增正EV單腿比例只作診斷。

## 保存／重現

外置輸出：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-residual-study-20261025/`；不抄完整語料。固定協議hash先保存，再跑。研究係數只留該目錄，deployment_eligible=false。未確認／失敗候選只保存研究分支，不合併正式模型。

## 結果

固定消融已完成；沒有候選達到預先登記嘅前瞻診斷條件，沒有晉升。盈利仍屬 NEEDS MORE TESTING。

## 歷史診斷結果

8,286個已核實標籤，8,280個有安全對齊MIN／stat序列，6個因零分母排除；182個DNP／缺標籤priced rows保持未標籤，唔當落空。初步掃描曾漏掉GS／NO等球隊代碼別名，誤將2,061列計作歷史不足；正式constructor在跑前已統一canonical team，所有模型同一cohort。此係前置掃描修正，不是看結果後改資格。

只評估dev內15個OOS日／32場／5,299行；五個已見terminal冇評估。所有數字皆歷史診斷，C含訓練重疊只作背景。

| 模型 | Brier（低較好） | log-loss | ΔBrier vs B［按日95% CI］ | 不差過B嘅fold |
|---|---:|---:|---|---:|
| 市場＋L10基準B | 0.169210 | 0.511853 | — | — |
| B＋分鐘趨勢 | 0.169386 | 0.512207 | +0.000175 [+0.000007, +0.000387] | 1/5 |
| B＋每分鐘產出趨勢 | 0.169071 | 0.511595 | -0.000140 [-0.000922, +0.000841] | 4/5 |
| B＋兩項 | 0.169256 | 0.511967 | +0.000045 [-0.000715, +0.000990] | 3/5 |

市場原價Brier 0.171728；原始L10 0.181795；現役C背景0.168417（歷史訓練有重疊，不能作獨立勝負判決）。四個擬合模型相對市場嘅CI皆跨0。全部梯級機率倒序數為0。

- 分鐘趨勢BM點估計比B差，只1/5 fold不差；原始CI偏正，但多重比較未調整，唔宣稱確認性傷害。
- 產出趨勢BR只有−0.000140名義Brier差，CI [−0.000922,+0.000841]；4/5 fold不差，但未證實贏B或市場。equal-game/unit加權Brier反而0.179110對B0.178793，唔將微小表面差當穩健增益。
- 合併BMR冇增益；相對BR加入分鐘項嘅名義ΔBrier +0.000185，未有理由保留額外複雜度。
- BR估計正EV單腿比例17.9%對B16.0%，但呢個唔係SGM／實際出手，亦唔係盈利。不能因標示更多+EV就採用。

**決定：沒有候選晉升。** 三個arm都未達預先登記「值得前瞻診斷」條件；不改λ、窗口、特徵或候選去救結果。NEEDS MORE TESTING只指未能下盈利／確認性結論，唔係允許上線。

本輪係數／程式只保存研究分支及外置證據；不合併main，不改現役C／EV門檻／dashboard／B0/B1/B2。冇真實SGM歷史組合價，唔計SGM ROI；沒有盈利改善聲稱。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 NBA_WC_PROB_LAYER=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
python3 .agents/scripts/nba_ml/train_nba_xgboost.py --residual-study \
  --dataset '/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-remediation-20261023/verified_dataset_v2/dataset.csv' \
  --output-dir '<new-external-output-directory>' --skip-shap
```

協議、原始OOS預測、逐fold模型／scaler／截止日期、metrics及source hash：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-residual-study-20261025/`。輕量報告／測試證據另存`/Users/imac/WongChoiData/NBA_Research/2026-10-25-market-residual-study/`。

## 檢查與限制

- Leakage／PIT輸入：PASS（既有獨立pre-tip來源及label hash重建，加MIN／stat日期對齊、target/future拒絕、只用train計scaler測試）。
- C歷史重疊：FLAG，明標context-only，不作採用裁判；舊terminal排除。沒有新確認集，故不能晉升。
- 功效／人口：FLAG，只有15個OOS日，全部季後賽／附加賽；冇季初盈利證據。相鄰日期亦可能相關。
- Golden／data contract：正式評分、NBA live機率、AU/HKJC golden及資料合約均冇修改；研究缺值排除，唔填成有訊號。
- 不報SGM ROI、Kelly、注碼或正式推薦。更多估計正EV標籤不作勝出條件。
- 源碼／規則hash在真實fit前凍結，結果後未改模型；完整測試及保存結果見同一證據目錄Final_Verification.json。

工程驗證：研究 focused 15 passed；CLI ROI＋banker audit 17 passed；quick及完整 `./檢查.sh` 全部通過（NBA 518 passed）。首次受限sandbox完整檢查嘅4個失敗係 `ps` 權限限制；以正常權限重跑 relocation 13 passed，再跑完整檢查全部通過，沒有跳過或改弱測試。
