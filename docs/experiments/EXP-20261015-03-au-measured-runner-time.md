# EXP-20261015-03 — AU 逐駒實測全程時間

狀態：COMPLETED／NOT SHIPPED；固定用法 primary 回歸，來源時間戳 FLAG。

## 問題及預先鎖定設計

用戶要求測試本駒完賽時間，避免以頭馬時間代替本駒時間。基準
`7a962be562ecb0af461daa71114b1dddf66ec8cd`，包括六場後停用 trial performance。
已讀 EXP-20260831-07、EXP-20260927-02、EXP-20261013-09/10：舊 WinningTime
速度實驗其實包含「頭馬時間＋負馬位換算」，唔係逐駒實測。

先作來源驗證：全語料 Runner Time presence；Racing Queensland 官方公開 GPS
CSV 與 PDF 對照。CSV 每駒完整互不重疊分段總和係本駒 GPS 全程時間；CSV header
嘅 race time 唔准當本駒時間。資料只寫 research cache，唔改 archive、ledger、dashboard。

鎖定來源窗：官方索引中 2026-01-01 至 2026-10-14 嘅全部 CSV。
評估窗：現役引擎重算語料中 2026-08-05 至 2026-10-14；完整日期配對。
只有 target 前嘅正式賽事往績可入 feature；試閘全部排除，唔以結果檔補 feature。
來源 join 必須 horse＋venue＋date＋race＋distance 相符；未知／衝突唔補值。

固定三個 arm，全部用完全相同嘅有效往績：

1. measured：官方逐駒 GPS 分段總和。
2. winner_only：同場有追蹤記錄嘅第一名 GPS 時間（對照共享頭馬偏差）。
3. margin_estimate：同一頭馬 GPS 時間＋往績負馬位 × 2.4m／頭馬平均速度。

標準：只用 target 日期之前、已匹配到原 formguide 地況嘅官方賽事；同場去重，
場地×途程最少十場 median，地況差最少四十場 median；規格沿用先前研究，唔用
本次結果揀。每駒最少三條有效往績，取最好三次平均，按公里正規化，場內 z-score；
固定加 0.5 分 × z 入現役 ability，冇覆蓋 z=0。原權重及所有 leaf 保留。

輸出同一份語料嘅 baseline、三 arm、measured 相對兩個對照；Gold／Good／Pass、
預先登記 ranking 指標、六個完整時間塊、場數四桶、逐日 paired bootstrap 2000 次
seed=7。三 arm 同一多重比較家族。A/A 必須零差。唔按效果加 arm／改 k／改窗。

## 限制預先聲明

官方 GPS time 唔等於逐駒 photo-finish 時間；要清楚標示來源。只覆蓋 Queensland，
唔冒充全澳結果。來源今天回補，冇可驗證當時 published/ingested timestamp：
historical source availability 係 FLAG；即使診斷結果正面亦唔可直接 promotion。
今次唔開未來 forward holdout，唔改判決合約。

## 可重現入口

`scratch/au_measured_runner_time_20261015.py`；詳細結果待執行後追加。

## 來源核對及 parser 正確性

- Sportsbet 網站（Ipswich 2026-10-15 R2）逐個展開 Hot Majesty／Slipsain，
  兩匹 2026-09-23 Eagle Farm R5 1800m 往績都顯示 `Time: 01.49.70`。
  Long Form 明文係 `Winning Time 1:49.700`。唔可以將呢欄重命名做逐駒時間。
- 同場官方 CSV：Becamo **109.70s**、Slipsain **109.85s**、Hot Majesty **110.03s**。
  呢個直接交叉驗證共用頭馬時間與逐駒 GPS 時間嘅分別。
- 8,918 份 SportsbetForm HTML cache：3,726 份有 Winning Time；runner／finish／
  finishing／overall time label 零份。呢個只限已存快取／已查 UI，唔代表網站所有
  產品、app 或 API 都永遠冇逐駒時間；用戶如有另一個位置可再核對。
- 3,687 Formguide 有 206,136 個 WinningTime token、12,651 個 Runner Time token；
  後者係舊 Racenet 來源，唔冒充現時 Sportsbet 來源。
- 官方 316 CSV、5,969,345 bytes；31,966 rows，22,745 條完整逐駒時間，
  9,221 條未追蹤／零分段／不完整記錄剔除，零 duplicate-time conflict。
  對到既有 formguide 地況及明確有 GPS 記錄嘅歷史頭馬：1,547 場標準參考。
- CSV 第二個 payload 數字係 TAB saddlecloth，**唔係名次**；winner 必須由
  同一條已完成歷史往績嘅 result line 名字確認，唔用「最短 tracked time」冒充頭馬。
- CSV 表頭係 track template，13,617 rows 嘅 template 距離同實際分段終點唔同。
  Rockhampton 2026-10-02 R1 template `1100m`，官方 PDF 與分段終點都係 **1050m**；
  Wasabi Barbie 分段總和 **60.12s** 對到 PDF。來源 join 用分段終點途程，再獨立
  要求同 formguide 途程相符；唔擅自放寬途程匹配。
- Ipswich 2026-10-08 R1 Swanfels 分段總和 **101.81s**，同 PDF TIME **1:41.81**
  一致；CSV header 102.825s 唔入 feature。
- preflight 第一版錯將 template 當實際距離，之後又發現舊 CSV 用 M:SS 格式；
  provisional 結果作廢。以上兩個來源正確性修正有官方 PDF／原 CSV 獨立依據，
  冇改任何 arm、gain、最少仗數、窗口或模型權重去救結果。
- 地況按來源可靠程度用 broad good／soft／heavy／firm／synthetic，同義數字映射；
  冇 exact rating 嘅歷史行唔捏造數字級別。

## 同語料配對結果

現役引擎 fresh dump：3,299 場（含較早歷史／不完整賽果），按已鎖定日期及賽果完整性
剩 **2,496 場／24,085 runner appearances／71 賽日，08-05 至 10-14**。
Baseline 重算能力分同現役合成式差少於 0.00011；A/A 全部指標零差。

| 固定加分 arm | Gold | Good 位置 | Pass | Gold Δ pp [95% CI] | Good Δ pp [95% CI] |
|---|---:|---:|---:|---|---|
| 現役 baseline | 510 | 651 | 1,228 | — | — |
| 逐駒 GPS 實測 | 506 | 648 | 1,232 | −0.160 [−0.352, 0.000] | −0.120 [−0.338, +0.082] |
| 頭馬 GPS 時間共用 | 504 | 651 | 1,231 | −0.240 [−0.424, −0.079] | 0.000 [−0.221, +0.210] |
| 頭馬 GPS＋負馬位估算 | 505 | 648 | 1,231 | −0.200 [−0.406, 0.000] | −0.120 [−0.338, +0.082] |

配對 bootstrap 以完整賽日 cluster、2000 次、seed 7。三個 arm×兩個 primary 係一個
Holm 家族；冇正面 primary WIN。逐駒實測相對估算只多捉一場 Gold、Good 不變，
唔構成實測時間有額外穩定增益嘅證據。相對共用頭馬 Gold +2、Good −3，同樣唔支持。

逐駒 feature 非空 **1,887 appearances（7.83%）**；561 場有至少一匹，409 場有至少
兩匹（57 賽日），133 場排序有變。單獨 feature 嘅可比場內 AUC mean **0.5666**，
只代表有判別力，唔代表加入現有模型有邊際收益。

逐駒 arm 六段 Gold Δ pp：−0.221、0、−0.275、−0.205、0、−0.267；
Good：−0.221、+0.262、−0.275、0、−0.229、−0.267。Gold 只有兩段非負，
未達四段要求。四個場數桶及五個 ranking metric 差額列於 evidence JSON；
ranking 只作描述，今次冇已完成部件預算／MDE 診斷，唔用嚟判 RANKING_WIN。

## 判決與限制

**唔加入 live。** 呢個固定構造令 Gold／Good 點估計回歸；亦未通過來源 availability
audit（machine decision 為 `leakage_audit_failed`，唔假報 PASS）。今次係來源回補嘅
historical diagnostic，唔係 untouched forward holdout，冇開／改既有速度 shadow terminal。
所有官方引用只用 target 前已完成往績，但今日回補嘅 publication／capture timestamp
未被證明當時已存在。

覆蓋只係 Queensland、有完整 GPS、最少三條且標準足夠嘅子群；另外其餘州份及
缺 GPS 馬會中性。**唔可以將呢次未贏推論成全程完賽時間無用。** 下一個資料方向係
核對用戶所指 Sportsbet 其他欄位／取得更廣逐駒實測來源；唔靠本次結果再搜 k。
Trial cutoff、weights、正式 engine、dashboard、D1 ledger 全部冇改。

## 重現及保存

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/central_wong_choi/scripts/central_wong_choi.py corpus-audit --domain au --json
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-runner-time-baseline.json
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_measured_runner_time_20261015.py fetch --cache /private/tmp/au-runner-time-official
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_measured_runner_time_20261015.py evaluate --cache /private/tmp/au-runner-time-official --root "/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing" --baseline /private/tmp/au-runner-time-baseline.json --out /private/tmp/au-runner-time-results.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scratch -p test_au_measured_runner_time_20261015.py -v
```

官方 CSV 原檔、URL／SHA256 manifest、PDF 樣本、baseline、逐場 predictions 及 evidence
另存本次 Codex artifact 目錄 `AU-runner-time-research/`；repo 只保存程式、報告及精簡證據。
六個來源／時間隔離測試 PASS；quick／full repo checks 見交付記錄。只保存研究分支，唔 release。

來源：
- [Sportsbet Ipswich R2](https://www.sportsbet.com.au/horse-racing/australia-nz/ipswich/race-2-11046759)
- [Sportsbet Long Form](https://www.sportsbetform.com.au/453035/3448926/)
- [Racing Queensland 官方 sectionals 索引](https://www.racingqueensland.com.au/industry/thoroughbred/thoroughbred-sectionals)
- [Eagle Farm 2026-09-23 官方 CSV](https://www.racingqueensland.com.au/RacingFile.ashx?path=/Sectional/20260923_Eagle_Farm_T.csv)
