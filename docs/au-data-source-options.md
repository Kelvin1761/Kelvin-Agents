# AU 額外數據源選項（2026-08-26 調研）

Kelvin 嘅條件：**免費**，而且**可以同 Sportsbet 兩個來源並存**。

## 背景：要搵嘅係咩

2026-08-26 量到 AU 現有特徵集已經飽和（EXP-20260826-07）：

* GBM 餵同一批 18 個 leaf，場內 AUC 0.6675 **輸**現行線性組合 0.6774
* 訊號加法唔成立（class +0.0026、sectional +0.0017，夾埋只有 +0.0027）
* 市場（賽前 WinOdds）AUC 0.7332 vs 我哋 0.6665，但最佳混合 **w=0.0**

所以：**唔係要多啲由現有數據推導嘅 leaf，係要外部新資訊。**
而且「市場數據」呢一類已經證實幫唔到排名 —— 加任何模型比重都令 AUC 跌。

## 調研結果

| 來源 | 免費？ | 帶咩 | 對排名有冇用 |
|---|---|---|---|
| **Punting Form**（sectional） | ❌ Starter $59/月起，sectional 要 Professional | **逐匹馬真段速**：全程時間、閘到 L600、L600/400/200/100 分段、**每個分段點嘅內欄距離同走位** | ✅ 唯一一個**唔係市場訊號**嘅新資訊；直接修 `pace_figure` 嘅根本缺陷（race-level → per-horse）|
| **Betfair Automation Hub CSV** | ✅ 免費（要 Betfair 戶口，free tier 要「購買」0 元）| 交易所價，1 分鐘間隔、last traded price、**冇成交量**。AU/NZ 純種馬 2020–2026 | ❌ 市場訊號 —— 已證實模型加落去貢獻為零 |
| **Punting Form 免費層** | ✅ | 基本 form guide | ❌ 同 Sportsbet 重複 |
| **Daily Sectionals / sectionaltimes.com.au** | 未確認 | 分段 | 待查 |

## 結論

**免費嘅嗰啲全部係市場數據，而市場數據幫唔到排名（已實測）。**
唯一一個能夠帶來非市場新資訊嘅係 Punting Form 嘅逐匹馬分段，而佢**要錢**。

呢個結論唔係「冇嘢可以做」，係「免費呢個條件同『要新資訊』呢個需求，
喺澳洲賽馬數據市場入面暫時互相排斥」。

## 但免費嗰啲仍然有一個唔同嘅用途

Betfair 交易所價 vs Sportsbet 固定盤 = **價值偵測**，唔係模型輸入。
交易所冇莊家抽水扭曲，所以「Sportsbet 位賠明顯高過 Betfair 引伸位賠」
就係一個真嘅 value 訊號。呢個唔會令模型排名變準，但會令**同一個排名之下
落注嘅期望值變好** —— 而 [[au-takeout-beats-the-edge]] 嗰個結論
（racenet SP 抽水 19.8% 食晒模型 9–14pp 優勢）正正就係死喺呢度。

⚠️ 呢條係落注層，唔係模型層。要做就要當一個獨立議題論證，
唔可以攞佢嘅回測數字當「模型改善」。

## 建議次序

1. **想改善排名** → 要 Punting Form Professional（付費）。冇免費替代。
2. **想改善落注期望值** → Betfair 免費 CSV 做價值偵測，唔掂模型。
3. **想乜都唔使付費又要改善** → 唯一剩返嘅路係等語料儲厚，
   跑返 `au_retest_watch.py` 排住嗰兩個候選。

## 來源

* <https://docs.puntingform.com.au/docs/sectional-data>
* <https://puntingform.com.au/pricing>
* <https://betfair-datascientists.github.io/data/dataListing/>
* <https://betfair-datascientists.github.io/data/usingHistoricDataSite/>
