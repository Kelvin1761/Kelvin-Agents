# 2026-05-31 AU Noise And Logic Audit（港式中文）

## 範圍

今次針對 AU Wong Choi 現行 live 結構，集中檢查：

1. 有冇明顯 noise 應該移除
2. 有冇 logic 前後矛盾
3. `confidence_score` 應唔應該保留
4. `jockey_horse_fit_score` 係咪過複雜
5. `jockey_score / trainer_score` 有冇改善空間
6. `health_score` 應唔應該移除

相關 benchmark：

- [2026-05-31 AU Noise Fix Shadow Test.md](./2026-05-31%20AU%20Noise%20Fix%20Shadow%20Test.md)
- [AU Wong Choi 現行評分結構詳解（港式中文）.md](./AU%20Wong%20Choi%20現行評分結構詳解（港式中文）.md)
- [Archive_Race_Analysis/AU_Racing/AU_JT_Database_Audit.md](./Archive_Race_Analysis/AU_Racing/AU_JT_Database_Audit.md)
- [Archive_Race_Analysis/AU_Racing/AU_Auto_Market_Free_Ablation.md](./Archive_Race_Analysis/AU_Racing/AU_Auto_Market_Free_Ablation.md)

---

## A. 已確認嘅 noise / contradiction

### A1. `Good/Firm` dynamic weight 分支係真 bug

- 現象：`get_dynamic_matrix_weights()` 喺 `Good/Firm` 會加 `weights["speed_performance"]`
- 問題：live 7D matrix 根本冇 `speed_performance`
- 結果：會直接 `KeyError`
- 狀態：**已修**

### A2. `health_score` 目前係真 placeholder

- `FEATURE_KEYS` 有 `health_score`
- 但 engine 冇 `_health_score()` scorer
- archive horse sample 入面 `health_score` 係固定 `60`
- 即係：
  - 唔係真訊號
  - 但會以 `18%` 權重滲入 `track` matrix

結論：

- 佢係「結構性中性 padding」
- 係 noise，但唔係強烈破壞型 noise

### A3. `confidence_score` 語意同用途唔一致

- 本質：data coverage / anchor completeness
- 現況：會喺 `place_tightening` 入面做正向推前

archive model top3 抽樣結果：

- hit horses 平均 `confidence_score = 81.20`
- miss horses 平均 `confidence_score = 81.12`

差距只係 `0.07`

結論：

- `confidence_score` 幾乎冇分辨力
- 至少現階段冇證據顯示佢適合做正向 ranking signal

### A4. 敘述層仲引用舊 matrix key

- live matrix 已經用 `class_weight`
- 但 narrative 層仍然有 `class_level / weight_pressure` 殘留

狀態：

- **已修**
- 呢個唔影響分數，但之前會令文字解釋同實際 matrix 結構唔完全一致

### A5. Sign anomaly 幾個位屬可疑

目前有幾個常數有「語意正面，但數值未必正面」嘅跡象：

- `class_up_pen = 0.0`
- `heavy_place_bonus = -2.88`
- `best_formal_mult = -0.06`

結論：

- 呢啲位值得警惕
- 但一次過改晒，歷史盤未證明會變好

---

## B. Machine-learning / ablation 測試結果

## B1. `Good/Firm` bug fix 後，runtime archive 表現

同 stored live baseline 比：

- Champion: `24.4% -> 20.6%`
- Gold: `4.1% -> 3.2%`
- Good: `20.9% -> 17.7%`
- Pass: `38.9% -> 35.1%`
- Top3 Place: `42.6% -> 40.5%`

但呢組唔應該解讀為「bug fix 令模型變差」。

原因：

- 呢個 runtime rerun 同 stored baseline 之間，混入咗整體 engine drift
- 唔係純粹 `Good/Firm` 單一變更嘅效果

所以：

- **bug fix 應保留**
- 唔應用呢組數去否定修正

## B2. `confidence_score` 去正向加成

### 方式 1：full runtime shadow

以 `runtime_fixed_good_only` 做內部 baseline 比較：

- Champion: `20.6% -> 20.9%`
- Gold: `3.2% -> 3.8%`
- Good: `17.7% -> 17.4%`
- Pass: `35.1% -> 35.4%`
- Top3 Place: `40.5% -> 41.1%`
- `0-hit: 53 -> 50`

即係：

- 小幅改善 `Gold / Pass / Top3 Place / 0-hit`
- 但 `Good` 輕微倒退

### 方式 2：直接喺 stored baseline 抽走 `place_tightening` 入面嘅 `confidence_score`

結果：

- Gold：不變
- Good：不變
- Pass：`38.9% -> 38.6%`
- Top3 Place：不變
- `0-hit: 48 -> 47`

結論：

- `confidence_score` 正向推前作用 **未被穩健證明**
- 它不再是強加分候選
- 但用「完全移除」做 mainline 改動，證據亦未夠乾淨

### 暫時建議

- **先唔直接 hard remove**
- 最穩陣係下一輪做：
  - `confidence_score weight = 0`
  - 或 `confidence_score` 只作 penalty / gate，不作正向加分

## B3. `health_score` remove

full runtime shadow：

- Gold: `3.2% -> 3.2%`
- Good: `17.7% -> 18.0%`
- Pass: `35.1% -> 34.5%`
- Top3 Place: `40.5% -> 40.3%`

即係：

- 幾乎冇穩定改善
- 甚至 `Pass` 略差

但舊有 matrix-only ablation 又見到：

- `track_pure` 有過 `Pass +1.3 ~ +1.6` 類型提升

結論：

- 「health_score 係假訊號」呢個判斷係對
- 但「直接移除 health_score」未證明可穩定提升 live ranking

### 暫時建議

- 唔建議即刻 mainline remove
- 但可列為第二優先級重構項：
  - 將 `track` matrix 改做純 `track_score`
  - 再配合其他 matrix weight 一齊重調

## B4. Sign anomalies 一次過修

full runtime shadow：

- Champion: `20.6% -> 19.6%`
- Gold: `3.2% -> 3.2%`
- Good: `17.7% -> 17.4%`
- Pass: `35.1% -> 34.5%`
- Top3 Place: `40.5% -> 40.5%`

結論：

- 一次過改 `class_up_pen / heavy_place_bonus / best_formal_mult`
- 歷史盤 **未見提升**

所以：

- 呢幾項唔應該 bundle 一次過上
- 要逐條再測

---

## C. `jockey_horse_fit_score` 係咪過複雜

### C1. 資料覆蓋

`AU_JT_Database_Audit.md` 顯示：

- `current_jockey_history_line`: `100%`
- `current_jockey_formal_rides > 0`: `53.8%`
- `current_jockey_trial_rides > 0`: `39.0%`
- `best_formal_jockey_rides > 0`: `95.3%`
- exact `jockey+trainer+track combo` exists: `30.8%`
- combo sample `>=10`: `18.4%`
- `trainer+track sample >=10`: `41.1%`

### C2. 解讀

`jockey_horse_fit_score` 複雜唔等於一定唔好，但現況有兩個問題：

1. 組件來源極多
   - formal rides
   - trial rides
   - best jockey
   - latest jockey
   - combo stats
   - trainer track stats
   - stage stats
   - jockey change signal

2. 覆蓋唔均勻
   - 有啲分支 coverage 高
   - 有啲分支（尤其 venue combo）其實好 sparse

### C3. Tempered test

我用 existing ablation 測咗 `jt_fit_tempered`：

- Gold: `4.1% -> 3.8%`
- Good: `20.9% -> 19.3%`
- Pass: `38.9% -> 38.0%`
- Top3 Place: `42.6% -> 42.0%`
- `0-hit: 48 -> 50`

結論：

- **直接 temper `jockey_horse_fit_score` 權重，現時係退步**

### C4. 你問應唔應該只集中 `jockey score + trainer score + combo score`

我目前判斷係：

- 唔應該即刻砍走 `jockey_horse_fit_score`
- 因為簡單 temper test 已經退步
- 但可以將佢 **拆細** 做更乾淨版本

最值得測嘅下一輪方向係：

1. `fit_core_only`
   - 只保留：
     - current formal rides / places
     - latest official vs current jockey
     - best formal jockey
2. `fit_combo_only`
   - 只保留：
     - venue combo
     - trainer track
3. `fit_signal_only`
   - 只保留：
     - jockey change signal
     - stage stats

咁樣先可以答到：

- 究竟係「整條 fit score 太複雜」
- 定係「當中某幾條 signal 好有用，某幾條先係 noise」

---

## D. `jockey_score / trainer_score` 值唔值得改善

### D1. 現況限制

目前：

- 只有 `field >= 13` 先用 named rating DB
- 中小場仍然多數靠 name-token fallback

而 archive 結果顯示 named DB on/off：

- Gold: `3.5% -> 3.2%`
- Good: `18.0% -> 17.7%`
- Pass: `35.1% -> 35.1%`
- Champion: `20.3% -> 20.6%`
- Top3 Place: `40.3% -> 40.5%`
- `0-hit: 56 -> 53`

### D2. 解讀

- named DB 並冇帶來大幅改善
- 但有少少：
  - `0-hit` 減少
  - `Champion`、`Top3 Place` 微升
- 同時：
  - `Gold`、`Good` 微跌

### D3. 結論

- `jockey_score / trainer_score` 有改善空間
- 但唔係「擴大 DB 覆蓋」就自然會變好

### D4. 我認為值得做嘅改進

1. 將 `named ratings` 由「只限大場」改做 shadow test 覆蓋所有 field sizes
2. 將 fallback token 規則同 named DB score 對齊
   - 避免同一個騎師喺大場同小場出兩套語意
3. 分開測：
   - `jockey only named`
   - `trainer only named`
   - `both named`

即係要做 **更窄身嘅 ML ablation**，而唔係一刀切。

---

## E. `health_score` 有冇足夠數據做真健康評估

目前睇 repo 同資料，我認為答案係：

- **未夠**

原因：

1. 冇獨立 `health` source
2. 冇穩定 vet / stewards / issue-coded layer
3. 冇明確傷病 / recovery / soreness database
4. 現有資料大多只係：
   - recent form
   - trial
   - consumption summary
   - warnings
   - forgiveness

呢啲比較似：

- readiness / robustness / profile cleanliness

唔係真正「健康分」

### 結論

- 名稱上，`health_score` 係誤導
- 數據上，暫時未夠支持做真 `health` 評估

### 建議

最合理有兩個選擇：

1. 短期：
   - 保留 placeholder，但唔再當成獨立訊號解讀
2. 中期：
   - 將 `health_score` 正式改名做 `robustness_score` 或 `readiness_score`
   - 前提係真有對應 scorer

如果唔做 scorer，我傾向最終：

- **移除 `health_score` 呢個概念**
- 但唔建議未經 matrix reweight 就即刻硬刪

---

## F. 今次最穩陣可落地嘅結論

### 應直接保留

1. `Good/Firm` crash fix
2. `class_weight` narrative key 對齊修正

### 暫時唔應直接 mainline

1. 一次過移除 `confidence_score`
2. 一次過移除 `health_score`
3. 一次過修所有 sign anomalies
4. 一刀切簡化 `jockey_horse_fit_score`

### 最值得下一輪 machine-learning test 嘅方向

1. `confidence_score -> gate only / no positive boost`
2. `fit_core_only / fit_combo_only / fit_signal_only`
3. `named jockey/trainer ratings` 全 field-size 覆蓋 shadow
4. `track_pure` + reweighted matrix 測試

---

## G. 一句總結

今次最清晰嘅答案唔係「有大堆 noise 可以即刻刪」，而係：

- 真 bug 要修
- 真 placeholder 要警惕
- 但大部分你懷疑嘅位，暫時仲需要更窄身、更乾淨嘅 ablation，先值得落主線

其中最有機會成為下一個 mainline candidate 嘅，仍然係：

- **將 `confidence_score` 從正向 ranking signal 降級**

但以目前證據，仲未到可以乾脆刪除。 
