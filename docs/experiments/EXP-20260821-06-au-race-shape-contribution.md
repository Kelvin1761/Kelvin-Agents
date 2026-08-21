# EXP-20260821-06 `race_shape`（13.5% 權重）到底有冇貢獻

- **日期**：2026-08-21
- **平台**：AU
- **假設**：`race_shape` 喺回測入面睇落有貢獻，但佢嘅價值大部分嚟自
  **檔位矩陣含住被評分嗰場之後嘅賽果**。用乾淨 point-in-time 語料量，佢應該冇貢獻。
- **搜索過嘅舊記錄**：[EXP-04](EXP-20260821-04-au-draw-field-size-scaling.md)（發現呢件事嘅起點）、
  [EXP-03](EXP-20260821-03-au-pace-map-gradient.md)、`REFIT_PLAN.md` 2026-08-04
  （`pace_map_score` 同實際走位 ρ = **−0.017**，明寫「值得跟進嘅係：我哋個 pace_map
  到底喺度量緊乜」——呢份就係嗰個跟進）、memory `au-micro-families-mostly-earn-keep`、
  `au-draw-granularity-earns-its-keep`
- **改到嘅檔案／組件**：無。**live 引擎一行都冇改。**

## 配置
- **baseline**：出廠 gains + `MATRIX_WEIGHTS`
- **candidate**：`race_shape` 權重歸零，其餘五個按比例歸一
  `{stability .38051, pace_perf .12205, jockey_trainer .26535, class_weight .13919, track .0929}`

## 數據
- 1,413 場（Archive/ 已包含）；`au_matrix_refit verify` max|Δ| 0.0108 已過
- 語料按日期排序，**2026-08-05 起 611 場係乾淨 point-in-time**
  （之前嗰批 2026-07-17 賽後重新評分過 —— 見 `au-archive-rescored-post-race`）
- 逐 fold 評估，唔只睇合計

## 結果

### 全語料（dev/holdout 標準切法）—— 符號打交

| | dev（1,201 場）| holdout（212 場）|
|---|---:|---:|
| gold | −0.42 | +0.00 |
| good_pos | −1.00 | +0.94 |
| champ | −1.50 | +0.94 |
| winT3 | −0.42 | +2.36 |
| mrr | −1.01 | +0.85 |

dev 話「剷咗變差」，holdout 話「變好」。呢個係「冇可靠效果」嘅典型形狀 ——
但拆開兩半語料睇就清楚咗。

### 拆開兩半：剷走 `race_shape` 之後，5 個 fold 之中好／差

| 指標 | 舊語料（802 場，矩陣含未來） | 乾淨 PIT（611 場） |
|---|---|---|
| gold | 1 好 / **3 差**（合計 −1.37）| **4 好 / 1 差**（+0.98）|
| good_pos | 2 / 2（−1.37）| 2 / 2（+0.16）|
| pass | 2 好 / 3 差（−1.12）| 2 好 / 3 差（−0.16）|
| champ | 1 好 / **4 差**（−2.00）| 2 好 / 1 差（+0.00）|
| winT3 | 3 好 / 2 差（−0.25）| 2 好 / 3 差（+0.33）|
| mrr | 1 好 / **4 差**（−1.40）| **4 好 / 1 差**（+0.14）|
| ndcg5 | 1 好 / **4 差**（−0.70）| **4 好 / 1 差**（+0.27）|

**舊語料：剷咗明顯變差。乾淨語料：剷咗打和，甚至好少少。**

### 同 EXP-04 對得上

EXP-04 用完全獨立嘅方法（`au_draw_walkforward_audit`，逐日重建矩陣，每場只用
嚴格早過自己日期嘅賽果，1,411 場）得出：「有檔位訊號 vs pace_map 全部 60」嘅
dev 頭 5 位配對 AUC 三個配置**全部係負**（−0.0045 / −0.0045 / −0.0054）。

兩條獨立線指同一個方向。

## 檢查
- **leakage-audit**：**呢份實驗本身就係一個 leakage 調查。** 洩漏路徑：
  `au_draw_bias_matrix.json` 由完整 `AU_Historical_Raw_Race_Results.csv` 重建。
  **live 運行冇問題**（評分嗰刻未來賽果根本未存在），但**任何用現行矩陣重新
  評分舊場次嘅回測都受污染**。2026-07-17 嗰次全語料重評分正正就係咁做。
- **golden_scoring**：冇郁（120 匹一致，live 引擎冇改）
- **data_contract**：PASS

## 結論

**假設方向成立，但未夠證據落刀。**

證據支持「`race_shape` 喺回測入面嘅價值大部分係矩陣洩漏造成」：
兩條獨立方法同一方向，而且舊／乾淨兩半符號相反 —— 呢個係洩漏嘅指紋，
唔係隨機噪音（隨機噪音唔會咁齊整咁跟住「語料乾淨與否」分邊）。

**但唔可以就咁剷咗佢**，三個理由：

1. 乾淨語料得 **611 場、16 日**，而且係鄉道場次為主（Beaudesert / Canberra /
   Murtoa / Murwillumbah / Sale）—— population 唔代表全年
2. 「打和甚至好少少」唔係「明顯更好」。合計 gold +0.98 = 611 場入面約 6 場
3. 剷一個 13.5% 權重嘅維度係大改動，需要更強證據

**兩個混淆未排除**：兩半語料唔止洩漏唔同，時段同賽事組成都唔同，引擎版本亦有差異。
單靠呢個對比分唔開「洩漏」同「population」。EXP-04 個 walk-forward 冇呢個混淆
（同一批場次、只換矩陣建法），佢一樣係負 —— 所以洩漏解釋較強，但未算證實。

**決定**：NEEDS MORE TESTING
**commit**：live 引擎未改；只 commit 記錄

## 立即可用嘅結論（唔使等）

**唔好信任何用 2026-08-05 之前語料跑嘅檔位相關 A/B。** 嗰批場次嘅
`pace_map_score` 係用含未來賽果嘅矩陣算出嚟。`au-draw-granularity-earns-its-keep`
（per-track 細 cell 贏）就係喺舊語料上量嘅 —— 應該喺乾淨語料重量。

## 幾時重測

等乾淨 point-in-time 語料儲夠約三個月（含 metro 賽事），用同一個 driver 重跑。

## 重跑
```bash
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
export PYTHONDONTWRITEBYTECODE=1
S=/tmp
python3 au_dump_engine_leaves.py --out "$S/leaves_fixed.json"
python3 au_matrix_refit.py verify --data "$S/leaves_fixed.json"

# ablation 權重
python3 -c "
import json,sys; sys.path.insert(0,'.')
from au_racing_engine.scoring import MATRIX_WEIGHTS
r={k:v for k,v in MATRIX_WEIGHTS.items() if k!='race_shape'}; t=sum(r.values())
json.dump({k:round(v/t,5) for k,v in r.items()}, open('$S/w_no_raceshape.json','w'))"

python3 au_matrix_refit.py compare --data "$S/leaves_fixed.json" \
  --weights "$S/w_no_raceshape.json"

# 逐 fold + 拆兩半語料（driver 見本檔；用 R.Dataset / ds.evaluate(ab, lo, hi)，
# 乾淨 PIT 切片 = date >= 2026-08-05，喺 leaves_fixed.json 係 index 802 起）
```

---

## 附錄（2026-08-22）：改用正確嘅污染分界線之後 → **KEEP**

上面用 `2026-08-05` 做「乾淨」界線係**錯嘅**。真正界線係 **`2026-08-09`**：

- `au_draw_bias_matrix.json` 係一個**靜態 commit 檔案**，最後重建 2026-08-09，
  **冇任何排程會重建佢**
- `au_dump_engine_leaves.py` 用 **live 引擎重新評分**舊場次（`RacingEngine(...)`），
  即係食現行矩陣

所以 1,413 場之中 **1,010 場（71.5%）**嘅檔位分係用含住自己結果嘅矩陣算，
只有 **403 場**係真正冇洩漏。

### 剷 race_shape（五維按比例歸一 + 濕地 overlay ×1.1260）

| 切片 | gold | good_pos | pass | champ | winT3 | mrr | ndcg5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 污染 1,010 場 | −0.89 | −1.29 | −1.29 | −1.39 | −0.20 | −0.95 | −0.48 |
| **真乾淨 403 場** | **+0.74** | **+0.99** | **+1.24** | −0.25 | **+0.99** | **+0.02** | **+0.38** |

真乾淨切片逐 fold（4 個）：`gold 2/1`、`good_pos 2/1`、`pass 2/1`、`winT3 2/1`、
`ndcg5 3/1`、`mrr 2/2`、`champ 1/1` —— **冇一個指標輸多數**。

### 三條獨立證據

1. `au_draw_walkforward_audit`（逐日重建矩陣，1,411 場）：「有檔位訊號 vs
   pace_map 全部 60」嘅 dev 頭 5 位配對 AUC 三個配置全部負（EXP-04）
2. 污染／乾淨兩半符號完全相反 —— 噪音唔會咁齊整跟住語料乾淨度分邊
3. **喺污染語料上 fit 出嚟嘅「重 fit 共識權重」，喺乾淨語料上差過簡單按比例歸一**
   （good_pos 1/3、champ 1/3、mrr 1/3）。如果洩漏結構唔存在，fit 落去唔會反而變差。

### 濕地 overlay 要一齊調

剷走一個低散開度維度會令剩低嘅主導 → ability 場內 SD **5.3960 → 6.0759（×1.1260）**。
濕地 overlay 係按 ability spread 校準，所以要同步 ×1.1260
（`WET_FORM_FEATURE_SCALE` 13.19→14.852、`WET_FORM_MAX_ABS` 5.49→6.1818）。
實測調埋好過唔調：`pass +0.74→+1.24`、`winT3 +0.50→+0.99`、`mrr −0.18→+0.02`。
`test_neutral_display_scale` 個累積係數守衛已接落去（× 1.1260）。

### 副作用：Grade 標籤會位移

全語料 ability 平均只 +0.34，但散開度加闊，所以 band 分佈變：
`C+ −3.5pp`、`B+ +1.9pp`、`B +1.1pp`、`A- +0.9pp`、`E +0.9pp`。
**「B-」前後唔完全同一個意思**，讀報告要習慣返。

考慮過重新校準 `GRADE_THRESHOLDS` 令各級佔比不變，**否決**：算出嚟會令
`S+/S/S-` 全部壓成 87.3（頂端馬匹數唔夠分），比溫和位移更差；而且會變成
同一次改動塞兩個假設。

### 唔改嘅嘢

`race_shape` 留喺 `MATRIX_FORMULAS`，所以照出報告，renderer 自動標
「（參考·不入排名）」—— 同 `form_line` 一樣嘅待遇。報告層零改動。

### 連帶要改嘅 test（三個，全部係佢哋做緊嘢）

- `test_signal_map`：`MATRIX_KEYS − MATRIX_WEIGHTS` 由 `{form_line}` 變
  `{form_line, race_shape}`
- `test_neutral_display_scale`：累積係數接 × 1.1260
- `test_shape_interaction_audit`：調 `pace_map_score` 再也唔會改綜合分 ——
  assert 反轉，用嚟釘死「呢個 audit 而家量嘅係報告訊號」
- `test_failure_cause_attribution`：`matrix_field_delta_by_formal_band` 冇
  `race_shape` key 係正確行為（佢只覆蓋計分維度）

### ⚠️ 證據基礎同重驗條件

403 場、約一個月、鄉道場次偏多。**等乾淨語料儲夠三個月（含 metro）要用同一個
driver 重驗**，如果反轉就 rollback（加返 `"race_shape":0.13485` 同還原兩個
WET_FORM 常數）。

**決定**：**KEEP**（由 NEEDS MORE TESTING 改判）
