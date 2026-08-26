# EXP-20260826-05 — 補抓、檔位、未用 leaf、同 HKJC 對照

**狀態：全部量完，冇一個過閘。三個結構性發現值得記低。**
**日期：** 2026-08-26 ・ **平台：** AU

## 1. `au_feature_ab` 個 `--min-depth` 會靜靜清空語料（已修）

`build_races` 讀 `source_compare.json` 攞 form depth。個檔唔存在時 `depth` 係空
dict，於是 `depth.get(name, 0) = 0 < min_depth(預設 4.0)` 對**每個場次**成立 ——
成份語料被隔走，輸出「0 場」，然後喺 `delta()` 度爆
`TypeError: 'NoneType' object is not subscriptable`。表面睇似「呢個特徵冇數據」。

修法：攞唔到深度資料就當「唔知」（`depth = None`）→ 唔篩，並且喺 stderr 出警告；
語料空就喺 `main()` 大聲死，唔好行落去爆一個意義不明嘅 TypeError。

## 2. 補抓歷史 `WinningTime` —— 唔可行，但揾到更好嘅來源，而佢一樣唔過閘

### 2a. 補抓本身唔可行

* `.sportsbet_cache` 4,824 個檔，**最舊 mtime 2026-08-09** —— 冇任何早過嗰日嘅
  HTML，所以重新 parse cache 補唔到歷史。
* 重新 fetch 會撞 [[au-cannot-backfill-measure-extraction-fixes]] 個陷阱：今日抓
  一個 2026-06 場次嘅 form 頁，見到嘅係**今日為止**嘅最近 10 仗；censor 走賽後行
  之後剩返嘅賽前仗數，比當年賽前抓少一大截。dossier 深度唔可比 = A/B confounded。

### 2b. 但結果 CSV 有更好嘅嘢 —— 而佢死咗

`AU_Historical_Raw_Race_Results.csv` 有一個 `Time` 欄，而且係**逐匹馬個別時間**：

| 期間 | 有 Time |
|---|---|
| 2025-08 → 2026-06 | **99–100%** |
| 2026-07 | 29% |
| **2026-08** | **0%** |

成因：`au_results_ingest.py:208` **硬寫 `"Time": ""`**。舊行係
`au_statistics_aggregator.py` 讀 `cols[9]` 寫落嘅。當 ingest 變咗主路徑（約
2026-07），成條欄位就死咗。reflector markdown 只 parse pos/num/horse/margin/sp，
本身冇時間，所以 ingest 補唔到 —— 要駁 Sportsbet 賽果頁先得。

### 2c. 由結果 CSV 重砌速度評分：更差

7,672 條有時間嘅賽果行、140 個 track×distance 標準（Formguide 版有 848）。
going 修正自驗合理（Good 4 −0.38、Soft 7 +1.22、Heavy 10 **+3.02** 秒）。

15 個配置（5 個變體 × k=0.25/0.5/1.0）：**冇一個過閘**，而且兩個**顯著負**
（`sf_best` k=1.0 holdout −0.0029 [−0.0058, −0.0001]；`sf_at_dist` k=1.0
−0.0036 [−0.0061, −0.0013]）。覆蓋 31.1%，同 Formguide 版差唔多。

**兩個獨立來源、兩套獨立構造，都停喺 ~30% 覆蓋而且都唔過閘。**
EXP-20260826-04 講「等覆蓋率升到 45% 再試」嗰個先驗要調低 —— 覆蓋唔係唯一問題。

## 3. 其餘抽咗冇讀嘅欄位

`12 Month` / `3rd Up` / `Turf` / `Season` / `Ave $` 全部嚟自**會賽後刷新嘅
career overview**，同已證實洩漏嘅 `J/H`（場內 AUC 0.850）、`WinRange`
（holdout +17.58pp）同一個 block。

我試過用「網站數字 vs 我哋 censor 後數到」去判斷，**個測試本身唔成立**：頁面
封頂 10 行，所以「網站大過我哋」對任何超過 10 仗嘅馬都成立。限制喺未撞上限嘅
13,589 匹重做：56.7% 網站數字較大，但「多出恰好 1 仗」只佔全體 **4.2%**
（多出 2–6 仗嘅一樣多）—— 即係大部分差異係頁面冇列晒，唔係今日嗰仗。
**分唔清 = 唔可以攞嚟 fit。** 照 `dist_place_rate` 嘅做法由 censor 過嘅往績行
自己數（新增 `pre12m_place_rate` / `pre12m_starts`）。

**結果：`pre12m_place_rate` 冇一個 k 過到 fold 閘。** 即係「近 12 個月上名率」
呢個訊號，`form_score`（AUC 0.5962）已經捉晒 —— 用一個更窄嘅窗口重數一次
冇加到嘢。呢個係 [[au-cohort-gap-is-not-a-gain]] 嘅又一例：先問模型係咪已經
另有路捉到同一件事。

## 4. 檔位（draw）應唔應該入排名？——**唔應該，但係真訊號**

結果 CSV 嘅 `Barrier`（要 `int(float(...))` 讀，佢存成 `"2.0"`），756 場：

| 檔位 | n | 上名率 | 馬匹數基準 | 超額 |
|---|---:|---:|---:|---:|
| 內 1–4 | 3,015 | 31.71% | 29.96% | **+1.75pp** |
| 中 5–8 | 2,893 | 28.45% | 29.21% | −0.76pp |
| 外 9+ | 2,203 | 20.88% | 23.60% | **−2.71pp** |

場內 AUC **0.5291**，單調。**訊號真，但太細**：4.5pp 嘅擴散 vs `rating_score`
嘅 23pp。而且加落排名試過三次都失敗 —— walk-forward（全負）、按馬匹數縮放
（REJECT）、今日 `race_shape` 復活（0.03/0.06/0.10 全部跨 0）。

**結論：唔入排名，但值得喺報告度講。** 一個 −2.71pp 嘅外檔劣勢係落注嗰陣真係
想知嘅嘢，而佢而家喺輸出度完全冇聲音。

## 5. AU 可以向 HKJC 學咩

| | HKJC | AU |
|---|---|---|
| 計分維度 | **7 個全部有權重** | 7 個入面 **2 個 0 權重** |
| leaf 用量 | — | **18 個 leaf 得 9 個入排名** |
| `class_score` | ✓ `class_advantage` | ❌ 2026-07-29 退役 |
| `consistency_score` | ✓ `stability` | ❌ 冇用 |
| `weight_score` | ✓ `class_advantage` + `horse_health` | ❌ 2026-07-30 退役 |
| 健康／風險 | ✓ `horse_health`（`risk_score`）| ❌ `health_score` 冇入分 |
| 課程操練 | ✓ `trackwork_trend_score` | ❌ 冇 |
| `race_shape` | **27.4%（最大維度）** | **0%** |

九個未用 leaf 逐個過主裁判（1,029 場，27 個配置）：**冇一個過閘**。但
`class_score` 係最接近嗰個 —— dev **+0.0016 / +0.0025 / +0.0029**、holdout
**+0.0014 / +0.0017 / +0.0039**，兩邊都**隨 k 單調上升**。呢個係「真訊號但功效
唔夠」嘅特徵形狀，而佢啱啱好就係 HKJC 有用而 AU 退役咗嗰個。

其餘：`distance_score` holdout 正但 dev 喺 k=1.0 轉負；`pace_map_score` dev 全負；
`weight_score` / `confidence_score` / `consistency_score` holdout 多數負。

⚠️ `distance_score` 要小心：佢由 `engine_line` 嘅「距離分佈 ⭐最佳 ← 今仗 ✅」
砌，語義同已證實洩漏嘅 `WinRange` 一樣。做咗 smoking-gun 檢查：698 匹「今日=最佳
路程」而且今日贏嘅馬，有 **18.1%** 喺 engine_line 度顯示今日路程賽前 0 勝 ——
即係個分佈冇系統性食咗今日嘅結果。唔算洩漏，但要入分之前要再做一次完整審計。

## 建議

1. **修 `au_results_ingest.py` 個 `"Time": ""`** —— 唔係為咗速度評分（嗰個唔過閘），
   係因為一個 99% 覆蓋嘅欄位靜靜變 0% 本身就係要修嘅嘢，而且將來想做任何時間
   相關研究都要佢。
2. **`class_score` 值得再追** —— dev 同 holdout 都單調向上，而且有 HKJC 嘅先例。
   等語料再厚啲重測。
3. **檔位入報告，唔入排名。**
