# 矩陣重 fit —— 要跑嘅嘢（2026-08-03 記錄）

呢份係**未跑**嘅計劃書。所有數字都係量過嘅，所有命令都係現成嘅。

## 點解要 refit（前提喺今日先成立）

之前判斷「前提唔成立」係啱嘅 —— 當時 `pace_figure` 實際覆蓋率係 **0%**（PF 寫咗落一個冇 leaf 讀嘅 key）。修好之後前提成立咗：

| leaf | 現有數據源 | 重抽之後 |
|---|---|---|
| `pace_figure_score` | 50% | **96%** |
| `sectional_score` | 98% | **34%** |
| `trial_score` | 71% | 71%（修好之前係 7%）|

現行 `MATRIX_WEIGHTS` 係喺**現有數據源嘅分佈**上 fit 出嚟。搬去一個 `sectional`
剩返三分一、`pace_figure` 翻倍嘅語料上直接用，本身冇道理。

## 語料

    /tmp/…/scratchpad/sb_archive        94 個場次 / 836 場 / 8,899 個評分行
    往績深度 ≥4 仗/匹 嘅可比子集         604 場   ← refit 用呢個
    深度 <4 嘅                          166 場   ← 唔好溝埋，見下

**深度分組唔可以取消。** Sportsbet 每匹馬只出最近十幾仗，場次愈舊，賽前往績
愈少（2026-08 有 8.8 仗/匹，2025-08 只得 1.6）。溝埋一齊 fit，等於 fit
「數據可得性隨日期變化」。

## 要跑嘅次序

    au_dump_engine_leaves.py --out <leaves>.json
    au_matrix_refit.py verify      --data <leaves>.json   # ← 一定要先跑
    au_matrix_refit.py gains       --data <leaves>.json
    au_matrix_refit.py refit       --data <leaves>.json
    au_matrix_refit.py walkforward --data <leaves>.json
    au_matrix_refit.py compare     --data <leaves>.json --weights <new>.json

紀律（全部已經有紀錄，唔好重新發明）：
* **取閘後候選嘅逐維度中位數（共識），唔取 argmax。** argmax 實測 dev
  good_pos +3.80 但 holdout pass_any1 −5.61。
* dev 85% / holdout 15%（依時間），dev 內部 5 fold 閘。
* **一定要行 `map_features_to_matrix_scores`** —— 漏咗 `MATRIX_DISPLAY_GAINS`
  會得出相反結論（試過）。
* 兩個要一齊郁嘅：**wet overlay**（直接加落 ability，要跟 ability 散佈）同
  **grade thresholds**（純報告文字，唔好為咗好睇而回調）。

## 一齊放入搜索空間嘅候選新維度

呢兩個**單獨有訊號但加落去冇改善**（fold 閘過唔到）。加唔到 ≠ 喺一個重新
分配過嘅權重下加唔到 —— 所以放入 refit 嘅搜索空間，唔好當加數項。

| 候選 | 場內 AUC | 同現有 leaf 嘅重疊 | additive A/B |
|---|---|---|---|
| `ave_prize` 平均獎金 | **0.613** | 同 `class_score` **+0.001** | ❌ 3/5 fold |
| `dist_place_rate` 同路程上名率 | **0.588** | — | ❌ 2/5 fold |
| `jh_pre_place_rate` 人馬配搭（乾淨版）| 0.568 | — | 未試（覆蓋薄）|

兩個都**由我哋自己過濾過嘅賽前往績行**砌，唔用網站總結欄位 —— 構造上唔會中毒。
實作喺 `au_unused_field_power.runner_features()`。

## 順便要處理嘅：三個喺 0.5 以下嘅現有 leaf

    track_score      0.487
    sectional_score  0.469
    weight_score     0.463

**唔好手動剔走。** 喺線性組合入面負相關唔一定係淨噪音，而且 `sectional` 已經
試過三次改、三次喺 holdout 輸。正路係喺 refit 度畀佢哋自己收斂 —— 或者用
`compare` 餵一份把三個歸零嘅 weights，量咗先講。

## ⛔ 洩漏黑名單 —— 呢啲欄位唔可以入任何歷史 fit

| 欄位 | 點解 |
|---|---|
| `J/H`（網站個 `Jockey N: w-p-s`）| **包含今日嗰仗**。Silent Shares `1: 0-0-1`，騎師賽前策騎 0 次，今日第三 |
| `Win Range` | **包含今日嗰仗**。41 匹今日贏、賽前未喺呢距離贏過嘅馬，今日路程**逐匹**都係範圍端點 |

⚠️ **加門檻（例如「至少兩次」）解決唔到 J/H** —— 五次入面仍然有一次係今日。
唯一正解係由自己嘅往績行重新數（`jh_pre_place_rate` 就係咁做）。

⚠️ 同一版嘢 provenance 係**混嘅**：`Career` / `Prizemoney` / `Ave $` 賽前乾淨
（首戰馬今日贏咗仍然顯示 `0: 0-0-0` / `$0`），`J/H` / `Win Range` 賽後。
**逐個欄位驗，唔可以整版通過。**

## 已經答完、唔使再擺入 backlog 嘅

* **段速時間點讀最好** —— 四種替代讀法全部輸畀現行嘅平均值
  （best 0.527 / consistency 0.519 / at_distance 0.517 / trend 0.497 vs mean 0.559）。
  段速數據嘅價值出咗喺**覆蓋率**，唔係公式。
* **試閘應唔應該只用喺淺資歷馬** —— 方向啱但幅度細（<5 仗 0.537 vs 5+ 仗
  0.518），而試閘段速本身係噪音（0.512 / 0.515）。唔值得建。
* **1st/2nd/3rd Up** —— 現時明文「不入分」，而量到只有 0.542。維持原判。

## ⚠️ 已知 confound：騎練 `(LY:)` 係**抓取當日**嘅 12 個月紀錄

我哋今日（2026-08-03）抓個人頁，攞到嘅係**今日為止**嘅 12 個月數字。歷史場次
用返呢個數，即係個窗口向前偷睇咗：refit 語料 2026-01-24 → 2026-08-01，最舊嗰批
偷睇約 6 個月，不過 70 個場次入面 58 個係 2026-04 之後（≤4 個月）。

同 `J/H` 嗰種洩漏**性質唔同**：練馬師 12 個月紀錄係幾百仗嘅聚合，今日呢仗只佔
約 1/400，唔係「答案本身」。但佢**仍然唔係時點正確**，而且：

* **對數據源對比嚟講係偏袒 Sportsbet 嘅** —— 現有 archive 嗰邊嘅 LY 係當年
  賽前抓嘅，時點啱。所以 `jockey_score` / `trainer_score` 嘅改善有一部分係
  呢個 confound，唔可以全部當成數據源贏。
* 對 refit 嚟講全語料一致，影響細啲，但要記住。

**驗法**：修好之後 `jockey_score` 嘅場內 AUC 如果由 0.565 跳到 >0.65，就要
懷疑；0.57–0.60 屬合理。（Sportsbet 冇提供歷史時點嘅騎練統計，所以呢個補唔到，
只可以記住同量。）

## ✅ 已經做完（2026-08-03 通宵）

1. 騎練 cache 建立咗（200 個人物）→ `(LY:)` token 填充率 **81.0%**
2. 馬匹索引由幾百升到 **5,583 匹**，94 個場次全部重寫過
3. 全部重新評分（94/94，0 失敗）+ 重跑對比

**量到嘅效果 —— leaf 升咗，但排名冇升：**

| | LY 修前 | LY 修後 |
|---|---|---|
| `jockey_score` 場內 AUC | 0.565 | **0.589**（可比對數 6,353 → 10,651）|
| `trainer_score` | 0.544 | **0.571**（4,612 → 7,744）|
| `ability_score` 綜合 | 0.620 | **0.626** |
| 首選＝頭馬 | 141 | **134** ↓ |
| 前三精準 | 41.6% | **41.4%** ↓ |

⚠️ **呢個係 refit 嘅直接理據，而家係量到嘅唔係推論嘅**：leaf 判別力升咗，
但排名跌咗，因為權重係喺**較弱嗰個版本**嘅分佈上 fit 出嚟。數據改善咗，
配權冇跟住改。

`verify` 喺新語料通過（604 場 / 6,228 匹，max|Δ| 0.0083，>0.01 係 0），
所以 replica 對得住引擎，可以信搜索結果。

`gains` 喺新分佈上郁得好犀利 —— `class_weight` **+73.7%**、`track` +29.3%、
`pace_perf` **−28.0%**。呢個獨立佐證咗 leaf 分佈真係變咗。
（⚠️ gain 同 weight 要一齊郁，唔可以淨係換 gain。）

## 跑之前要先做完嘅

1. 騎練 cache 補完（`AU_Sportsbet_People_Cache.json`），`(LY:)` token 填返
2. 用完整馬匹索引重跑 fact anchors（賽績線覆蓋會升）
3. 重新評分 + 重跑 `au_source_compare.py`

呢三樣做完先 dump leaves —— 否則 refit 會喺一個 `jockey_score` 得 63%、
`formline_score` 得 69% 嘅殘缺分佈上做。
