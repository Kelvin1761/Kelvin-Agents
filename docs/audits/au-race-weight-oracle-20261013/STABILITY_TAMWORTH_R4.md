# Stability 第二輪：Tamworth R4 同單一第十名格式錯誤

日期：2026-10-13。**保留正確性修正；未證明整體模型表現改善。**

## 核對用戶個案

2026-10-12 Tamworth R4、1000m Maiden Plate：用戶講嘅係 **#2 Platinum Card**。
當日保存嘅賽前評分 CSV 排第二、64.8516 分；賽前市場 $35，賽果第七、SP $31。
市場資料只用作核對背景，完全冇加入修正、評分或參數。

賽前證據來自 meeting `_prediction_snapshots/20261012T100944.090506+1100-a041db23123d/`。
原 meeting、immutable snapshot、已發佈分析及賽果全部保留，冇回寫。

## 真正嘅錯誤：第十名變成冠軍加分

Facts 已將 Last 10 `0x` 解碼為近績序列 `10`，生涯只有 1 次正式出賽。
`0` 本來代表第十或更後，唔可以單憑摘要推論確切輸距、班次或精確終點名次。

舊 parser 對所有純數字兩位以上字串套用 compact Last 10 規則，將已解碼嘅單一
`10` 變成 `[1, 10]`。結果 `_consistency_score` 當佢有兩仗、一仗前三、一仗大敗：

| 項目 | 錯誤版本 | 修正格式 |
|---|---:|---:|
| 基礎 consistency 分 | 64.60 | 64.60 |
| 虛構前三獎勵 | +7.86 | 0 |
| 第八或更後懲罰 | −2.70 | −2.70 |
| consistency | 69.76 | 61.90 |
| PQ（完整樣本不足，fallback） | 69.76 | 61.90 |
| stability | 63.90 | 60.76 |

呢個錯誤唔係「第十扣得唔夠」造成；係**先錯加咗一場冠軍**。修正唔更改任何
權重、基礎分、扣分幅度、賠率使用規則。

本次修正：Facts enrichment 明確標記 `recent_form_format=positions`；parser
按來源區分 decoded positions、compact、legacy auto。未有 marker 嘅舊 Logic，
只喺匹配 Facts「近績序列解讀」同值時認作 decoded。Legacy compact `2134`
仍解作四仗；明確 compact `10` 仍解作 `[1,10]`。唔靠數值形狀猜資料格式。

現行完整 **8 匹賽前馬群**重播：64.9013 → 63.7364，排名 **2 → 3**，低約 1.165 分。
現行重播同當日 published 64.8516 唔係同一個數字；唔將兩者混用。
賽後可對齊嘅馬只有 7 匹，唔用 7 匹排名冒充當日 8 匹賽前排名。

## 點解修正後仍然偏高

1. **負面正式往績冇完整入表。** Racecard 生涯 1 次、Last10 `0x`；Facts 完整表卻
   係 0 正式＋3 試閘，Formguide 詳細段亦只得三課試閘。近績 `_form_score`
   因冇正式 entries 維持中性 60；PQ 因少於兩場完整正式資料而沿用 consistency。
   不能從摘要憑空補輸距、日期、馬群或班次。
2. **速度背景主要來自一課舊試閘。** PF 唯一 dated run 係 2025-11-04，對照
   Formguide 係 Tamworth TRIAL。race-context L600 delta 0.18，加輸距修正後
   own proxy 約 0.714；場內 z-score 令 pace_figure 84.08、pace_perf 82.96，
   對能力分貢獻約 +2.78。呢個唔係正式賽、亦唔係本駒實測 L600 split。
3. **fallback 本身仍高於中性。** 64.6 基礎分扣 2.7 後係 61.9，會留低輕微正面
   stability 貢獻。是否應重新設計先驗／可信度，屬新模型假設，不能為呢匹馬
   即場加大扣分或將冷門自動壓低。

## 整批比較：同一份輸入，兩個 arm

沿用上一輪固定 dev cohort、完整語料日期切法同 eligible races，唔換窗救修正。
兩個 arm 都由相同 prepared Logic／Facts 重播；baseline 強制舊 parser，candidate
使用格式修正。所有被測馬嘅 baseline 對 frozen snapshot 差異 ≤0.01（實際 drift
記錄 0），paired leaves 同原始逐馬差值另行保存。

Dev：**1,762 場（08-05 至 09-21）**，修正 72 匹。五個 whole-date dev folds
嘅 Gold／Good 全部無點估計回歸。四個 field-size cohort 亦無回歸。

通過 dev 正確性 guardrail 後，只做一次 terminal 確認。原 811 場 terminal：
排除已曝光 Tamworth 全 meeting 8 場、21 場 incomplete／tied results、11 場
runner alignment 不完整，剩 **771 場（09-22 至 10-12）**，修正 47 匹。
Tamworth R4 只解釋機制，唔加入 performance validation。

| 指標 | Dev baseline → candidate | Dev Δ 95% CI | Terminal baseline → candidate | Terminal Δ 95% CI |
|---|---:|---:|---:|---:|
| Gold | 21.5096% → 21.5664% | +0.0568pp [0, +0.1703] | 19.7147% → 19.7147% | 0pp [0, 0] |
| Good | 25.6527% → 25.6527% | 0pp [0, 0] | 26.5888% → 26.5888% | 0pp [0, 0] |
| Pass | 49.7162% → 49.7162% | 0pp [0, 0] | 49.6757% → 49.8054% | +0.1297pp [−0.2594, +0.6485] |
| 前三平均模型 rank（低為佳） | 4.1241 → 4.1226 | −0.00151 [−0.00284, −0.00038] | 4.0502 → 4.0480 | −0.00216 [−0.00520, +0.00086] |

Bootstrap：配對、按場重抽、2,000 次、seed 7。Terminal 四個馬群 cohort、五個
baseline 首選 SP cohort 嘅 Gold／Good 逐場都冇變；SP 只喺評分後 join 做分組。
**符合正確性修正嘅無顯著 primary 回歸要求，唔係 PRIMARY_WIN／RANKING_WIN。**

## Stability 高估同低估分開睇

Dev baseline 1,176 失手場中：

- **1,121 場**至少有一匹模型首兩揀落選，但 stability ≥60；共 1,460 匹。
- 呢 1,460 匹中，PQ evidence 標記 observed 1,378、fallback 82。
- **928 匹**實際上名馬被漏出模型 Top4，而且 stability <60。

成功對照 586 場中，亦有 128 匹首兩揀落選但 stability ≥60，及 115 匹漏出
Top4 嘅低 stability 上名馬。成功係 Gold 或 Good 聯集，所以仍可能有一部分錯選。

以上全部係 outcome-conditioned 描述。高 stability 落選唔等於 score formula 錯，
低 stability 上名亦唔足以證明缺少新訊號。呢輪只修可獨立證明嘅格式問題。
**大部分高分落選馬並非 fallback，不能靠修呢個 parser 解決所有失手。**

## 下一步設計假設

優先測「資料來源及適用性」，而唔係全局降 stability：

- 生涯有出賽、完整正式 entries 卻為 0：先查原始資料／解析分類，清楚分開
  「摘要證明大敗」同「完整往績足以評估質素」。
- 正式賽、試閘、race-level 背景、個體 proxy：分開記錄證據類型及有效樣本。
  一課舊試閘嘅相對高分，不能默認為已證明正式賽能力。
- 高分往績嘅今仗適用性：按途程、跑道、地況及 dated runs 審計，再預先登記
  少量獨立候選。過去「全部久休縮分／全部減 PQ」已失敗，唔重試同一規則。

呢啲尚未加入 live ranking。需要新來源或新轉換時，另做 PIT audit、單項 ablation
及時間驗證；本輪 terminal 已用於正確性確認，不能再拿來擇參。

## 產物／退回

- [實驗及重跑命令](../../experiments/EXP-20261013-02-au-decoded-form-correctness.md)
- `scratch/au_stability_format_20261013/audit.json`：dev 數字及逐場 stability 類型。
- `scratch/au_stability_format_20261013/terminal.json`：terminal 同完整個案重播。
- `scratch/au_stability_format_20261013/paired_leaves.json`：2,533 場凍結比較 leaves，約 29MB。
- `scratch/au_stability_format_20261013/baseline/`：修正前 scoring、engine_core、golden
  及 data-contract，保留原有其他 session 工作。
- 已按規定 record AU golden、重校 2,000 場健康基準、用生成器更新模型說明。
- 新增七項名次格式回歸測試；另將退役欄位測試改為固定基準情境，保留真實 CLI
  gate 及「只警告、唔攔發佈」斷言，唔改發佈 policy。
- 原始賽前 artifact 冇覆蓋，冇 commit／push／deploy。

驗證結果：`./檢查.sh --quick`、`./檢查.sh` 全部通過；凍結 paired leaves 重算 2,533 場，逐場指標全部同報告一致。完整 log：`scratch/au_stability_format_20261013/full-check.log`。
