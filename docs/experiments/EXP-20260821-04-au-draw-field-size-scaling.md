# EXP-20260821-04 按馬匹數縮放檔位修正

- **日期**：2026-08-21
- **平台**：AU
- **假設**：檔位訊號嘅強度取決於馬匹數（實測內↔最外差距：5–8 匹 1.6pp、
  9–11 匹 7.6pp、12–14 匹 10.7pp），但 98.4% 嘅 draw-bias cell 唔按馬匹數分層，
  所以 6 匹馬同 14 匹馬食同一個修正。按馬匹數縮放應該改善排名。
- **搜索過嘅舊記錄**：[EXP-20260821-03](EXP-20260821-03-au-pace-map-gradient.md)（本實驗嘅診斷來源）、
  memory `au-draw-baseline-mismatch`、`au-draw-granularity-earns-its-keep`
- **改到嘅檔案／組件**：`au_draw_walkforward_audit.py`（評估 harness，唔係 model code）。
  **live 引擎一行都冇改。**

## 零、跑之前先修 harness

`au_draw_walkforward_audit.py` 用緊 `expected = 1.0 / field_size` —— 即係
**pre-2026-08-16 嘅引擎**。live 引擎由嗰日起用 `_draw_pool_baseline`。
唔修就會攞候選同一個「唔係現行模型」嘅 baseline 比。

已補上 `_pool_baseline()`，同 `engine_core._draw_pool_baseline` 一致。門檻
（track+distance ≥10、track ≥30）本來就對得上。

順帶量到嗰個 shipped 修正自己嘅效果（`--legacy-baseline` 對照）：
holdout −0.0037 → **−0.0025**（好 +0.0012），dev 一樣。方向啱，幅度細 ——
同佢當初「correctness fix, not a performance claim」嘅定位一致。

## 配置
- **baseline**：現行公式，point-in-time 重建檔位矩陣
- **candidate**：同上 + `raw *= clamp(field_size / 10, 0.4, 1.5)`
  參考值 10 = 語料平均馬匹數（10.1），由**出賽組成**攞，唔係由結果擬合

## 數據
- **語料**：1,530 場 Logic → **1,411 場**對得上賽果（Archive/ 已包含，見 EXP-01）
- **holdout**：15%，未碰過
- **leakage 控制**：harness 逐日重建檔位訊號，每場只用**嚴格早過自己日期**嘅賽果

## 結果

判決依據 = 頭 5 位配對 AUC。關鍵 arm 係「point-in-time draw vs neutral」——
即係「有檔位訊號」對「pace_map 全部 60」。

| 配置 | dev | holdout | holdout 95% CI |
|---|---:|---:|---|
| 對照（舊 baseline） | −0.0045 | −0.0037 | [−0.0096, +0.0027] |
| **baseline（現行）** | **−0.0045** | **−0.0025** | [−0.0082, +0.0038] |
| **candidate（縮放）** | **−0.0054** | **−0.0027** | [−0.0091, +0.0036] |

候選喺 **dev 同 holdout 都差過 baseline**。另一個 arm（point-in-time vs 已存檔
live 分）一樣：dev −0.0068 → −0.0077，holdout −0.0007 → −0.0009。

場數指標同樣退步：pass −1.06 → −1.63、winT3 −0.71 → −0.99、Good位 −0.50 → −0.64。

## 檢查
- **leakage-audit**：PASS —— harness 本身就係 leakage-safe 設計（逐日重建，
  只用嚴格早過該場日期嘅賽果）。候選冇加新資料源，只改縮放。
- **golden_scoring**：冇郁（120 匹一致，因為 live 引擎冇改）
- **data_contract**：PASS
- **退步**：候選喺兩個 arm、dev 同 holdout、加場數指標，全部退步

## 結論

**REJECT，而且唔係邊緣。** 候選喺每一個切法都比 baseline 差。

點解會咁 —— 一個合理解釋：診斷（EXP-03）量嘅係「檔位對**入位率**嘅邊際效應」，
但排名要嘅係「檔位對**同場相對次序**嘅判別力」。放大大場次嘅修正，同時等於
放大嗰啲 cell 嘅噪音；而大場次本身 cell 嘅 sample 未必更足。診斷量到嘅差距係
真嘅，但佢唔轉化成排名收益 —— 呢個同 memory `au-cohort-gap-is-not-a-gain`
講嘅係同一件事，今次係第四次。

**仲有一個更大嘅發現，唔關候選事：** 三個配置嘅「point-in-time draw vs neutral」
dev **全部係負**（−0.0045 / −0.0045 / −0.0054）。即係**一個 leakage-free 嘅
檔位訊號，喺 dev 上比完全冇檔位訊號更差**。holdout 嘅 CI 全部跨過 0，所以
statistically 未算證實，但方向一致。live 矩陣睇落有用，可能係因為佢用晒
包括未來嘅賽果。呢個值得另開一個實驗查，唔應該塞入呢份。

**決定**：REJECT
**commit**：live 引擎未改。harness 嘅 baseline 同步修正 + 兩個對照 flag
（`--field-scale`、`--legacy-baseline`，兩個都預設 off）已 commit ——
留住係為咗下一個人唔使由零重做同一個實驗。

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
export PYTHONDONTWRITEBYTECODE=1
S=/tmp; R="$AU_RACING"

python3 au_runtime_failure_audit.py --archive-root "$R" \
  --results-csv "$R/AU_Historical_Raw_Race_Results.csv" \
  --dataset-json "$S/runtime_dataset.json" \
  --output-json "$S/rt.json" --output-md "$S/rt.md"

# baseline / candidate / 對照
python3 au_draw_walkforward_audit.py --dataset-json "$S/runtime_dataset.json" \
  --results-csv "$R/AU_Historical_Raw_Race_Results.csv"
python3 au_draw_walkforward_audit.py --dataset-json "$S/runtime_dataset.json" \
  --results-csv "$R/AU_Historical_Raw_Race_Results.csv" --field-scale
python3 au_draw_walkforward_audit.py --dataset-json "$S/runtime_dataset.json" \
  --results-csv "$R/AU_Historical_Raw_Race_Results.csv" --legacy-baseline
```
