# EXP-20260821-03 `pace_map_score` 點解喺同場之內分唔開馬

- **日期**：2026-08-21
- **平台**：AU
- **類型**：診斷（未測試候選）
- **起因**：[EXP-20260821-02](EXP-20260821-02-au-gain-weight-joint-refit.md) 收尾發現
  `race_shape` 原始場內 SD 只有 **2.03**，gain 推到 headroom 上限都到唔到 ✅✅。
  結論係「問題唔喺 gain，喺 `pace_map_score` 本身」。呢個實驗查清楚點解。
- **搜索過嘅舊記錄**：`au-draw-granularity-earns-its-keep`、`au-draw-baseline-mismatch`、
  `au-neutral-display-scale-fix`、`au-one-sided-scales-that-are-correct`
- **改到嘅檔案／組件**：無（純診斷）

## 一、機制：佢係一個 4 級階梯

`pace_map_score = 60 + clamp(modifier, −9.43, +4.05)`，而 modifier 只由**檔位桶**決定：
`≤4 內檔` / `5–8 中檔` / `9–12 外檔` / `13+ 大外檔`。同場所有馬共用場地、距離、
馬匹數，所以場內唯一變量就係嗰 4 個桶。

實測（乾淨 point-in-time 語料，709 場）：

| 每場有幾多個唔同分值 | 場數 | 佔比 |
|---:|---:|---:|
| 1 | 3 | 0.4% |
| 2 | 135 | 19.0% |
| 3 | 336 | 47.4% |
| 4 | 235 | 33.1% |

- 平均每場 **10.1 匹馬只有 3.13 個唔同分值** → 每個分值孭 3.2 匹
- **96.6% 嘅馬同至少另一匹完全同分**
- 1 檔同 4 檔同分；4 檔同 5 檔唔同分
- 場內 SD **1.08**（leaf 層）

**任何顯示尺 gain 都拉唔開一個 4 級階梯。**

## 二、階梯係咪太粗？答案：唔係

桶**內**逐個檔位嘅入位率（766 場 / 8,161 匹，前 3 名）：

| 桶 | 檔位 | 入位率 | 95% CI |
|---|---:|---:|---|
| inside | 1 / 2 / 3 / 4 | 33.5 / 31.1 / 30.3 / 33.2% | 全部重疊 |
| middle | 5 / 6 / 7 / 8 | 31.4 / 30.5 / 26.0 / 26.2% | 全部重疊 |
| outside | 9 / 10 / 11 / 12 | 23.9 / 22.7 / 20.7 / 19.4% | 全部重疊 |
| wide | 13 / 14 | 16.6 / 17.5% | 重疊 |

**每個桶入面，最好同最差檔位嘅 CI 都重疊** —— 呢個樣本量之下冇桶內梯度。
桶**之間**就好乾淨：32.0% → 28.6% → 22.2% → 16.3%，單調。

**所以低 SD 係誠實嘅**，唔係缺陷。細分檔位（例如逐個檔位一個分）會加噪音唔加訊號。

## 三、真問題：桶係絕對檔位，但訊號強度取決於馬匹數

⚠️ 中途差啲得出錯結論：「middle 桶入面嘅相對外檔入位率 37.9%」睇落係大發現，
但 `middle` 桶入面嘅「相對外檔」＝**細場次**（8 匹馬嘅第 7 檔），而細場次入位率
機械上就係高（3/8 = 37.5% vs 3/14 = 21.4%）。同 `au-draw-baseline-mismatch`
嗰個陷阱一模一樣。控制馬匹數之後：

| 馬匹數 | 場數 | 基準 | 內檔 | 中檔 | 外檔 | 大外檔 | 內↔最外 | CI 分得開 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 5–8 | 172 | 42.0% | +0.7 | −0.9 | — | — | **1.6pp** | ❌ 重疊 |
| 9–11 | 325 | 30.0% | +3.8 | −2.0 | −3.8 | — | **7.6pp** | ✅ |
| 12–14 | 187 | 23.5% | +2.0 | +1.0 | −1.4 | −8.7 | **10.7pp** | ✅ |

三個 band 全部單調遞減。但**訊號強度差 6.7 倍**：細場次檔位幾乎唔緊要（而且
統計上分唔開），大場次係一個大訊號。

而引擎點做？`f_cat`（field_1_8 / 9_12 / 13_plus）**只用喺 global fallback**。
實測 `au_draw_bias_matrix.json` 嘅 cell 來源：

| 層 | cell 數 | 佔比 | 有冇按馬匹數分 |
|---|---:|---:|---|
| track + distance | 644 | 87.0% | ❌ |
| track 總體 | 84 | 11.4% | ❌ |
| global | 12 | 1.6% | ✅ |

**98.4% 嘅情況下，6 匹馬同 14 匹馬食同一個檔位修正。**

## 檢查
- **leakage-audit**：N/A（診斷，用賽後結果做描述性統計，冇入模型）
- **golden_scoring**：冇郁（冇改任何 code）
- **data_contract**：PASS

## 結論

`race_shape` 場內 SD 低係**兩個原因疊埋**：

1. 檔位本質上只分到 4 級 —— 呢個係對嘅，桶內冇梯度（已驗）
2. 修正幅度冇按馬匹數縮放 —— 呢個係**可以改善嘅缺口**

第 1 點解釋咗點解 EXP-02 嘅 gain 重擬救唔到佢：拉闊一個 4 級階梯只係把噪音一齊
拉闊。第 2 點係一個有數據支持嘅候選。

**候選（未測試）**：按馬匹數縮放檔位修正 —— 5–8 匹收窄（實測訊號 1.6pp 且 CI 重疊）、
12+ 匹放大（實測 10.7pp）。注意呢個**唔會**提高場內 SD 太多（細場次會更平），
但會令大場次嘅檔位訊號更準 —— 目標係準確度，唔係 band 靚。

⚠️ 呢個方向有前科：`au-draw-baseline-mismatch` 嗰次修好咗一個真嘅馬匹數混淆
但**過唔到閘**。所以呢個候選一定要行足 `model-regression-gate`，唔可以因為
「機制上明顯應該咁」就落。

**決定**：診斷完成。候選已經跑閘 → **REJECT**（見 [EXP-20260821-04](EXP-20260821-04-au-draw-field-size-scaling.md)）
**commit**：診斷記錄已 commit；model code 未改

## 重跑
```bash
# 階梯粒度（每場幾多個唔同分值）
python3 - <<'PY'
import json,statistics,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,".agents/skills/shared_racing/scripts"); sys.path.insert(0,".")
from corpus_paths import logic_files
from wongchoi_paths import AU_RACING
paths=[p for p in logic_files(AU_RACING) if Path(p).parent.name[:10]>="2026-08-05"]
d=Counter()
for p in paths:
    j=json.load(open(p,encoding="utf-8"))
    v=[round(float(h["python_auto"]["feature_scores"]["pace_map_score"]),2)
       for h in (j.get("horses") or {}).values()
       if "pace_map_score" in (h.get("python_auto",{}).get("feature_scores") or {})]
    if len(v)>=3: d[len(set(v))]+=1
print(sorted(d.items()))
PY

# 桶內梯度 + 控制馬匹數（用 AU_Historical_Raw_Race_Results.csv 嘅 Barrier + Pos）
# 見本檔第二、三節嘅表；腳本喺 scratchpad，重寫十幾行就有。
```
