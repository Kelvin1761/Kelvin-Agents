# Tennis 盈利改善研究：第一輪（2026-10-27）

**研究已啟動，完成兩項固定對照；今輪未找到可部署嘅盈利提升。正式模型、風險折扣、權重及注碼全部未改。**

## 1. 短賠熱門唔係現成解法

沿用之前未夠樣本嘅假設：所選球員最早賠率 <=1.6、600最低樣本、原2026-07-15時間分界；唔掃新門檻。

完整賽前一致結果語料有3,774場，排除282場首價時間不足／賽後，得到3,492個獨立fixture。短賠群體只得269場，低於600。模型LL 0.673798，市場0.631212；模型較差嘅配對差 +0.042586，95% CI [+0.016498,+0.070020]。呢啲係legacy診斷，不足以升級。

同一語料，原卡保存 `decision=BET`、每單1u紙上比較：

| | 原卡 BET | 再收窄 odds<=1.6 |
|---|---:|---:|
| 筆數 | 257 | 35 |
| P/L | −43.037u | −8.602u |
| ROI | −16.75% | −24.58% |
| ROI 95% CI | [−30.24%,−2.67%] | [−48.37%,−1.84%] |

少下注令總損失變細，但每注回報更差；配對P/L差亦未能排除噪音。**唔部署短賠收窄規則。** [完整記錄](../experiments/EXP-20261027-05-tennis-profit-feasibility.md)

## 2. 移除 nudges 冇可靠改善

直接用當時保存嘅 Elo base、各分項、選擇方向及 segment-risk discount；唔用今日資料重算舊模型。

第一版只重建 raw combiner，漏咗已保存嘅風險折扣層，只對到326場。已明示量度修正、保留原始輸出，完成parity測試，再量第二版。第二版同一1702場重現最終保存機率，誤差 <=1e-6；冇改動任何折扣參數。

| 同一1702場，保存選擇方向，EV>0平注1u | 原模型 | 全部nudges關掉 |
|---|---:|---:|
| LL | 0.661209 | 0.661847 |
| Brier | 0.233838 | 0.234119 |
| 注單 | 1393 | 1366 |
| 紙上 ROI | −19.67% | −20.76% |

LL差 +0.000638，95% CI [−0.001381,+0.002606]。同群市場LL 0.568570；關掉修正層冇填補差距。另有9個逐項消融，無一項有通過Holm修正嘅改善證據，冇揀點估計最好一項再調參。

**REJECT 本次移除nudges候選。** 呢個唔證明每個nudge都有用；全部係dev-only，唔係untouched holdout。第二表用EV>0、第一表用原卡BET，兩表各自保持同群體比較。 [完整消融](../experiments/EXP-20261027-06-tennis-stored-nudge-ablation.md)

## 3. 資料同判讀界線

- Central corpus audit通過，4份登記snapshot完整性及watermark核對通過；冇以archive替換live DB。
- 所有研究需要嘅8個table／全部rows由同一唯讀transaction投影，223MB，冇按outcome縮語料。SHA256：`b4fa1d2af45480f567e5e36a47bb52a2f1b7adaf15f6111fd35db3286d910aa7`。
- 原始保存預測有15,681行；唔等於15,681個獨立、可下注及未看過結果嘅場次。
- 現存實際報價只有Sportsbet，另外3行mock不入研究。未有獨立銳價；本地已記錄實盤prop單為0，不能申報實盤回報。
- 3,492場全部欠新制fixture frozen identity。opening quote同forecast時間相符只係必要條件，唔係身份／成交完整證明。今次冇倒填定價證據，唔將legacy數字當修正後新模型成績。
- 全部結果已被其他審計看過，所以唔當新untouched holdout；原有600 floor、power、校準、CLV、ROI及分層閘全部保留。
- 16組完整檢查全過（Tennis858）；新增研究防污染測試12項另行全過。正式source無改動。

## 4. 下一步值得投入邊度

今輪唔支持繼續掃賠率門檻或刪修正層。先累積修復後可追溯嘅賽前紀錄，並評估一個獨立參考價來源嘅可行性，再預先登記其市場相對增量。額外來源唔代表自動有edge，唔用假想公平價冒充可成交價。

接入時要分開reference同Sportsbet執行價，記錄兩邊實際觀察時間、事件／球員身份、盤口結算規則、可成交back/lay、深度及費用，避免將延遲、midpoint或走地價當賽前可成交價。

已核對官方接入限制（2026-10-27）：Pinnacle公開API已自2025-07-23關閉一般公眾接入，唔假設可以直接免費抓；Betfair Delayed key提供1–180秒可變延遲，不能直接當同步即時價格。見 [Pinnacle官方文件](https://github.com/pinnacleapi/pinnacleapi-documentation/blob/master/README.md)、[Betfair官方key說明](https://support.developer.betfair.com/hc/en-us/articles/360009638032-When-should-I-use-the-Delayed-or-Live-Application-Key)。本輪冇購買、開通API或送出任何投注。

## 保存及重現

研究工具只保存研究分支 `codex-tennis-profit-research-20261027`；失敗候選程式唔自動合併main。主分支只保存本報告、實驗記錄及濃縮JSON。

外置證據：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-profit-20261027/`，包括完整投影、逐場配對、v1／v2輸出、原始事前protocol內容／hash／UTC lock及artifact manifest。研究版本及重跑指令附於兩份實驗記錄。
