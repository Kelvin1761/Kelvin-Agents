# 矩陣重 fit —— **已經跑咗（2026-08-03）**


## 結果：共識權重過晒閘，已經 apply

    出廠 → 共識
    stability      0.35364 → 0.38232   (+8%)
    pace_perf      0.22416 → 0.14407   (−36%)  ← 裝住 sectional（AUC 0.469 反向）
    race_shape     0.07948 → 0.11502   (+45%)
    jockey_trainer 0.17251 → 0.19149   (+11%)
    class_weight   0.06375 → 0.07337   (+15%)
    track          0.10646 → 0.09373   (−12%)

| 閘 | 要求 | 實際 |
|---|---|---|
| `verify` | 必須通過 | ✅ max\|Δ\| 0.0083，>0.01 係 0 |
| walkforward | ≥4/5 窗口 | ✅ **5/5** |
| holdout 主指標 | ≥2/3 向上 | ✅ t3prec +3.66、winT3 +9.89、champ 0.00 |
| 全樣本 604 場 | — | ✅ **11/11 指標改善** |

全樣本：winT3 +3.97、any2 +2.81、mrr +2.08、champ +1.82、ndcg5 +1.76、
t3prec +1.55、gold +1.32、compet +1.66、blowout −0.17（少咗 blowout 係好事）。

**前三精準 41.72% → 43.27%**，而現有數據源係 42.0% —— 由落後變成領先。

argmax 對照組（**冇 ship**）：holdout gold −3.30、champ −5.49、mrr −3.68 ——
第三次重現同一個 overfit 型態，所以共識唔取 argmax 呢條規則再次成立。

搜索嘅 baseline 同 production `MATRIX_WEIGHTS` **逐個數字對得上**，
所以唔係同一個影子 baseline 比。

跨 5 個窗口嘅共識同主共識逐維度差距 ≤0.005 —— 收斂本身先係證據，
唔係任何單一次搜索。

**知會埋郁咗嘅嘢**：場內 pure_7d SD 由 4.4085 收窄到 3.7344，所以 wet overlay
乘 ×0.8471（scale 15.90→13.47、clamp 6.62→5.61）。呢個係量出嚟嘅比例。
`test_neutral_display_scale.py` 嗰個 lockstep 測試**捉到**我冇更新 —— 佢做嘢。

---

## 以下係跑之前嘅計劃（保留做紀錄）

## 點解要 refit（前提喺今日先成立）

之前判斷「前提唔成立」係啱嘅 —— 當時 `pace_figure` 實際覆蓋率係 **0%**（PF 寫咗落一個冇 leaf 讀嘅 key）。修好之後前提成立咗：

| leaf | 現有數據源 | 重抽之後 |
|---|---|---|
| `pace_figure_score` | 50% | **96%** |
| `sectional_score` | 98% | **34%** |
| `trial_score` | 71% | 71%（修好之前係 7%）|

現行 `MATRIX_WEIGHTS` 係喺**現有數據源嘅分佈**上 fit 出嚟。搬去一個 `sectional`
剩返三分一、`pace_figure` 翻倍嘅語料上直接用，本身冇道理。

## ❌ 第二次 refit（96.8% LY 覆蓋）—— 過唔到閘，**冇 ship**

騎練覆蓋由 87% 升到 97%、LY 填充率 81.0% → **96.8%** 之後再 refit 一次。
baseline 係已經 ship 咗嘅 v1 共識權重。

| 閘 | 要求 | 實際 |
|---|---|---|
| walkforward | ≥4/5 | **3/5** ❌ |
| holdout | 主指標 ≥2/3 向上 | winT3 −3.30、champ −2.20、t3prec −0.37 ❌ |

dev 睇落靚（winT3 +3.31、champ +1.17），holdout 反轉 —— 典型 overfit 型態。
**結論：v1 權重已經食晒呢個語料嘅收益，再 fit 係喺度 fit 噪音。**

搜索出嚟嘅共識（**唔會用**，記錄低）：
`{"stability":0.42408,"pace_perf":0.09207,"race_shape":0.15358,"jockey_trainer":0.19579,"class_weight":0.06526,"track":0.06922}`

## ✅ 但同一組權重之下，騎練數據本身係顯著進步

`sb_refit`（81% LY）vs `sb_v2`（96.8% LY），**權重完全一樣**，604 場配對：

| 指標 | 新贏 | 舊贏 | p | |
|---|---|---|---|---|
| **Good 位置** | 21 | 3 | **0.0003** | ✅ |
| **Good any2** | 24 | 10 | **0.024** | ✅ |
| 頭馬入前三 | 21 | 11 | 0.110 | — |
| 前三命中格數 | **799** | 776 | +23 | |

**呢個先係值得留意嘅結果**：`Good 位置` 正正係之前以為「落後現有源」嗰個指標，
補完騎練數據之後喺同一組權重下顯著改善。**改善嚟自數據，唔係嚟自權重。**

要 ship 嘅嘢已經 ship 咗 —— `AU_Sportsbet_People_Cache.json`（651 個人物）
喺 Drive 上，將來每次跑都會用到，唔使改 code。

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

## ⚠️ `ave_prize` 過咗閘，但**建議唔好而家 ship**

理由唔係佢差，係個 holdout 已經唔乾淨：

嗰 91 場 holdout 今日已經被睇過**四次** —— v1 refit、候選維度測試（兩個特徵、
多個權重）、反向 leaf 測試（三個變體）、v2 refit。每睇一次，佢作為「未碰過」
嘅價值就少一截。一個 dev +0.65 / w=0.05 嘅邊際結果，唔應該靠一個已經被
反覆查詢嘅 holdout 落決定。

而且今日兩個獨立訊號都指向同一件事：
* v2 refit（更好數據）dev 靚、holdout 反轉 → 呢個語料已經榨到盡
* 今日所有**真**收益都嚟自修好入到 leaf 嘅數據，唔係嚟自調權重

**建議**：`ave_prize` 留住做**下一批新場次**嘅第一個測試對象 —— 嗰陣個
holdout 係真.未碰過。實作要改引擎（由 `Ave $` 砌 field-relative leaf、
入 `MATRIX_FORMULAS`、調 `MATRIX_WEIGHTS`），唔係改個數字。

## 候選新維度 —— 測完（2026-08-03）

**當加數項全部唔過閘，但當維度就唔同** —— `au_feature_ab.py` 試 `ability + k·z`
（其他維度權重不變），`au_candidate_dimension.py` 試真正加維度（新維度攞 w，
其餘縮到 1−w）。兩者數學唔同，結論唔同。

| 候選 | 場內 AUC | additive | 做維度 |
|---|---|---|---|
| `ave_prize` | 0.613 | ❌ 3/5 | ✅ **w=0.05**：dev 4/5、holdout t3prec +1.47 / winT3 +3.30 / champ +1.10 |
| `dist_place_rate` | 0.588 | ❌ 2/5 | ⚠️ w=0.08：holdout t3prec +2.56 但 **winT3 −1.10**，而 dev winT3 本身係 0.00 |
| `jh_pre_place_rate` | 0.568 | 未試 | 未試（覆蓋薄）|

⚠️ **揀權重嘅方式決定結論。** 第一次用 dev-argmax（w=0.18），holdout 出
champ −4.40、good_pos −5.49；改用保守 w=0.05 三個主指標全正。**同一個特徵。**
呢個就係「共識唔取 argmax」喺特徵層嘅同一課。

⚠️ `ave_prize` 觸發咗「holdout 升幅大過 dev」警報 → 照規矩人手覆驗：69 匹首戰馬
今日跑咗（有啲贏咗）仍然 `Prize $0`。**乾淨。** 警報係故意嘈過頭。

**要 ship `ave_prize` 需要真正改引擎**（由 `Ave $` 砌一個 field-relative leaf、
入 `MATRIX_FORMULAS`、調 `MATRIX_WEIGHTS`），唔係淨改一個數。

## （舊）一齊放入搜索空間嘅候選新維度

呢兩個**單獨有訊號但加落去冇改善**（fold 閘過唔到）。加唔到 ≠ 喺一個重新
分配過嘅權重下加唔到 —— 所以放入 refit 嘅搜索空間，唔好當加數項。

| 候選 | 場內 AUC | 同現有 leaf 嘅重疊 | additive A/B |
|---|---|---|---|
| `ave_prize` 平均獎金 | **0.613** | 同 `class_score` **+0.001** | ❌ 3/5 fold |
| `dist_place_rate` 同路程上名率 | **0.588** | — | ❌ 2/5 fold |
| `jh_pre_place_rate` 人馬配搭（乾淨版）| 0.568 | — | 未試（覆蓋薄）|

兩個都**由我哋自己過濾過嘅賽前往績行**砌，唔用網站總結欄位 —— 構造上唔會中毒。
實作喺 `au_unused_field_power.runner_features()`。

## 三個 0.5 以下嘅 leaf —— 測完，**剷唔得**（2026-08-03）

| 變體 | holdout |
|---|---|
| 剷 sectional | t3prec −2.56、winT3 −3.30 |
| 剷 track 維度 | t3prec −0.73、winT3 −3.30（**dev 睇落 3↑/0↓**）|
| 兩個都剷 | t3prec −3.30、winT3 **−6.59** |

線性組合入面負相關唔一定係淨噪音。refit 已經畀咗校準版答案：`pace_perf` −36%
（唔係 0）。工具：`au_unhealthy_leaf_test.py`。

⚠️ 更正：**`weight_score` 根本唔喺 `MATRIX_FORMULAS` 入面**，佢個 0.463 一分錢
都唔使畀。`track_score` 先係大件事 —— 佢**就係成個 `track` 維度**（9.4% 權重）。

## （舊）順便要處理嘅：三個喺 0.5 以下嘅現有 leaf

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

## 2026-08-04 —— 維度**內部**權重審查（#3，全部 REJECT）

第一次查 `MATRIX_FORMULAS` 入面每個維度內部嗰組 leaf 權重。`au_matrix_refit.py`
一直只調維度之間嘅 `MATRIX_WEIGHTS`，內部從來冇搜過。harness：
`au_inner_weights.py`（604 場、dev 513 / holdout 91 依時間切、5 fold 閘、
consensus 唔係 argmax、主指標 Gold + Good位、守門 t3prec + winT3）。

只有三個維度真正有得調（`race_shape` / `track` 單 leaf ×1.0，`class_weight`
單 leaf ×0.70，`form_line` 維度權重 0.000）：

| 維度 | 現行 | consensus | dev+holdout | SD 對照 | walk-forward |
|---|---|---|---|---|---|
| `stability` | form .60 / cons .40 | .65 / .35 | 全部升 | ✅ 過 4↑/0↓ | **5/5** |
| `jockey_trainer` | j .28 / t .20 / fit .52 | .333/.286/.381 | 全部升 | ✅ 過 2↑/0↓ | **3/5** ❌ |
| `pace_perf` | pf .759 / sec .194 / tr .047 | — | 冇候選過閘 | — | — |

**三個全部冇 ship。** 逐個講點解：

* **`pace_perf`** —— 231 個候選冇一個過 dev + 5 fold。現行比例守得住。
  （順帶答返一個舊問題：`sectional_score` AUC 0.469 反向，但佢個 0.194
  內部權重**係啱嘅** —— 搜索試過搬走佢，冇一個變體贏。）

* **`jockey_trainer`** —— 呢個係我事前認為最可疑嗰個：`jockey_horse_fit_score`
  攞過半內部權重（0.52）但場內 AUC 只有 0.532，而同維度 jockey 0.600 /
  trainer 0.605。搜索**確認**咗方向（fit 0.52 → 0.381），dev 同 holdout
  兩邊全部升（holdout Gold +1.10 / any2 +2.20 / t3prec +1.47，冇一個跌），
  而且過埋 SD 對照組。**但 walk-forward 只有 3/5**（窗 2 winT3 −0.83、
  窗 4 winT3 −1.67）。保守版 0.30/0.24/0.46 亦只有 4/5。
  已 ship 嘅維度重配權當時係 5/5，唔可以為呢個降低同一條閘。

* **`stability`** —— form .60 → .65 **過咗**預先聲明嗰條閘（wf 5/5、SD 對照
  4↑/0↓、holdout 冇跌），全樣本 Gold +0.50 / Good位 +0.33 / winT3 +0.83 /
  t3prec +0.28。仍然唔 ship，兩個原因：
  1. **champion −0.50**，而且加 champion 做守門之後 wf 跌到 3/5（窗 4 −2.50）。
  2. 掃一掃鄰近值：`0.62 → 5/5`、`0.63 → 4/5`、`0.65 → 5/5`、`0.68 → 4/5`、
     `0.70 → 4/5`。**相鄰值 pass/fail 跳來跳去** —— 呢個係平面加噪音嘅特徵，
     唔係一個有 gradient 嘅最優點。幅度本身亦只係 604 場之中 1–5 場。

⚠️ **留返嘅教訓**：`jockey_trainer` 嗰個結果最值得記住 —— dev 升、holdout 升、
SD 對照過、AUC 亦支持個方向，四樣都指向同一邊，但逐窗一睇就散。
「多個獨立檢查同意」唔等於「穩」，如果嗰幾個檢查都係喺同一批數據上切出嚟。

## ⚠️ 更正：「trainer 評分蝕 4.4pp」係錯嘅（2026-08-04）

我曾經報「簡單收縮上名率 0.615 vs 引擎 `trainer_score` 0.571，差 4.4pp」。
**嗰個係跨語料比較。** 0.571 喺 `sb_refit`（LY 填 81%）量，0.615 喺 `sb_v2`
（LY 填 96.8%）量。同一語料量返：

    trainer_score 0.605  vs  簡單公式 0.615   →  1.0pp
    jockey_score  0.600  vs  簡單公式 0.599   →  0.001

引擎個 base 公式冇問題，prior 亦準（練馬師 prior 0.3946 vs 實測中位數 0.3909；
騎師 0.3564 vs 0.3598）。**by-going 分項、micro adjustment、base 公式三個
方向全部查完，冇一個係大缺口。**

仍然有效嘅係 leaf 替換 A/B（同語料）：換 `trainer_score` dev 5/5、
holdout t3prec +1.47 / winT3 +1.10，冇一個跌。但幅度應該按 1.0pp 而唔係
4.4pp 去理解 —— 呢個係邊際改善，唔係修一個壞掉嘅 leaf。

## 2026-08-04 再測 —— 又四個負面結果

**段速覆蓋唔足唔係問題。** PI（位置增益）喺**三個參考點全部反向**：

    sectional_score（Settled − 終點）  覆蓋 34%   AUC 0.469
    l400_pi（400m − 終點）             覆蓋 74%   AUC 0.478
    l800_pi（800m − 終點）             覆蓋 74%   AUC 0.480

`l400_pi` 本來係最自然嘅補救（`inject_fact_anchors` 算咗 18 處，引擎一個字都
冇讀，而 400m 走位覆蓋係 Settled 嘅三倍）。但佢一樣反向 —— **提升覆蓋只會提升
噪音**。「由後追上」本身就係「之前落後」嘅標記，領放馬贏得多。

**試閘名次＋時間合併** = 0.528，同單用名次（0.528）**完全一樣**。加唔到嘢。

**賽績線畀返權重**（`form_line` 而家係 0.0）：dev 睇落得（w=0.03 全部非負），
但 holdout `champion` 喺**每一個權重**都係負（−1.10 到 −2.20），`winT3` 完全冇動。
唔過閘。

**騎練 cache 有大城市偏差 —— 新缺口。** 2026-08-04 Warwick（鄉郊）實測，
LY token 只填到 **107/214 = 50%**，而 archive（全部大城市場次）係 96.8%。
`jockey_score` 係第三強嘅 leaf（0.589），呢個缺口值得補 —— 補覆蓋比加特徵划算。

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
