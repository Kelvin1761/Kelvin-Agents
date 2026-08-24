# EXP-20260824-03 Sportsbet PacePerf 逐仗表現歸因

- **日期**：2026-08-24
- **平台**：AU
- **起因**：Randwick R1 現役模型把 Gunroom 排第 1，實際 9/11；Clear Proof、
  Isawyou 原始排第 2、3，實際跑第 1、2。Gunroom 嘅 PacePerf leaf 80.91，係主要
  高估來源之一。
- **假設**：Sportsbet L600 係一場賽事嘅 race-level 環境，馬匹只係參加過嗰場唔等於
  證明自己應付到。若正式賽輸超過 3L，嗰場 L600 環境唔應計入該馬平均。
- **production code 改動**：無
- **重跑腳本**：`scratch/au_gunroom_20260824/sportsbet_pace_attribution_experiment.py`
- **判決**：**REJECT / 不落 production**

## 預先鎖定候選

只測一個版本，冇 sweep、冇用 Randwick R1 結果調 threshold：

1. Sportsbet 正式賽輸距 ≤3.0L：保留該仗 race-level L600 delta。
2. 正式賽輸距 >3.0L：不計該仗。
3. 試閘維持現役做法，避免同 EXP-20260823-02 已否決嘅「刪試閘」混埋。
4. 逐場用候選 L600 平均重算場內 z-score，同現役一樣 `60 - z × 20`。
5. 只改 `pace_figure_score`；完全冇讀 odds、SP 或市場資料。

## 資料與重播核對

- runtime dataset：1,411 場；development 899、terminal holdout 512，按完整日期切。
- Sportsbet source：5,509 匹；當中 3,748 匹有可逐仗對齊嘅 Formguide PF 證據。
- 611 份 Formguide 成功 resolve；0 份缺失。
- 逐匹用原本所有 PF row 重播 `l600_delta_avg`：**0 drift**（容許誤差 0.011 秒）。
- 候選刪去 12,559 個「正式賽輸 >3L」PF run，實際改動 3,555 匹排名分數。
- Sportsbet source 由 2026-08-05 先進入 runtime 語料，全部位於合約 terminal 時段；
  因此 development 係零改動，唔可以用今次 holdout 結果再調另一個門檻。

## 合約結果

| 指標 | dev | holdout | 95% CI | 判決 |
|---|---:|---:|---:|---|
| 頭 5 位配對場內 AUC | +0.0000 | +0.0035 | **[-0.0040,+0.0110]** | REJECT |
| 全場配對 AUC | +0.0000 | +0.0034 | [-0.0026,+0.0090] | 不確定 |

holdout 次要指標變化：

| Gold | Gold strict | Good位置 | Pass | Champion | Winner in Top 3 | Winner in Top 5 | T3 precision |
|---:|---:|---:|---:|---:|---:|---:|---:|
| -0.39pp | -0.78pp | -0.20pp | **-1.37pp** | +0.59pp | **-1.37pp** | +0.59pp | **-0.65pp** |

主 AUC 點估計向上，但 CI 跨零；項目最重視嘅上名捕捉指標多數向下，冇足夠證據話係
改善。按合約必須 REJECT。

### Holdout 馬群分層

- ≤8 匹：Good位置 +1.27pp，但 Pass -1.91pp、winner in Top 3 -3.18pp。
- 9–10 匹：Good位置 -1.99pp、Pass -0.66pp。
- 11–12 匹：Good位置 +0.81pp、Pass -2.44pp。
- 13+ 匹：Gold / Good位置各 -1.23pp、winner in Top 3 -3.70pp。

冇一個馬群桶呈現一致改善。

## Randwick R1 凍結快照

| 排名 | 原始模型 | 候選 |
|---:|---|---|
| 1 | Gunroom 71.0427 | **Gunroom 70.9096** |
| 2 | Clear Proof 70.5121 | **Isawyou 70.2057** |
| 3 | Isawyou 70.2057 | **Clear Proof 69.7566** |
| 4 | Let's Go Again 69.2082 | Twinkling Star 68.7949 |
| 5 | Twinkling Star 68.4226 | Let's Go Again 68.7762 |

Gunroom 10 個 PF run 保留 8 個，L600 平均由 -0.163 變 -0.108，PacePerf 只由
80.91 降到 79.74，仍排第 1。Clear Proof 同樣保留 8/10，但平均由 +0.139 變
+0.305，PacePerf 由 58.70 跌到 52.07，反而由第 2 跌到第 3。候選連個案目標都冇
達成。

## REF-DA01 五角度覆盤

### 1. 結果偏差

Gunroom 原始第 1、實際第 9；Clear Proof / Isawyou 原始第 2 / 3、實際第 1 / 2。
候選只令 Gunroom 總分跌 0.13，並把 Clear Proof 錯降一位，結果偏差冇收窄。

### 2. 過程偏差

候選成功回答「馬匹有冇喺該步速環境跑近」，但 Sportsbet L600 仍係**同場所有馬
共享**嘅 race-level context。輸距篩選只改變一匹馬曾經接觸過邊批賽事，冇變成個體
sectional。場內 z-score 會同時重排全場，所以可以壓低 Gunroom，亦可以更大幅壓低
Clear Proof；呢個正係 R1 發生嘅事。

### 3. SIP-DA01 自我審計

個案直覺支持「環境要有兌現先算」，但凍結 R1 重播同 512 場 terminal 評估都唔支持
落 production。審計阻止咗由合理敘事直接跳到模型改動，決策由「值得試」變成
REJECT，符合證據紀律。

### 4. 泛化性審計

- 🟡 **診斷有用**：報告應清楚寫 PacePerf 係歷史賽事環境 exposure，唔係本駒實速。
- ⚪ **排名規則未證實**：3L 歸因 AUC CI 跨零，上名指標變差，R1 亦失敗。
- Sportsbet-era 全部落 terminal，現有語料冇獨立 Sportsbet development 期可再安全調參；
  應向前累積新賽果，而唔係重複翻炒同一 holdout。

### 5. Design Pattern Proposal

- **Issue ID:** REF-20260824-03
- **分類:** 🟡條件性資料限制
- **問題描述:** race-level L600 可以描述歷史 pace environment，但無法單靠 Sportsbet
  資料分辨個別馬喺同場嘅真正 sectional performance。
- **受影響 Protocol:** PacePerf 解釋文字、未來資料收集；唔改 ranking。
- **建議修改:** 保留現役 coarse PacePerf；明確標示「環境分」；Sportsbet-only 前提下
  停止再用輸距／名次包裝成個體實速。等有新 Sportsbet target dates 先做 forward
  validation。
- **預期效果:** 避免過度解讀，保持現有已驗證嘅正交訊號；唔聲稱命中率改善。
- **SIP-DA01 評價:** 有效 — 候選有廣泛 footprint，但仍因泛化證據不足而否決。

## 結論

**REJECT。** Sportsbet-only 最後一個新方向亦未能改善 PacePerf；production 排名保持
不變。現階段再改 threshold 只會用同一 holdout 調參，唔符合合約。應結束 PacePerf
調整，移去下一場分析。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scratch/au_gunroom_20260824/sportsbet_pace_attribution_experiment.py \
  /private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json \
  --randwick-dir '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive/2026-08-22 Randwick Race 1-10'
```
