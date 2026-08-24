# EXP-20260824-02 休後狀態 × 證據厚度 × 高波動加分安全欄

- **日期**：2026-08-24
- **平台**：AU
- **起因**：Randwick R1 原始模型將 Gunroom 排第 1，但實際 9/11；Clear Proof、
  Isawyou 原始排第 2、3，實際跑第 1、2。用戶認為其他馬排序合理，問題集中喺
  Gunroom 被高估。
- **假設**：若模型首選同時係長休後第二仗、復出未上名、計分 leaf 證據薄，而且
  大比例優勢來自濕地 overlay + pace-performance lift，應由第 1 降到第 3。
- **production code 改動**：無
- **重跑腳本**：`scratch/au_gunroom_20260824/prep_evidence_overlay_experiment.py`
- **判決**：**REJECT / 不落 production**

## 資料與防洩漏

- point-in-time runtime dataset：**1,411 場**；development 899、合約 terminal
  holdout 512，按完整日期切分。
- 休後狀態只由目標賽前 `Facts.md` 正式賽日期與名次重建。
- 證據厚度沿用現役 `_default_leaf_count`：9 個計分 leaf 有幾多個剛好停留預設 60。
- 高波動支持：
  - `positive wet lift = max(wet_form_feature, 0)`
  - `positive pace lift = max((pace_perf matrix - 60) × live weight, 0)`
  - `volatile_share = (wet lift + pace lift) / (ability - 60)`
- **完全冇讀市場、SP 或賽後價格。** `actual_pos` 只作評估 label。

## Randwick R1 機制核對

Gunroom 原始賽前快照：

| 項 | 值 |
|---|---:|
| 原始 ability | 71.0453 |
| 休前空窗 | 239 日 |
| 復出後再跑 | 14 日 |
| 復出結果 | 未上名（4/8） |
| 計分預設 leaf | 2 |
| pace lift | +2.3812 |
| wet lift | +2.4753 |
| volatile share | **43.97%** |

即係 Gunroom 高出中性 60 嘅 11.0453 分，有接近一半由兩個平均有效、但今場同時失手
嘅訊號撐起。個案機制成立。

## 三條件主候選

只喺 development 搜：spell 90/120/180 日、再跑 21/30/45 日、預設 leaf 1/2、
volatile share 30/40/50%、降 1/2 位，共 108 個配置。預先要求至少 8 個 development
觸發先叫有最低 power。

**結果：0 個配置有 8 次觸發。** 最佳非零配置只得 1 次 development 觸發：

- spell ≥120 日、30 日內再跑、預設 leaf ≥1、volatile share ≥30%、降兩位
- dev 頭五 AUC：+0.000062；五 fold 只有最後一 fold 非零
- holdout 頭五 AUC：**+0.0005 [0.0000, +0.0013]**
- dev 觸發 1 匹（0 上名）；holdout 觸發 2 匹（0 上名）
- Good位置全樣本 +0.14pp；Gold / Pass / t3prec / winner@3/5 全部 0

CI 下界只係 0，按合約係 **REJECT**。方向啱但樣本只有 3 匹，唔可以講成改善。

### 預先定義嘅嚴格 Gunroom profile

spell ≥180、30 日內再跑、預設 leaf ≥2、volatile share ≥40%、降兩位：

- development 觸發：**0**
- holdout 觸發：**0**
- 所有指標：0

呢條規則會觸發 08-22 Gunroom，但 1,411 場歷史語料冇第二個同形首選可供驗證；
實質係單馬規則，唔可以 ship。

## Ablation（主候選鎖定門檻）

| 條件 | dev 頭五 AUC | holdout | 95% CI | dev / holdout 觸發 |
|---|---:|---:|---:|---:|
| 只休後 | −0.000310 | +0.000257 | [−0.000893,+0.001455] | 21 / 12 |
| 只薄證據 | −0.000682 | **−0.005521** | **[−0.010455,−0.000643]** | 246 / 226 |
| 只高波動 | −0.000558 | −0.001412 | [−0.004768,+0.001926] | 174 / 101 |
| 休後＋薄證據 | −0.000186 | +0.000642 | [−0.000127,+0.001540] | 5 / 5 |
| 休後＋高波動 | +0.000248 | +0.000514 | [0.000000,+0.001285] | 6 / 2 |
| 薄證據＋高波動 | −0.000682 | −0.000514 | [−0.002941,+0.001679] | 55 / 51 |
| 三條件 | +0.000062 | +0.000514 | [0.000000,+0.001285] | 1 / 2 |

薄證據本身用「首選降到第 3」會顯著變差；現役安全欄只同第 2 對調、保持 top-3
內部排序，正正避免呢個成本。三條件交互唔係證明三項各自有用，只係罕見篩選器。

## 次級 ablation：移除薄證據條件

因三條件完全冇 power，另只喺 development 搜「休後＋高波動」：spell 60/90/120/180、
再跑 21/30/45 日、share 20/30/40/50%、降 1/2 位。

development 鎖定：spell ≥60 日、30 日內再跑、share ≥20%、降兩位：

- dev：19 次觸發，頭五 AUC **+0.000434**，5/5 fold 非負
- holdout：8 次觸發，頭五 AUC **+0.0006 [−0.0003,+0.0016]**
- dev cohort 上名 3/19（15.79%）；holdout 3/8（37.50%）
- 全樣本 Good位置 +0.07pp、Champion +0.07pp；其餘主要指標 0

主 CI 仍跨零，照樣 **REJECT**。而且主三條件 run 已經間接曝光過兩個相關 terminal
個案，所以呢段只可作 exploratory ablation，唔可以當全新 pristine holdout。

## Randwick R1 候選排序

兩個會觸發 Gunroom 嘅候選都將首選移到原第 3 與第 4 分數中間：

| 排名 | 原始模型 | 候選 |
|---:|---|---|
| 1 | Gunroom 71.0453 | **Clear Proof 70.5134** |
| 2 | Clear Proof 70.5134 | **Isawyou 70.2017** |
| 3 | Isawyou 70.2017 | Gunroom 69.7044 |
| 4 | Let's Go Again 69.2070 | Let's Go Again 69.2070 |
| 5 | Twinkling Star 68.4200 | Twinkling Star 68.4200 |

所以候選**確實修到今場**，而且冇利用賽果重算其他馬；但單場吻合唔等於可泛化。

## REF-DA01 五角度覆盤

### 1. 結果偏差

| 原始預測 | 實際 | 偏差 | 候選處理 |
|---:|---:|---:|---|
| Gunroom 1 | 9 | +8 | 降至 3 |
| Clear Proof 2 | 1 | +1 | 升至 1 |
| Isawyou 3 | 2 | +1 | 升至 2 |
| Call Me Sassy 7 | 3 | +4 | 不變，仍然漏出 Top 5 |

候選改善頭二次序，但冇修 Call Me Sassy 呢個 Top-5 miss。

### 2. 過程偏差

- 模型唔係全面睇錯 Gunroom：基礎能力 68.57 並非全場最高；係 pace + wet 合計
  +4.86 將佢推過 Clear Proof。
- 「休後第二仗」確實冇落入舊 ranking context。
- 兩個 lift 喺全語料平均有效，所以單獨壓低會蝕；只有交互方向呈正，但 cohort 太細。

### 3. SIP-DA01 自我審計

五角度審計改變咗決策：只睇 R1 會採用，完整 development / holdout / ablation 後改成
REJECT。呢個改變正確，因為嚴格規則喺 1,411 場語料係 0 次歷史觸發；放寬後 CI
仍跨零。協議冇同基礎模型衝突，反而防止把賽後結果寫成單馬 override。

### 4. 泛化性審計

- 🟡 **條件性風險 profile**：休後短期再跑兼主要靠高波動支持，方向值得監察。
- ⚪ **未證實排名規則**：三條件同形個案極罕，現有語料不足以證明降兩位泛化。

### 5. Design Pattern Proposal

- **Issue ID:** REF-20260824-02
- **分類:** 🟡條件性
- **問題描述:** 基礎分唔係最高、但由 wet + pace lift 大幅反超嘅休後首選可能過度自信。
- **受影響嘅 Protocol:** 報告風險層／首選可靠度
- **建議修改:** 暫時只記 `prep_volatile_support_risk` 診斷旗標，唔改排名；向前累積
  至少 30 個觸發後，用同一門檻重跑合約。
- **預期效果:** 提升可解釋性；現階段**唔聲稱命中率改善**。
- **SIP-DA01 評價:** 有效 — 成功分開「修到一場」同「可泛化改善」。

## 結論

**REJECT ranking change。** 候選會把 Randwick R1 排成 Clear Proof／Isawyou／Gunroom，
但三條件歷史樣本近乎零；較寬嘅休後＋高波動版本亦係 holdout CI 跨零。production
評分保持不變，失敗候選唔 commit 入 model code。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  scratch/au_gunroom_20260824/prep_evidence_overlay_experiment.py \
  /private/tmp/au_reopt_20260821/work/au_ml_runtime_dataset.json \
  --randwick-dir '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive/2026-08-22 Randwick Race 1-10'
```
