---
name: leakage-audit
description: 'Detect data leakage and invalid backtesting in the Wong Choi racing, tennis and NBA pipelines. Use this skill whenever a feature is added or changed, feature engineering or dataset construction changes, train/test splitting or fold logic changes, rolling or career statistics change, odds/results joins change, or preprocessing/scaling/encoding changes. Also use before believing any unusually good backtest result.'
---

# leakage-audit

呢個 repo 每一次「靚到唔似真」嘅結果都係洩漏。三個實例，記住個形狀：

1. **Sportsbet form pages 洩漏咗要預測嗰場本身** —— 17.1% 嘅 form run 就係當場。
   佢一手做出咗「Sportsbet 打贏現役」呢個假結論。
2. **賠率快照含走地價** —— tennis 回測冇取 `MIN(id)`，做出 +58% ROI 嘅假結果。
3. **Sire signal** —— leave-one-out +4.9pp（首戰 +13.4pp），point-in-time 全部負。
   **LOO 唔係 leakage control。**

## 唯一真正管用嘅問題

對每一個涉及嘅欄位，逐個問：

> **「呢個**確切**嘅資訊，喺我落注嗰一刻（賽前 / 開盤時）真係拎得到嗎？」**

答唔到「係，而且我證明得到」= 當洩漏處理，flag 出嚟俾人審，**唔准當安全**。

## 統計閘門捉唔到洩漏

一個洩漏特徵可以 5/5 fold 全過、holdout +17.58pp。**只有逐欄位嘅賽前檢查捉得到。**
所以呢個 skill 唔靠 AUC，靠對照。

## 檢查清單

### A. 目標／賽後資訊
- [ ] 有冇用到 `actual_pos`、`finish_position`、`margin`、`SP`、賽後 sectional、
      賽後 going、結算後嘅 ledger 欄位入去**評分**（唔係只做 join 完之後評估）
- [ ] `au_runtime_micro_ablation.py` 嘅做法係對嘅範本：賽果只喺**評分之後**
      join，永遠唔入 `race_context` 或 horse data。新 harness 照跟。
- [ ] `racing_data_health.py` 刻意只讀賽前 artifact —— 唔准為方便加賽果進去

### B. 時間 / point-in-time
- [ ] 每個歷史統計（J/T 上名率、draw bias matrix、班次基準、opponent index）
      係唔係只用**當日之前**嘅資料重算？定係用今日成個語料算完再套返舊場次？
- [ ] `.shift()` / rolling window 方向：`rolling(...).mean()` 有冇包住當期？
- [ ] 官方評分、州曆、going 呢類**有時間窗**嘅欄位有冇被永久 cache？
      （七個州曆凍結喺 11 日前，已修，6h TTL —— 同一個形狀會再出現）
- [ ] 舊語料庫係唔係賽後重新評分過？97 個 AU 場次有 85 個 mtime = 2026-07-17，
      最舊遲 349 日。**乾淨 point-in-time 只有 08-05 起。** 用早過呢個日期嘅
      場次做 point-in-time 論證 = 無效。

### C. 切分
- [ ] dev / holdout 係**時間排序**切，唔係隨機切
- [ ] 同一場／同一場次 meeting 有冇跨越 dev 同 holdout 邊界
- [ ] 重複事件（同一場被抽兩次、re-score 舊檔留低兩份）有冇去重
- [ ] fold 之間有冇 overlap；walk-forward 每一步嘅訓練窗真係只向後睇
- [ ] **時間切分等同 condition 切分** —— 印出 population 組成先。網球 holdout
      74% 硬地，訓練窗有一半係 0% 硬地。你以為量準確度，其實量場地。

### D. fit/transform
- [ ] scaler / encoder / normaliser 有冇 fit 落全份數據（包括 holdout）
- [ ] z-score 係**場內**做，唔係全池。全池標準化會把「呢場獎金高」當成
      「呢匹馬好」（`au_feature_ab.py` 已強制場內）
- [ ] 缺值填補用嘅中位數／均值係唔係只由訓練窗算
- [ ] 冇值嘅馬 z = 0（唔郁佢），**唔可以當成最細值**

### E. join 洩漏
- [ ] 由賽果檔／結算檔 join 返嚟嘅欄位，有冇一個唔覺意流入評分路徑
- [ ] 賠率：`tennis_wc` 回測**一定** `MIN(id)` 取最早快照；後面嘅 id 係走地價
- [ ] `Race_Results_*.json` 只准做評估，唔准做特徵源
- [ ] opponent index 之類由 form-line 文字抽出嚟嘅欄位，`partial` 記錄要標記，
      唔可以當完整

### F. 「有欄位」唔等於「有數據」
- [ ] 量 power 之前先 `count` 非空。`speedmaps=` / `odds=` 曾經寫落每個 call
      site 但**冇 caller 傳**，292 行 SpeedPos 真值 0 行。
- [ ] 中性值（60.0）唔係「分數低」，係「冇證據」。混埋一齊算會做出假訊號。

## 點做

```bash
# 1. 睇欄位覆蓋同 fallback，唔係睇有冇 key
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_source_coverage_audit.py

# 2. 數據合約：presence / neutral 比例 / 場內散佈 / 值域
python3 .agents/skills/shared_racing/scripts/data_contract.py --platform au --check

# 3. 賽前 artifact 對齊（刻意唔讀賽果）
python3 .agents/skills/shared_racing/scripts/racing_data_health.py

# 4. 獨立來源交叉驗證（最可靠嘅單欄位洩漏測試）
#    由另一個已驗證來源獨立計同一個特徵，兩者唔夾就係洩漏。
```

## 輸出

逐個涉及欄位一行：

```
欄位                 賽前拎得到？  證據                                 判決
last6_avg            係           由 form-line 抽，日期全部 < 賽日        OK
official_rating      有疑          RA 個窗只回溯一星期，過咗補唔返        FLAG
sire_strike_rate     否            要用到當日之後嘅同父仔女成績           LEAK
```

任何 `FLAG` 未清 = 唔准當呢個候選過閘。任何 `LEAK` = 立即 REJECT，
並且**回頭作廢**所有用過呢個欄位嘅舊結論。
