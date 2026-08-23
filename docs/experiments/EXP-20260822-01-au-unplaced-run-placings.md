# EXP-20260822-01 未上名嘅仗，名次讀成輸距，一律當中性 60

- **日期**：2026-08-22
- **平台**：AU
- **假設**：AU 賽績表對跑第 4 或以後嘅仗寫 `名次 -`，而引擎用 `parse_float` 讀呢格
  會攞到**輸距**（負數）當名次；負數過得晒所有「跑得好唔好」嘅門檻，所以每一場
  未上名嘅仗都被評成中性中游，而「末段跌位」呢件事結構上冇得表達。
- **搜索過嘅舊記錄**：`docs/experiments/` grep `名次 / placing / last10 / PI /
  sectional` — 冇相關記錄。最近似係 EXP-20260821-05（審計後續修假警報）同
  memory `au-field-size-extraction-gap`（同一格嘅另一半問題：馬匹數）。
- **改到嘅檔案／組件**：
  - `.agents/scripts/inject_fact_anchors.py` — 新增 `_formguide_header()`、
    `_enrich_last10_from_formguide()`，並喺 `parse_formguide_for_horse` **之前**呼叫
  - `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/scoring.py`
    — 新增 `parse_placing()`
  - `.../au_racing_engine/engine_core.py` — 八個 `parse_float(entry["placing"])`
    改用 `parse_placing`

## 起因

用戶覆盤 2026-08-22 Randwick R1：模型首選係 Gunroom（$31），但佢「全程位置都對，
最後 800m 跌走」，而市場亦完全唔覺佢有機會。

拆分佢個分：clean 五維分 **68.57 = 場內第 4**，唔係第一。頂到第一係兩樣嘢：

| | Gunroom | Clear Proof（$4.20） | 差 |
|---|---|---|---|
| clean ranking score | 68.57 | **71.08** | −2.51 |
| 濕地 overlay | **+2.475** | −0.571 | +3.05 |
| pace_perf（12.2% 權重） | **79.51** | 59.83 | +2.40 |
| 綜合戰力分 | **71.05** ① | 70.51 ② | +0.53 |

任何一樣拿走，Clear Proof 就係第一。而 `pace_perf` 有 94% 係 `pace_figure_score`
—— engine 自己個 note 講明係 **race-level**（佢跑過嘅場幾快），唔係本駒自己嘅
末段 split。

順住問「點解引擎睇唔到佢跌位」，就撞到下面呢個管線缺陷。

## 根因（三層）

1. `inject_fact_anchors.parse_racecard()` 由 **Racecard** 抽 `Last 10:` —— Racecard
   根本冇呢個欄位。實測今日 **760/760** 匹 Facts 寫 `Last 10 字串: None`，而
   Formguide header **760/760** 都有值。所以 `parse_last10()` 同
   `pos_source='last10'` fallback 由頭到尾係死 code。
2. Fallback 斷供之後，唯一嘅名次來源係 `1-x, 2-y, 3-z` 上名行 —— 佢按定義唔會提到
   任何跑第 4 或以後嘅馬。於是名次格寫 `- (-1.5L)`，冇 ` /starters`。
3. `parse_float("- (-1.5L)")` 回 **−1.5**（輸距）。負數過得晒所有門檻：

   | 位置 | 條件 | 效果 |
   |---|---|---|
   | `_form_score` | `place <= 5` | **base 60**（中性中游），輸 0.3L 同輸 24L 一樣 |
   | `_sectional_score` | `<= 3` | 當**上名** |
   | `_sectional_breakdown` | `<= 4` | 當**前四** |
   | `_distance_score` | `not > 3` | 當**同程上名** |

   `field_size` 由同一格 parse，所以 2026-07-31 加嘅馬匹數正規化**只曾對上名場生效**。

## 規模（乾淨 point-in-time 語料，2026-08-05 起）

- 計分 form 行 **18,394 / 27,932（65.9%）**名次係負數，全部 base 60。
  隱藏輸距中位 **5.0L**、p90 **11L**、最大 **240L**；2,849 行係 10L+ 嘅大敗。
- **94.8%** 嘅馬至少有一行中招；**67.4%** 係最近一仗（近期權重 1.0）。
- PI（`settled − finish`）只有 **19.1%** 跑得出，未上名嘅 **0 / 22,846**。
  剩低樣本均值 **+2.690** —— 純生存偏差：領先到 800m 然後跌落第 4 完全冇紀錄，
  所以「後勁」訊號結構上只睇得到跑得好嘅馬。

## 修法同驗證

`_enrich_last10_from_formguide()` 由 Formguide header 補 `last10_raw`（一定要喺
`parse_formguide_for_horse` 之前跑，因為嗰個 call 會消費 `decoded`），再由
`parse_placing()` 保證任何時候都唔會將輸距讀成名次。

落地之前先對證我哋自己個結果庫（`AU_Historical_Raw_Race_Results.csv`）：
**3,350** 場可對證嘅往仗，Last-10 解碼同結果庫一致 **97.91%**。所以佢仍然只做
**fallback** —— 上名行有值時照用上名行，唔一致就寫 `pos_note`。

Gunroom 實例（同結果庫核對）：

| 仗 | 修前 | 修後 | 真相 |
|---|---|---|---|
| 2026-08-08 Kembla R4 | `- (-1.5L)`，PI `-` | `4/8 (-1.5L)` | 8 匹跑第 4（$3.60 第二熱門）|
| 2025-11-15 Doomben R8 | `- (-5.48L)`，PI `-` | `6/11 (-5.48L)`，PI **−4**，段速 **極慢** | 11 匹跑第 6 |

趨勢線由 `PI 趨勢: 微升` 變成 `L400 PI: −2 → −2 → −4 … 趨勢: 衰退中 ⚠️`。

## 覆蓋率結果（13 個配對場次 / 6,754 record 行 → 全語料）

| 指標 | baseline | candidate |
|---|---|---|
| 名次已知 | 38.7% | **80.9%** |
| 有馬匹數 | 38.7% | **80.9%** |
| PI 算得出 | 21.1% | **42.7%** |
| PI 樣本均值 | +2.690 | **+0.963** |
| fade 觀測（PI<0） | 208（13.6%） | **1,013（33.0%，4.9×）** |

殘餘 19% 補唔到：Sportsbet 個 overview 欄位其實係 **Last 6**（Formguide 標籤寫
"Last 10:" 係誤導），而 dossier 深 10 仗，所以第 7 仗之後冇來源。


## 後續（同日）：真正嘅根因喺上一層 —— 序列化，唔係 fallback

用戶追問「rating / sectional 覆蓋率」時掃咗源頁面，發現一件更基本嘅事：

```
Finished 4/8 3.03L $2,675 (of $45,000), Jockey Aaron Bullock, Barrier 5, Weight 59.0kg 7.00
In running 400m 3rd    Sectionals 600m 33.220s
1st Karkadaan (Jessica Taylor 56.5kg)  Winning Time 51.860
```

**`Finished N/M` 喺源頁面每一條正式賽往績行都有 —— 實測 7,069/7,069 = 100.0%**，
而 `claw_sportsbet_form.RE_RUN` 一直正確 parse 咗 `run['pos']` / `run['field']`。
但 `run_line()` **只寫 `starters:{field}`，從來冇寫 `pos`** —— 名次係「抽到、
然後喺序列化靜靜掉」。下游因此只能由 `1-x, 2-y, 3-z` 上名行重建，而嗰行按定義
唔會提到任何跑第 4 或以後嘅馬。

所以上面用 `Last 6` 做 fallback 係**繞路**。正確修法：`run_line()` 寫
` finish:{pos}/{field}`，`inject_fact_anchors` 以佢為**最高優先**來源
（上名行、`Last 6` 降為第二、第三層 fallback，令舊 formguide 照跑）。

實測（Randwick R1 端到端，同一份 Racecard）：

| | 名次已知 | 有馬匹數 | PI |
|---|---|---|---|
| 修前 | 49.3% | 49.3% | 19.2% |
| `Last 6` fallback | 84.9% | 84.9% | 32.9% |
| **`finish:N/M` token** | **100.0%** | **100.0%** | 36.9% |

`Last 6` 版本嘅 2.09% 對位誤差同「Sportsbet 只出 6 個 form figure 而 dossier 深
10 仗」嗰個 19% 殘餘缺口，兩樣一次過消失。

⚠️ 洩漏檢查：`run_line()` 只喺 `if run_date(run) >= date_str: continue` **之後**
被呼叫，所以 `finish` token 唔可能引入賽後資訊。守門條件冇動過。

### PI 仍然只有 36.9% —— 但唔係數據問題

PI = `settled − finish`，而 `settled` 喺源頭只有 **51.5%**。同一批往績行嘅
`In running 400m` 有 **94.6%**、`800m` 有 **92.8%**。即係 PI 覆蓋率嘅上限係
「揀咗 `Settled` 做 checkpoint」，唔係缺數據。但
[EXP-20260822-02](EXP-20260822-02-au-late-fade-scoring.md) 已證末段跌位訊號
落唔到分（ρ +0.26 對全模型），所以換 checkpoint 屬**報告價值**，唔係排名價值。

### `Sectionals 600m` 係 race-level —— 已證實，唔係 bug

同一場歷史賽事、唔同馬匹嘅 `Sectionals 600m`：**1,191 場全部完全相同（100.0%）**。
所以 Sportsbet **冇逐駒段速**，`pace_figure_score` 結構上只能係 race-level。
要個體 split 就要換源（RA sectionals），唔係抽取層修得到。


## ⚠️ 2026-08-23：`finish` token 嘅語料回測**無效**，唔可以引用

想量 100% 覆蓋（`finish` token）vs 84.9%（`Last 6`）嘅排名差異，做法係由 cache
重建 form 行。**呢個做法本身有系統性偏差，量出嚟嘅數唔可信。**

原因：Sportsbet 表格頁**封頂 10 條往績行**（實測 659 個 runner block，500 個剛好
10 條，最大 10）。cache 頁係**賽後**抓嘅，所以嗰 10 格有部分被賽後嘅新仗佔咗；
我用 `run_date >= 場次日期` 濾走之後，剩低嘅賽前往績就**少過**當日 live 抽取拿到嘅。

實測 dossier 深度（同 672 份 Facts、同 6,731 匹）：

| 臂 | dossier 總行 | 每匹平均 |
|---|---|---|
| baseline | 59,987 | **8.91** |
| `Last 6` fallback | 59,987 | **8.91** |
| `finish` token（cache 重建） | 55,496 | **8.24（−7.5%）** |

即係嗰一臂同時改咗兩樣：名次準確度 ↑ **同** 往績深度 ↓。第 5–10 行餵
`going_stats` / `formline` / 對手線，所以嗰個 −1.18 t3prec、−3.37 pass2
**分唔開係名次修正定係歷史被截**。作為 A/B 佢係廢嘅。

**唯一有效嘅比較係 baseline vs `Last 6`**（dossier 完全一樣，59,987 行對 59,987 行，
只差名次復原率 34.6% → 79.8%）：五個指標全部 CI 跨零，leaf 顯著變好。
即係本文上半部嘅結論**成立**，冇改變。

### 連帶要收回嘅說法

1. 「`finish` token 令排名顯著變差」—— **收回**。嗰個量度無效。
2. 「修好之後 391/3000 候選過閘（之前只有 20–55），證明出廠權重嚴重過期」——
   **收回**。嗰個搜索係喺被截歷史嘅語料上做，過閘率高有可能純粹係語料被弄壞。
   同一份語料嘅 walk-forward 亦只有 2/3 窗口、指標 5 升 5 跌，本身唔過閘。
3. 「重 fit 想要 `pace_perf` 升」（EXP-03）同「想要 `pace_perf` 持平」（本文）——
   **兩個都唔可信**，因為分別喺兩份有唔同缺陷嘅語料上做。

### 可以點做

`finish` token 修正本身係**源頭正確性修正**（源頭覆蓋 7,069/7,069 = 100.0%），
生產環境係**賽前** live 抽取，冇 10 條封頂被賽後仗佔位嘅問題，所以生產覆蓋率
係真 100%。但佢嘅**排名效果只可以向前量** —— 由落地之後嘅 live 場次累積，
唔可以 backfill。重 fit 嘅問題亦只能等嗰批乾淨 post-fix 場次夠數先重開。

## 排名 A/B（787 場重建 Facts + Logic + 評分，兩臂同一份 Formguide、同一個 going）

兩臂都由**同一批 Formguide 快照**重建（baseline 用 `git worktree` 出 4882ff8c 嘅乾淨
checkout），評分時逐場 forced 用**已發佈語料嗰個 going**，所以 going / track profile /
州曆 cache 呢類非 point-in-time 干擾兩邊完全一樣。600 場配對、5,750 匹。

### 綜合指標 —— 全部跨零，即係打和

| 指標 | baseline | candidate | 差 | 95% CI |
|---|---|---|---|---|
| ability 場內 AUC | 0.6766 | 0.6798 | +0.0032 | [−0.0013, +0.0077] |
| top-3 precision | 51.11% | 50.78% | −0.33 | [−1.33, +0.61] |
| gold@4 | 68.67% | 67.83% | −0.83 | [−2.50, +1.00] |
| pass（3 揀 2 上名） | 54.33% | 52.67% | −1.67 | [−4.00, +0.67] |
| 首選上名 | 58.67% | 59.33% | +0.67 | [−1.17, +2.50] |
| 首選頭馬 | 25.67% | 25.00% | −0.67 | [−2.33, +1.00] |

### 但 leaf 層面係大幅改善（配對 bootstrap 4,000 次）

| leaf | 排名權重 | ΔAUC | 95% CI | | 場內 SD |
|---|---|---|---|---|---|
| `form_score` | **22.83%** | **+0.0265** | [+0.0149, +0.0383] | ✅ | 8.09 → **10.65** |
| `rating_score` | 9.74% | +0.0096 | [+0.0028, +0.0167] | ✅ | 5.36 → 5.33 |
| `performance_quality_score` | 15.22% | +0.0026 | [+0.0000, +0.0054] | — | 18.91 → 19.02 |
| `consistency_score` | **0%** | **+0.0938** | [+0.0761, +0.1121] | ✅ | 3.80 → **12.52** |
| `class_score` | **0%** | **+0.0883** | [+0.0685, +0.1082] | ✅ | 0.4838 → 0.5722（**原本反向**）|
| `distance_score` | **0%** | +0.0165 | [+0.0059, +0.0270] | ✅ | 5.81 → 4.87 |
| `sectional_score` | 0% | +0.0065 | [−0.0046, +0.0180] | — | 9.92 → **7.45** |

**冇一個 leaf 變差。** 五個顯著變好。

### 點解 leaf 升咗但綜合打和 —— 兩個原因，都唔係「個修冇用」

1. **三個升幅最大嘅 leaf 攞 0% 排名權重**（`consistency_score` +0.094、
   `class_score` +0.088、`distance_score` +0.017）。`class_score` 本來 AUC **0.4838**
   —— 即係**反向**預測，因為未上名嘅仗經 `not > 3` 當咗同程上名。
2. **`form_score` 嘅場內 SD 由 8.09 闊到 10.65（+32%）**，而 `stability` 個
   `MATRIX_DISPLAY_GAINS` 係 0.9750、`MATRIX_WEIGHTS` 係 38.1% —— 兩個都係喺
   SD 8.09 嗰個分佈上 fit 嘅。排名只食 `weight × gain × deviation`（見
   `matrix_mapper` 註釋同 `au-dimension-scale-weight-lockstep`），所以一個闊咗 32%
   嘅 leaf 塞入一個唔變嘅 gain，等於靜靜將全模型最重嘅維度再加重 32%。

   呢個係 repo 自己записа過嘅模式（2026-08-03 註釋）：「補完騎練 LY token 之後
   `jockey_score` 場內 AUC 0.565→0.589，但排名反而跌 —— **leaf 好咗，配權冇跟住**。」

### `sectional_score` 覆蓋率跌（43.2% → 38.0%）係修好嘅證據

個 leaf 之前收到**假前提**嘅加分：未上名嘅仗經 `recent_top3` / `recent_top4`
（−1.5 ≤ 3、≤ 4）當咗上名，於嘅解鎖「增益兌現」等 bonus。名次修正之後嗰啲仗唔再
合格，所以更多馬跌返 60 地板。而因為個 leaf 係**純加分累加器**（七個正項、零個負項），
拆走假加分只能令分數向 60 靠，**冇得表達「跌位」本身**。

## 檢查
- **run_tests.sh**：九個 suite 全綠
- **golden_scoring（AU）**：120 匹全部一致 —— ⚠️ **呢個係盲點，唔係好消息**。
  golden 個 fixture 把**已經算好嘅 leaf 分**當輸入存落去，只驗下游矩陣算術，
  所以一個 Facts→leaf 嘅解析缺陷佢結構上捉唔到。
- **data_contract（AU）**：`stale-baseline`（引擎由 `15bb329f6325` 變
  `6f2e9879511c`）—— 按規矩要等判決之後先 `--calibrate`。
- **leakage-audit**：PASS。名次來源係**該仗當時已公開嘅賽果**，落注時點之前就有；
  唔涉及今場任何資訊。Last-10 字串本身係抓取當日嘅 racecard 快照，同名次一樣屬
  賽前可得。

## 結論

呢個係一個**數據正確性缺陷**，唔係調參。引擎將輸距讀成名次，令 65.9% 計分行、
94.8% 嘅馬中招，而「末段跌位」呢件事結構上冇得表達。修好之後名次覆蓋
38.7%→80.9%、PI 21.1%→42.7%、fade 觀測 208→1,013（4.9×），五個 leaf 顯著變好
（包括佔 22.83% 權重嘅 `form_score` +0.0265，同一個本來**反向**嘅 `class_score`），
**冇一個變差**。

綜合排名打和，原因量得清楚：三個升幅最大嘅 leaf 攞 0% 權重，而 `form_score`
闊咗 32% 但 gain / 權重冇跟住。所以「綜合打和」係**配權過期**嘅症狀，唔係
「個修冇效果」—— 呢個分別好緊要，唔可以當成 REJECT 嘅理由。

順帶量到嘅兩件事，各自值一個獨立實驗：

1. **`SECTIONAL_MICRO_WEIGHTS` 係 base 60 + 七個正項、零個負項** ——「缺乏後勁」
   同「冇數據」拿同一個分。`scoring.py` 寫住「試過三次，三次都輸，唔好試第四次」，
   但嗰三次都係喺 fade 只有 208 個觀測（13.6%）嘅語料上量。而家 1,013 個（33.0%），
   嗰句話嘅證據基礎已經唔同。
2. **`pace_figure_score`（race-level L600）攞 11.49% 權重、AUC 0.5392、70 分以上
   飽和**（PF 70-79 +4.59pp、80-89 +2.39pp、90-99 +5.59pp），而本駒自己嘅
   `sectional_score` 攞 0%。六個上行壓縮候選全部 CI 跨零，所以呢度**未有可落地嘅
   改法**，但個形狀本身係錯嘅。

⚠️ **`golden_scoring` 對呢類缺陷結構上盲**：佢個 fixture 把**已經算好嘅 leaf 分**
當輸入存落去，只驗下游矩陣算術。一個改寫 65.9% form 行嘅改動，佢報「120 匹全部一致」。

**決定**：**KEEP**（數據正確性修正；leaf 全面變好、無倒退；綜合無顯著倒退）。
配權／gain 重 fit 係**另一個實驗**，按 repo 規矩要自己過 walk-forward
（`au_matrix_refit.py`，要先重新 dump leaves）。

**commit**：未 commit
**部署備註**：生產排程行 `/Users/imac/wongchoi-scheduler`（worktree，分支
`au-production` @ f262cd66），所以要 merge 落 `au-production` 先生效。
落地之後要跑 `data_contract.py --platform au --calibrate`（而家報 `stale-baseline`：
引擎由 `15bb329f6325` 變 `6f2e9879511c`）。

## 重跑
```bash
export PYTHONDONTWRITEBYTECODE=1
# 覆蓋率／PI 分佈
python3 /tmp/.../form_probe.py ; python3 /tmp/.../pi_probe.py
# Last-10 對證結果庫
python3 /tmp/.../last10_validate.py
# 兩臂重建 + 評分 + 配對 bootstrap
bash run_arm.sh <baseline-worktree> out_base ; bash score_arm.sh <baseline-worktree> out_base
bash run_arm.sh /Users/imac/Antigravity-repo out_cand ; bash score_arm.sh /Users/imac/Antigravity-repo out_cand
python3 ab_eval.py
```
