# EXP-20261013-08 — HKJC 逐場權重事後診斷

預先登記：2026-10-13。只做研究，唔產出可部署權重，唔改 live engine。

- Baseline HEAD: `0116c740330db7f02f9d04d2884e211b1d494517`；root 有大量其他工作未 commit，必須記錄實際 scoring source hash。
- Dataset: `scratch/hkjc_race_weight_oracle_20261013/dataset.csv`，4,500 horse rows / 362 races。現行獨立 RacingEngine 重播，並非完整 meeting orchestrator（未重施 SIP）。存檔 ranking 另報差異，唔混成 published prediction KPI。
- 唯一日期隔離：以 EXP-20260928-06 原來截至 2026-09-27 的日期集合、尾15%日期，保守隔離 2026-09-09 起所有日期。呢個係研究 quarantine，唔係重定正式 promotion split。只診斷更早嘅日期；terminal 不擬合、不報 KPI。
- Miss 定義：canonical Gold（實際前三全部落模型Top4）同 Good（模型Top2都上名）都唔達標。額外報 winner rank、top3 capture，唔改 primary。
- 七維非負、和1。local 每維 baseline ±0.05；positive [0,1]；signed [-1,1] 只作反訊號診斷。
- 全場排序 logistic objective、固定 temperature=6、L2=0.02，用 local/positive 兩個範圍；唔搜尋超參數。
- 同時 Gold+Good 可行性：枚舉前三入Top2嘅pair，以及Top4唯一容許嘅外圍馬；逐個 linear program 最小化 L1 權重改動，取全局最小可行解。margin=0.01分；唔可行只限上述線性模型／凍結修正／margin。
- 初出馬分數鎖定；其餘以 baseline ability 減 matrix 加權作固定 residual（包括顯示尺與四捨五入）。重播 score 必須逐行一致。全維使用現行原始matrix，不用顯示維度分。
- 按成功／失手／positive亦救唔返，報 dimension spread、leaf neutral rate、podium relative-rank；venue/surface/field cohort。
- 逐場oracle係事後上限，唔係預測績效。資料來源／先驗／歷史曾賽後重算，PIT provenance FLAG；任何方向都只係待驗證假設。賠率、incident、賽後sectional、歷史CSV priors唔入 optimizer。
- 完成後保存逐場結果、權重witness、hash、來源差異及報告；唔更新golden／calibration，因為冇改評分。

診斷語義補充（首輪結果後、未作候選）：同時 Gold+Good 比原來 miss 定義更嚴，所以額外分開枚舉 Gold-only、Good-only；以「任何一項都救唔返」先稱為達標不可救。聯合witness有解時可重用作單項可行性證明，但唔聲稱佢係單項最小L1。完整全場順序另用pairwise LP驗可行性。呢啲都係事後診斷，唔改正式KPI或promotion gate。

## 實測結果

- 272場有效development races（274場中2場label／field不合格）；197場重播失手。Gold38、Good61。
- 單項達標（Gold OR Good）：local救54／197、positive救152／197、signed救196／197。
- 聯合Gold AND Good：local12、positive77、signed158；唔混用兩個目標。
- 45場positive單項亦無解，44場signed先有解。只有5／272場positive可以完整複製全場排序。
- 77場positive聯合witness：56場減shape；但舊EXP-20260928-06嘅樣本外減shape候選已失敗，今次唔係promotion建議。
- 70場段速全場常數，但失手／達標比例相近，唔能單靠缺段速解釋失手。
- Raw Logic核對：4場／9匹明文「初出」但冇engine debut flags；3場失手、2場positive無解。需對racecard/profile確認，唔當已證實live bug。
- 存檔206場失手；與重播失手重疊176場、30場重播達標、21場新失手。271/272場全排序有變，故正式published model KPI未重播一致。
- 任何oracle權重只限已知賽果事後解釋。冇候選／冇績效改善證據／冇模型改動。

完整報告：`docs/audits/hkjc-race-weight-oracle-20261013/REPORT.md`。
逐場：同目錄 `results.json`／`race_diagnostics.csv`／`patterns.json`／`debut_source_flags.json`。
Frozen dataset：`scratch/hkjc_race_weight_oracle_20261013/dataset.csv`，4MB；命令同SHA256見report／results。
執行前內置可用22GiB，無大型語料複本。source SHA256執行後全部保持一致。

## 驗證

8個獨立oracle tests PASS（LP可行性／反訊號／Gold-vs-Good／逐行baseline／初出鎖定／日期quarantine）。
`./檢查.sh --quick` PASS（最終修改後重跑）；AU／HKJC golden保持原樣。
首次完整檢查12個HKJC排程測試因sandbox禁止寫production log而失敗；冇改排程code，正常權限重跑該suite70／70 PASS。

正常權限完整 `./檢查.sh` 最終exit0，所有14個suite PASS。完整日誌已附 `docs/audits/hkjc-race-weight-oracle-20261013/full_check.log`。
