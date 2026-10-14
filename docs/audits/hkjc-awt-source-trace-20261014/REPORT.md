# HKJC 18場泥地來源追蹤 — 2026-10-14

**18場全部核查，搵到三個可獨立重現嘅資料／解析問題。呢輪唔係權重搜索，冇使用當場賽果調參，亦冇聲稱模型表現改善。**

## 1. AWT表面喺formguide解析時掉失

原始往績：`沙田 "AWT" 1800 好`。
現行parser輸出：`venue='沙田', rail='AWT'`。
但同表面性能同同場同程統計只用venue判斷，變咗草地。profile補充亦唔一定救到：同日期recent formguide優先，profile同日會被去重。

213個賽果對齊runner records中，149個有呢類賽前往績；共499次泥地往績列全部掉失表面（係跨target races嘅row usages，唔係499個獨立賽事）。

使用相同原formguide、相同日期cutoff、現行±200m／730日／365日半衰／4場中性收縮，單獨修正parser：

| 項目 | 修正前 | 隔離修正後 |
|---|---:|---:|
| 可由formguide重建本地泥地有效樣本嘅runner records | 0/213 | 138/213 |
| 泥地target score有變嘅runner records | — | 136/213 |

呢個只用formguide近期往績，**冇加入profile、冇重新scrape、唔係完整歷史覆蓋**。因此138係呢條來源路徑嘅覆蓋，唔可以同原stored訊號18直接當同一份baseline比較。

修正：`candidate_preserve_awt_surface.patch`，只喺quoted rail已明確AWT時保留canonical表面。草地fixture逐欄完全相同。

## 2. 場地有效樣本攞咗第一個草地數字

現行engine用`今場=.*?有效樣本`搜尋，會跨過分隔符，攞第一項沙田草地樣本。

真實例：

- 今場=沙田AWT 60.3分
- 沙田草地：有效樣本4.0
- 跑馬地：有效樣本0.7
- 沙田AWT：有效樣本0.7

舊reader報4.0，正確應係0.7。分數60.3本身未讀錯。

32個有stored surface訊號嘅紀錄中，27個有效樣本值讀錯；正確泥地有效樣本>0係18個。

**更正上一輪報告：26/213只代表錯誤regex讀到嘅第一個草地樣本>0，唔係泥地coverage。呢個結論作廢，正確stored泥地coverage係18/213。**

修正：`candidate_target_surface_sample.patch`，用今場target名稱匹配同一個surface欄，缺target欄就0，唔借其他表面／海外樣本。

213個紀錄全部重播，metadata-only候選同baseline ability／matrix scores逐項一致。呢個係樣本量診斷修正，唔係排名改善。

## 3. Facts將AWT名稱截短，標準時間lookup亦會失去表面

`r.get('venue',...)[:4]`會將`沙田AWT`變`沙田AW`。最近往績、較舊往績表同完成時間趨勢共有三處。

`get_standard_time`只會喺venue包含完整AWT時選泥地標準；截短後會選沙田草地分支。所以只修第一個parser，未修renderer，仍然有下游身份掉失。

修正：`candidate_preserve_awt_rendering.patch`，三處改用既有canonical venue/surface normalizer。回歸fixture驗證輸出保留`沙田AWT`，完成時間lookup每次收到完整泥地名稱。

呢個會影響完成時間衍生輸入，需要完整、凍結profile來源嘅paired replay先評估。今次原formguide分段profile重算0個改變，**唔可以因此聲稱所有完成時間／段速衍生都冇影響**。

## 資料鏈實際情況

- 18場／213個matched runner records（唔係213匹獨立馬）。
- stored Facts surface line：32；stored Logic同樣32，全部來自2026-10-11三場。其餘15場Facts本身未帶呢條訊號，因此未見Facts有而Logic掉失嘅證據；唔可以叫181個紀錄係當前transport failure。
- 先修原始表面，再用既有formatter及現役Logic summary parser：213/213成功round-trip；泥地target有效樣本讀值符合formatter小數精度。逐馬candidate evidence保存喺trace.json，未寫返meeting檔。
- 原parser重讀海外PDF：11個runner有真正Dirt／Synthetic紀錄；符合既定PIT／距離條件、且本地AWT無樣本可fallback嘅只有2個。上一輪182個「foreign rows present」只係list非空，可能包括placeholder，唔係真正海外泥地coverage。

## 現有健康掃描對照

重用shared `racing_data_health.scan_meeting`，只讀原meeting，報告在health/。

- 前5個meetings通過；上述表面錯誤仍存在，代表結構／欄位presence檢查未覆蓋surface身份正確性。
- 2026-10-04：R9 racecard與Logic馬號集合有差異。
- 2026-10-11：scanner報formguide discovery/source-ready問題；R4 racecard與Logic馬號亦有差異。本追蹤能讀到該日三場賽績檔，故scanner的0/11不可直接當成檔案不存在。馬號差異須另查退出馬，未當成漏抽馬。

呢啲係meeting整體健康檢查，唔係只量18場泥地、唔係候選績效gate。

## 驗證／現役狀態

- 9個回歸測試PASS：AWT/HV/ST target樣本、missing fallback、quoted AWT保留、草地不變、同日排除、Facts標準時間lookup保留AWT。
- 原18場metadata-only候選重播：213/213 ability及matrix scores一致。
- 候選Facts→Logic：213/213往返成功。
- `./檢查.sh --quick`最終PASS；正常權限完整`./檢查.sh` PASS，14個suite全過。full_check.log附於本目錄。
- 冇修改現役Facts generator／engine、meeting資料、權重、golden、calibration、dashboard、排程；冇commit／push／activate。
- 三份patch針對本次trace所記source hash，只可套到相容版本；root同時有其他工作，唔可把整份dirty檔當本次改動。

## 評估限制同修正方向

今次用18場全部嘅**賽前輸入**診斷，原2026-09-09起quarantine保持。任何權重擬合／終局賽果調參都冇做。

parser同renderer係可獨立證明嘅surface身份錯誤；唔需要靠績效數字先承認係錯。但parser／renderer可能改同場同程同完成時間等入分訊號，仍要完成correctness-only paired replay、leakage審計同既定無顯著退步／cohort guardrail先可上線。

完整profile來源身份／PIT未驗證，故績效promotion仍FLAG。泥地資料唔係全無：重建出嘅138個近期泥地樣本係下一步嘅有效來源；應先保住呢條資料鏈，再研究泥地專用權重，唔係用血統／海外弱fallback代替漏失嘅本地實績。

## 重現

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_awt_source_trace.py --dataset scratch/hkjc_race_weight_oracle_20261013/dataset.csv --output docs/audits/hkjc-awt-source-trace-20261014
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s docs/experiments/patches -p test_hkjc_awt_source_trace.py -v
```

trace.json包含213個逐馬record、原始泥地往績例子、before/after field、候選transport文字、Logic／Facts／formguide／racecard／PDF／標準檔source SHA256。腳本驗證所有被記錄sources在執行中冇變；唔含當場results欄。


## 後續：已落實修正

2026-10-14用戶要求fix後，三份修正已套入工作目錄，正式測試與18場配對重播見[修正報告](../hkjc-awt-source-fix-20261014/REPORT.md)。本報告以上描述保留作修正前調查記錄。
