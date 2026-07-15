# HKJC Wong Choi 未結構化訊號研究（2026-07-13）

## 結論先行

今輪未有任何候選足以正式改動 production 7D matrix。

最值得繼續 shadow 嘅方向係建立一個細權重 supporting matrix，集中處理：

1. trackwork / trial readiness；
2. variant-adjusted finish time / L400；
3. 已有 24/25 season professional priors（只用 win/place rate 與 sample size，完全不用 ROI／odds）；
4. rail/draw condition（但要先修正 surface/course parser）。

最佳探索候選喺 90 場 out-of-sample/forward 組合測試中保持 Top1 不變，Top2 individual place rate 由 45.0% 升至 48.3%，Top4 平均三甲命中由 1.544 升至 1.633；但 Top4 hit paired p=0.0676、Top2 p=0.261，仍未達統計門檻，而且 Happy Valley / Sha Tin 嘅 Top1 方向不一致。因此建議只延長 shadow validation，不實裝。

## 研究規則

- 全程不用 market odds、market rank、odds movement、ROI 或 value/edge。
- 只用賽前已存在欄位及歷史賽果。
- 不改 production engine、7D weights、`Race_X_Logic.json` 或現役 renderer。
- 4–5 月 archive 用 rolling-origin：每個測試賽日只用之前賽日訓練。
- 2026-07-12 沙田係額外 forward holdout；候選權重喺睇該日測試結果之前已固定。
- 顯著性用 paired exact McNemar、Wilcoxon signed-rank 同 10,000 次 paired bootstrap。

## 資料覆蓋

| Dataset | 賽日 | 場次 | 匹次 | 用途 |
|---|---:|---:|---:|---|
| 2026-04-12 至 2026-05-24 | 13 | 130 | 1,611 | 訓練 + rolling-origin |
| rolling heldout（2026-04-29 至 2026-05-24） | 8 | 79 | — | 主 backtest |
| 2026-07-12 沙田 | 1 | 11 | 152 | forward holdout |
| 合併比較 | 9 heldout days | 90 | — | 效果與 paired 統計 |

重要 data-quality 限制：

- 4 月 trackwork entries、adjusted finish time、last margin 大量缺失；5 月後先接近完整。
- `race_class` 對 `第一班／第三班／第四班` 解析失敗，舊 dataset 多數變成 `Unknown`。
- Sha Tin AWT 舊 snapshot 將路程放入 `course`，而 `track` 全部寫成 Turf；現階段不能可信地報 surface breakdown。
- Turf A/B/C/C+3 可作 rail/course proxy，但 AWT 不可。
- 07-12 coverage 健康：trackwork 100%、adjusted finish time 92.8%、L400 96.7%、last margin 89.5%。

## Rolling baseline（79 場）

| KPI | Baseline |
|---|---:|
| Top1 win | 19/79 = 24.1% |
| Top2 individual place | 74/158 = 46.8% |
| 兩匹 Top2 都入位 | 18/79 = 22.8% |
| Top3 平均三甲命中 | 1.241 |
| Top4 平均三甲命中 | 1.570 |
| Top4 包晒三甲 | 8/79 = 10.1% |
| Top5 平均三甲命中 | 1.772 |
| Winner MRR | 0.4287 |

## 各訊號獨立測試（rolling 79 場）

下表係「直接重新學完整 ranking」結果；佢反映訊號有冇信息，但亦顯示直接取代 7D 排名會過度重排頭兩名。

| 訊號 | Top1 | Top2 place hits | 兩匹 Top2 入位 | Top4 avg | Top4 全中 | 判斷 |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 19 | 74 | 18 | 1.570 | 8 | — |
| Official rating | 16 | 70 | 13 | 1.608 | 8 | reject |
| Distance/course record | 16 | 77 | 22 | 1.570 | 11 | Top2 有訊號，但傷 Top1 |
| Trackwork/trial | 14 | 73 | 16 | 1.633 | 10 | 過度重排 |
| Gear | 19 | 68 | 13 | 1.519 | 7 | reject |
| Trip/hidden merit flags | 12 | 67 | 10 | 1.494 | 8 | reject；文字 flags 太 noisy |
| Variant/sectional | 18 | 71 | 18 | 1.532 | 11 | 只見 shortlist 訊號 |
| Professional priors | 16 | 77 | 18 | 1.570 | 9 | 有 Top2 訊號但傷 Top1 |
| Rail/draw condition | 18 | 71 | 17 | 1.557 | 11 | parser 未穩定，不能採用 |
| Fixed-class rating | 16 | 72 | 17 | 1.582 | 9 | 修正 class token 後仍無改善 |

`clean_variant_sectional` 直接模型曾將 Top4 全中由 8 增至 14（McNemar p=0.0313），但 Top2 place hits 由 74 跌至 70、Top1 由 19 跌至 18；再加上今輪做過多個候選比較，呢個單一 p-value 不足以支持實裝，故仍然 reject 作完整 ranking。

## Supporting matrix 測試（rolling 79 場）

Supporting matrix 保留現有 7D baseline，只讓新 dimension 用固定比例影響 final score。

| 候選 | Top1 | Top2 hits | 兩匹 Top2 | Top4 avg | Top4 全中 | 主要統計 |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 19 | 74 | 18 | 1.570 | 8 | — |
| Trackwork 20% | 20 | 75 | 18 | 1.633 | 10 | Top4 p=0.277 |
| Variant 10% | 19 | 75 | 20 | 1.608 | 9 | Top4 p=0.250 |
| Trackwork 20% + Variant 10% | 19 | 74 | 19 | 1.620 | 12 | 全中 p=0.219 |
| + Distance 10% | 18 | 75 | 20 | 1.646 | 12 | Top4 p=0.173；Top1 -1 |
| + Prior 10% + Rail 10% | 19 | 77 | 20 | 1.646 | 10 | Top4 p=0.151 |
| Clean trackwork 20% | 20 | 75 | 18 | 1.646 | 10 | Top4 p=0.211 |

`raw + field-relative` 同時入模會造成共線性；de-duplicated clean trackwork 稍為改善 Top4，但仍未顯著。呢個支持日後每個概念只保留一個 authoritative representation。

## 2026-07-12 沙田 forward holdout（11 場）

| 候選 | Top1 | Top2 individual place | 兩匹 Top2 | Top4 avg | Top4 全中 |
|---|---:|---:|---:|---:|---:|
| Baseline | 2/11 | 7/22 = 31.8% | 0 | 1.364 | 0 |
| Distance/course direct | 2/11 | 9/22 = 40.9% | 1 | 1.545 | 1 |
| Clean variant direct | 3/11 | 10/22 = 45.5% | 2 | 1.455 | 0 |
| Trackwork 20% | 2/11 | 10/22 = 45.5% | 2 | 1.455 | 0 |
| Trackwork 20% + Variant 10% | 2/11 | 10/22 = 45.5% | 2 | 1.545 | 0 |
| + Prior 10% + Rail 10% | 2/11 | 10/22 = 45.5% | 2 | 1.545 | 0 |

主候選嘅改善並非只來自一場：Race 3、5、8 各增加一個 Top2 place hit；Race 1、6 各增加一個 Top4 hit。冇任何 Race 嘅 Top4 hit 數下降，Top1 兩場命中亦保持不變。不過 11 場太少，Top2 hit paired p=0.25。

## 90 場合併結果

| 模型 | Top1 | Top2 individual place | 兩匹 Top2 | Top4 avg | Top4 全中 | Winner MRR |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 21/90 = 23.3% | 81/180 = 45.0% | 18/90 = 20.0% | 1.544 | 8/90 = 8.9% | 0.4197 |
| Trackwork 20% | 22/90 = 24.4% | 85/180 = 47.2% | 20/90 = 22.2% | 1.611 | 10/90 = 11.1% | 0.4309 |
| Trackwork 20% + Variant 10% | 21/90 = 23.3% | 84/180 = 46.7% | 21/90 = 23.3% | 1.611 | 12/90 = 13.3% | 0.4233 |
| + Distance 10% | 20/90 = 22.2% | 83/180 = 46.1% | 21/90 = 23.3% | 1.644 | 13/90 = 14.4% | 0.4155 |
| + Prior 10% + Rail 10% | 21/90 = 23.3% | 87/180 = 48.3% | 22/90 = 24.4% | 1.633 | 10/90 = 11.1% | 0.4276 |

最佳 Top2/Top4 平衡候選係 `Trackwork 20% + Variant 10% + Prior 10% + Rail 10%`：

- Top1 不變；
- Top2 individual place +3.3 percentage points；
- 兩匹 Top2 都入位 +4.4 points；
- Top4 average +0.089；
- Top4 paired Wilcoxon p=0.0676，bootstrap 95% CI 為 +0.011 至 +0.167；
- Top2 paired p=0.261，仍不顯著；
- 多候選探索後未做 multiplicity correction，不能將 p=0.0676 視為接近通過 production gate。

## 穩健性與退步位置

- Sha Tin rolling：主候選 Top1 有改善；Happy Valley Top1 有退步，整體互相抵消。
- 07-12 forward 只係 Sha Tin，未能解決 Happy Valley consistency 疑問。
- 1200m、1650m 嘅 Top1 容易被 supporting signals 調低；1400m、1800m 有改善，但各 slice 樣本太細。
- Class breakdown 因 parser 將中文班次變成 Unknown 而不可信。
- Surface breakdown 因 AWT/Turf contract 錯誤而不可做。
- Gear 及 generic hidden-form flags 對 Top2 明顯有害，應停止沿現有表示法研究。

## 建議次序（仍然不實裝）

1. **修復 research data contract**
   - 正確 parse 中文班次、Group race、Turf/AWT、rail A/B/C/C+3。
   - 每個 archived race 保存 `feature_schema_version`、engine hash、7D matrix snapshot、final ranking snapshot。
   - 將 4 月 archive 用同一 schema 重新 materialize；不能 backfill 嘅欄位保持 neutral 並保存 missing mask。

2. **延長兩個 preregistered shadow 候選**
   - Candidate A：Trackwork 20%。
   - Candidate B：Trackwork 20% + Variant 10% + Prior 10% + Rail 10%。
   - 權重固定，不准按 meeting 再調。

3. **最低確認門檻**
   - 再收集至少 15–20 個完整賽日；Happy Valley 與 Sha Tin 各至少 6 個。
   - Top1 不得下降超過 1 percentage point。
   - Top2 individual place 至少 +2 points，且兩匹 Top2 入位率不下降。
   - Top4 average / Top4 全中至少一項 paired p<0.05，bootstrap CI 不跨 0。
   - 兩個場地、主要 1200/1400/1600-1650 路程方向一致。

4. **只保留 concept-level features**
   - 唔好同時放 raw、field-relative、flag 三個重複版本。
   - Trackwork 應拆成 cadence、gallop density、jockey presence、slowing/medical risk 四個可解釋 component。
   - Variant/sectional 應先建立一致嘅「越低越好／越高越好」方向，再做 daily variant normalization。

5. **暫停／拒絕方向**
   - Gear standalone。
   - Generic trip/hidden-merit keyword flags。
   - Official rating standalone。
   - 一次過 full-feature ranking model及 dual-head win/place model；兩者都明顯傷害 Top1/Top2。

## 最終判斷

今輪證據顯示「未結構化訊號」有機會改善 Top2 同 Top4，但正確用法唔係取代 7D，而係做細權重、concept-level supporting matrix。07-12 forward holdout 對 trackwork-led 候選係正面，但統計與跨場地一致性仍未足夠。現階段最合理行動係固定候選繼續 shadow，先修 data contract，再等真正新賽日驗證。
