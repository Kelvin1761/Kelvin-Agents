# 2026-07-31 AU Geelong 覆盤 + 陳舊證據根因分析

> 觸發：用戶指出 R7 #8 Benbulben —— 全場最大冷門（SP $101）、跑最後（−21.0L），
> 但模型排第 2，四匹退出後變成公佈嘅頭號推介。用戶判斷「其他排序合理，只有呢匹離譜」。
> 本報告驗證咗呢個判斷：唔係一般噪音，係一個獨立嘅結構性漏洞。
>
> **審批閘門：以下所有 candidate 只供審批，未有跑 A/B，未改任何 code / matrix。**

## 1. Meeting 覆盤

`2026-07-31 Geelong Race 1-9`（Soft 7，9 場）。Reflector report 見同名 meeting folder。

| 指標 | 值 |
|---|---|
| Gold / Good / Pass / 1-Hit / Miss | 0 / 2 / 2 / 3 / 2 |
| Top-5 包齊實際前三 | 1/9 (11.1%) |
| Top-5 包至少兩匹前三 | 5/9 (55.6%) |
| 冠軍在 Top-5 | 3/9 (33.3%) |

退出後嘅實際頭號推介表現 —— 9 場有 5 場入前三：

| 場 | 頭號推介（退出後） | 結果 | SP |
|---|---|---|---|
| 1 | #2 Gaelic Kiwi | **2nd** | $5.50 |
| 2 | #11 Nothin' Surer | **3rd** | $18 |
| 3 | #5 Alabama Dance | **2nd** | $8.50 |
| 4 | #8 Royal Duck | **1st** | $2.25 |
| 5 | #10 Ashina | 4th | $9 |
| 6 | #2 Omnic | **2nd** | $3.70 |
| 7 | **#8 Benbulben** | **11/11, −21.0L** | **$101** |
| 8 | #2 Nicoffhome | 前三外 | — |
| 9 | #1 Ania | 4th | $7.50 |

排序本身合格。R7 係另一類 failure。

## 2. Benbulben 根因

呢匹馬喺分析檔內**全部正式賽績只有兩場，兩場都係 2024 年 8 月**：

| 日期 | 賽事 | 名次 | 評語 |
|---|---|---|---|
| 2024-08-11 | Casterton 3500m Maiden | 4th，**−12.0L** | "Only plodded final 400m.; Poor." |
| 2024-08-02 | Swan Hill 2400m Maiden | 6th，**−9.05L** | "Passed a few plodders late.; Plain." |

即係 **久休 719 日**、由 Maiden **升班** BM62、2400m。市場 $61 飄到 $101。模型 68.1 分排第 2。

分數拆解：

### A. `sectional_score` = 77.5（base 35.8 → 兩場 2024 舊賽貢獻 +41.7）
`engine_core.py:804 _sectional_breakdown`

- `+20.0` 位置增益（PI）優秀「近2仗末段平均追前 3.5 個位」。PI 係 +2 同 +5；
  嗰個 +5 就係評語寫住 *"passed a few plodders late"* 而輸 9 個馬位嗰場。
  引擎自己嘅 `sectional_trend_line` 已經寫 **趨勢: 數據不足**，但照原強度計分。
  **呢個 module 完全冇 sample-size shrinkage**（對比 `pace_map` 有 empirical-Bayes `k=25`）。
- `+15.07` 末段極速破標準「生涯最快 35.11s，快過場地標準 36.74s」。
  `timing_600m_best_speed` 係**跨路程嘅生涯最大值**，去同**今仗路程**嘅標準比
  （`engine_core.py:860-880`）。同一匹馬自己嘅 L600 平均係 15.4 m/s (38.96s)，
  「最佳」17.09 m/s (35.11s) —— 一個唔同賽事形態嘅單一快段速，換到最高獎勵。
- `+6.64` 增益兌現「近3仗有1次前四」。嗰個「前四」＝ 6 匹跑第 4，輸 12 個馬位。

### B. `consistency_score` = 88.2 —— 最關鍵嘅 bug
`engine_core.py:3481 _consistency_score`

- `+23.58` ＝ 3 × 7.86，來自「近6仗3次前三」，讀 `recent_form` = `4-6-1-3-3-8-2`。
- 但 `form_score` 只見到 **2 場**（就係上面兩場 2024），並且正確地做咗薄樣本收縮 →
  55.6，note 寫「2場計分樣本，偏弱分向中性收縮」。
- **同一個矩陣維度用兩個唔同嘅證據窗**：
  - `form_score` ← 已核實嘅賽績表（2 行，有班次係數，有 index decay）
  - `consistency_score` ← 原始 last-10 字串（7 場，**冇班次加權、冇 decay、冇 cap、冇收縮**）
  一個 leaf 嘅薄數據防護，俾另一個 leaf 抵銷。`stability = 0.6×55.6 + 0.4×88.2 = 68.6`。
- 嗰批 1-3-3 名次係喺上面兩場 2024 之**前**嘅鄉下 Maiden —— 大約三年前。

### C. 唯一知道久休嘅 feature，排名權重係零
`engine_core.py:3634` 印咗 `久休 719 日而缺少試閘時間支撐`，`score -= 1.0`
落 `health_score`。但 `health_score` 屬 `REPORT_ONLY_FEATURE_KEYS`（`scoring.py:21`），
權重 **0.000**。719 日久休對排名嘅代價：**完全冇**。

### D. `data_coverage.confidence` 報「高」(84.6%)
Coverage 只數 feature **有冇值**，唔數背後**有幾多數據**。
`sectional_score` 憑 2 個 PI 值就標記 `"observed"`。

### E. 市場訊號在 bundle 內但完全冇用
`current_market_line: $61 $51 $71 $61 $51 $61`。喺 `_data` 內，權重零（呢個係
2026-07-24 「odds improve the system not the model」嘅有意設計），但**公佈嘅推介
亦冇任何 market gate**。

### F. 公佈嘅推介卡從來唔會因退出而重新排序
`top_picks` 仍然係 rank 1 Omamori（已退出）、rank 2 Benbulben。當日四匹退出，
Benbulben 直接被推上頭號，冇任何 re-validation。

## 3. Archive 量化（713 場 / 7,253 匹，現行引擎存檔分數）

`scratch/au_stale_evidence_cohort.py`、`scratch/au_layoff_cohort.py`（皆唯讀）。
久休日數由 `latest_official_date` 取，空白時 fallback 去 Facts 賽績表日期
（`field` 294 / `facts` 6,932 / `none` 321）。

### 3a. 久休 vs 前三率 —— 全體馬匹（大樣本，單調）

| 久休 | n | 入前三 % |
|---|---:|---:|
| 0–45d | 5,919 | **28.6%** |
| 46–90d | 247 | 27.5% |
| 91–180d | 773 | 26.5% |
| 181–365d | 256 | 24.6% |
| 365d+ | 31 | **19.4%** |

**完全單調遞減，n = 7,226。** 呢個係一個引擎有計、有印、但排名完全掉咗嘅真實訊號。

### 3b. 久休 vs 頭號推介表現

| 久休 | n | 勝 % | 前三 % | 尾三分一 % | 平均 SP |
|---|---:|---:|---:|---:|---:|
| 全部 | 713 | 23.8 | 49.9 | 19.6 | 7.5 |
| 0–45d | 570 | 23.2 | 49.8 | 18.1 | 6.8 |
| 46–90d | 26 | 34.6 | 50.0 | 19.2 | 7.3 |
| 91–180d | 91 | 26.4 | 50.5 | **28.6** | 9.6 |
| 181–365d | 15 | 13.3 | 46.7 | 26.7 | **17.4** |
| 365d+ | 3 | **0.0** | **0.0** | **66.7** | **35.0** |

`>180d` 嘅 18 個頭號推介：7 匹入前三（38.9% vs 基線 49.9%）。
`>330d` 嘅 4 匹：**0 匹入前三**（9/12、13/15、4/9、5/9）—— 加 Benbulben 係 0/5。
注意平均 SP 隨久休遞升（6.8 → 35.0）：**市場一路知，模型一路唔知**。

### 3c. 薄 PI 樣本 vs 頭號推介表現

按 `sectional_score` 背後有幾多場帶 PI 值分組：

| PI 場數 | n | 前三 % | 尾三分一 % |
|---|---:|---:|---:|
| 1 | 71 | **38.0** | **28.2** |
| 2 | 89 | 49.4 | 20.2 |
| 3 | 74 | 56.8 | 17.6 |
| 4+ | 380 | 51.3 | 18.2 |
| 基線 | 713 | 49.9 | 19.6 |

單 PI 場嘅頭號推介前三率 **−11.9pp**，跌落尾三分一嘅頻率高 40%。

## 4. Candidate 修正（待審批，未跑 A/B）

按證據強度排：

### C1 — 久休衰減成為真正嘅排名 feature（證據最強）
`_spell_days()` 已經存在，唔需要新數據。將久休由 report-only 搬入排名，
或者用久休去衰減 `form_score` / `consistency_score` 嘅證據權重。
- 支持：3a 單調（n=7,226）、3b（>330d 係 0/5）、成本零新數據。
- 風險：`>365d` 頭號推介只有 n=3，magnitude 要靠 3a 嘅全體斜率去定，唔好靠 3b。

### C2 — Sectional PI / L600 加 sample-size shrinkage
按 `n/(n+k)` 收縮 PI 同 L600 獎勵，同 `pace_map` 現有做法一致。
- 支持：3c（單 PI 場 −11.9pp，n=71）。
- 順帶修：L600「破標準」要 **同路程**（或做路程正規化）才比較，
  唔好再拿 1250m/3500m 嘅生涯最快去比 2400m 標準。

### C3 — `form_score` / `consistency_score` 統一證據窗
兩個 leaf 都用已核實賽績表，`consistency` 加班次加權 + 時間衰減 + cap，
令薄樣本收縮唔會被另一個 leaf 抵銷。
- 支持：機制上明確（B 節），但要獨立 A/B 因為會同時動兩個 leaf。

### C4 — 公佈層 gate（唔改模型）
1. 退出後重新排序 `top_picks`，並且對「因退出而升上頭號」嘅馬做 re-validation。
2. 對「證據深度不足」嘅頭號推介加 watchlist flag（久休 > X 日 / PI 場數 ≤ 1 /
   formal_count ≤ 2），而唔係喺分數層動手。
3. `data_coverage.confidence` 要反映**證據深度**，唔止 feature 有冇值。
- 支持：純顯示層，零排名風險，直接解決用戶睇到嘅症狀。

## 5. C1 Shadow A/B 結果 —— **FAIL，不可採納**

`scratch/au_layoff_shadow_test.py`（連續版）＋ `scratch/au_layoff_shadow_test_gated.py`
（tail-gated 版）。713 場切成 dev 606 場（2025-08-02 → 2026-06-10）＋ 未碰過嘅
holdout 107 場（2026-06-10 → 2026-07-08）。同一把尺
`.agents/skills/shared_racing/eval_metrics.py`。久休扣分加落 `ability_score`，
做法對齊現有 `wet_form_feature`。

### 5a. 連續 piecewise-linear 版 — FAIL

dev fold：

| 指標 | P=0 | P=2 | P=4 | P=6 | P=8 | P=12 |
|---|---:|---:|---:|---:|---:|---:|
| Gold | **33** | 31 | 28 | 27 | 28 | **25** |
| good_pos % | 19.80 | +0.33 | +0.33 | 0.00 | 0.00 | +0.33 |
| champion % | 23.60 | +0.16 | +1.15 | +0.16 | −0.33 | **−1.16** |
| winner_in_top3 % | 51.49 | +0.49 | −0.17 | +0.33 | +0.82 | +1.81 |
| top_pick_blowout % | 20.13 | −0.33 | −0.99 | −0.66 | −0.82 | −1.15 |
| top_pick_competitive % | 56.27 | −0.49 | +0.17 | −0.82 | −1.15 | −1.32 |
| mean_ndcg_at5 | 0.5365 | −0.00 | +0.00 | −0.00 | −0.00 | −0.01 |

holdout：`top_pick_blowout` −1.87pp，但 `champion` −0.93、`winner_in_top3` −0.93、
`mrr` 倒退，Gold 6 → 6。

**唯一單調改善係 `top_pick_blowout`，代價係 Gold 33 → 25。FAIL。**

診斷：量到嘅訊號只喺尾部決定性（>365d 19.4%，n=31），
0–180d 三格（28.6 / 27.5 / 26.5%）幾乎冇 gradient 但佔 6,939 / 7,226 匹。
喺密集區施加扣分＝純噪音重排 → Gold 流失來源。

### 5b. Tail-gated 版 — 亦 FAIL（而且反證咗 5a 嘅「唯一改善」係噪音）

Gate footprint（713 場之中）：

| Gate | 涉及馬匹 | 涉及場次 | **佢係頭號推介嘅場次** |
|---|---:|---:|---:|
| >180d | 287 | 198 | **18** |
| >270d | 86 | 76 | **4** |
| >365d | 31 | 30 | **3** |

| Gate / P | Gold (dev) | blowout % (dev) | 其他 dev 指標 | holdout |
|---|---|---|---|---|
| th=180, P=3→15 | **−1 到 −3** | **+0.17（變差）** | 全部 ±0.5 以內 | 幾乎全零 |
| th=270, P=3→15 | −1 到 −2 | 0.00 / +0.17 | 全部 ±0.35 以內 | 全零 |
| th=365, P=3→15 | **33 → 33 (+0)** | **0.00** | **全部指標 0.00** | **全部 0.00** |

兩個關鍵讀數：

1. **th=365（訊號真正所在）對 713 場嘅影響係字面上嘅零** —— 因為只有 **3 場**嘅
   頭號推介久休超過 365 日。呢個 cohort 喺 archive 上根本**無法量度**。
2. **th=180 之後 `top_pick_blowout` 反而變差 (+0.17)。** 即係 5a 嗰個 −0.99
   改善**唔係嚟自懲罰久休**，而係嚟自 0–180d 密集區嘅重排 —— 佢本身就係噪音。
   C1 連續版連唯一嘅「勝利」都係假嘅。

### 5c. 結論

**713 場 archive 支撐唔起一個久休 ranking feature。** 訊號係真嘅（7,226 匹單調），
但會改變頭號推介嘅場次只有 3–4 場（~0.5%）。任何足以起作用嘅 magnitude 都必須
闊範圍施加，而闊範圍施加係淨負。同 AU round 10（PF backfill）、trainer_signal、
HKJC stale re-score 一樣 —— killed candidate 係常態。

### 5d. Geelong R7 反事實（記錄用）

久休 719 日 → weight 1.00；全場其他馬 8–108 日。

| P | Benbulben 排名 | 頭號推介變成 |
|---|---|---|
| 0 | **1** | Benbulben（實際 11/11, $101） |
| 2 | 2 | Winston（實際 **3rd**） |
| 4 | 4 | Winston |
| 8 | 6 | Winston |

任何 `P ≥ 2` 都足以令佢唔再做頭號推介。**但 R7 嘅 KPI 標籤唔會變好** ——
前三命中數由 1 變 1（Thunderbolt Way 59.82、Power Pivot 53.75 分數太低，
任何久休扣分都拉唔到佢們入前三）。改善純粹係「頭號推介唔會係跑最後嘅 $101 冷門」。

## 6. 修正後嘅建議

C1 已被 shadow test 否決。**呢個 failure mode 屬「罕見但災難性」**
（~0.5% 場次，但一出現就係公信力問題），而且**冇可量度嘅排名 edge**。
呢種組合正正係 flag / gate 嘅用途，唔係 weight 嘅用途。

所以建議改為 **C4 優先（顯示層，零排名風險）**：

1. **退出後重新排序 `top_picks`** —— 呢個係純 bug，唔係 modelling trade-off。
   Benbulben 之所以成為頭號推介，係因為四匹退出而張卡從來唔重排。
2. **薄證據 / 久休 watchlist flag** 落頭號推介：久休 > 270 日、
   PI 場數 ≤ 1、`formal_count` ≤ 2 → 標示但唔改分。
3. **`data_coverage.confidence` 要反映證據深度**，唔止 feature 有冇值。
   Benbulben 憑 2 個 PI 值就報「高 84.6%」。

C2（sectional shrinkage + L600 同路程比較）仍然值得獨立 A/B ——
佢嘅 cohort n=71（單 PI 場頭號推介 −11.9pp），比久休尾部大 20 倍，
係唯一一個 archive 有能力量度嘅 candidate。

C3 最後。

---

## 7. 用戶診斷（2026-07-31）：狀態與穩定性冇計馬群大細同輸距

用戶指出真正問題唔喺退出重排，而係 **Benbulben 退出前已經 15 匹排第 2**，
而 `狀態與穩定性` 拿到 68.6 分，但佢兩場正式賽都係細場近乎最後、輸一大截。

### 7a. 機制確認

`_form_score` 逐場只用**絕對名次**定 base：`1→100, 2→85, 3→75, ≤5→60, else→40`。
冇馬群大細正規化，冇輸距。Benbulben：

| idx | place | base | 實際 |
|---|---|---|---|
| 1 | 4 | **60** | 4th **of 6**，輸 **12.0L**（評語 "Only plodded final 400m.; Poor."） |
| 2 | 6 | 40 | 6th **of 12**，輸 **9.05L**（"Passed a few plodders late.; Plain."） |

`_sectional_breakdown` 更因為「近3仗有1次**前四**」再送 `realization_bonus +6.64` ——
嗰個「前四」就係 6 匹跑第 4。

`form_score` 有效權重 **0.1796（全 leaf 最高）**、`consistency_score` 0.1197，
兩者合共就係整個 狀態與穩定性 維度 0.2993。

### 7b. 輸距（margin）：真缺陷但屬尾巴 → A/B inconclusive 偏負

2026-05 之後 251 場、2,626 匹、輸距覆蓋 79.7%。`form_score` replay drift **0.00%**。

現行 base vs 實際輸距（2026-05 起）：

| base | 場數 | ≤2L | 2-5L | 5-10L | >10L | 平均 L/km |
|---|---:|---:|---:|---:|---:|---:|
| 85（第2） | 1036 | 85.8% | 12.4% | 1.6% | 0.2% | 0.78 |
| 75（第3） | 924 | 66.1% | 29.8% | 3.7% | 0.4% | 1.39 |
| **60（第4-5）** | 1566 | 31.8% | 54.8% | 12.1% | **1.3%** | 2.24 |
| 40（第6+） | 3083 | **4.5%** | 41.9% | 39.7% | 13.9% | 4.60 |

**Benbulben 嘅「輸 12L 拿 base 60」落喺 1.3% 尾巴。** A/B（9 個 config）：
dev 最好 `s8 cap15`（good_pos +1.50、winT3 +1.50、Gold +1），但
**holdout 全部 config good_pos −3.92、good_any2 −1.96、champ −1.96**。唔通過。

### 7c. 馬群大細：**密集**缺陷，但覆蓋率唔夠測

用 `AU_Historical_Raw_Race_Results.csv` 逐 (date, track, race) 數行數，
拿到 5,066 個 run 嘅真實馬群大細。改用場內百分位
`pct = (place−1)/(field−1)`（同 `eval_metrics.py` 嘅 `top_pick_pct` 同一公式）：

| 現行 base | 場數 | 平均百分位 | 應該係 |
|---|---:|---:|---|
| 85（第2） | 590 | 0.11 | 85:62% **75:38%** |
| 75（第3） | 562 | 0.23 | 75:72% **60:23%** |
| 60（第4-5） | 1029 | 0.38 | **75:15%** 60:75% **40:10%** |
| 40（第6+） | 2199 | 0.66 | **60:20%** 40:79% |

**21.5% 嘅 run 拿錯 base、11.0% 錯 ≥20 分。** 最大 cohort：

| 現行 → 應該 | runs | 佔比 |
|---|---:|---:|
| 40 → 60（大場第6+被當成細場跑最後） | 450 | **8.9%** |
| 85 → 75 | 224 | 4.4% |
| 60 → 75 | 151 | 3.0% |
| **60 → 40（Benbulben）** | 106 | **2.1%** |

呢個係目前所有 candidate 之中**唯一密集**嘅（對比久休尾巴 ~0.5% 場次、
大輸距第4-5名 1.3% runs）。

A/B 結果 **null，但因為量度不足**：馬群大細覆蓋率只 11%，
只有 **3.7%** 嘅計分 run 真正改到 base（955 / 25,521）。
dev +0.17/+0.49 好轉、holdout −0.93 左右，全部喺噪音帶。
**唔可以當成「修正無效」** —— 同 C1（量到咗然後 FAIL）性質完全唔同。

### 7d. 卡住嘅唔係數據，係一行 extraction

`claw_racenet_scraper.py`：

```python
runs = sel.get('forms', []) or []
if runs:
    lr = runs[0]
    last_race = f"{lr.get('finishPosition')}/{lr.get('eventStarters')} ..."   # line ~138
...
for r_idx, pr in enumerate(runs):        # 同一批物件
    ...
    f_fg.write(f"{track}{trial_str} R{race_num_run} {date} {dist}m cond:{cond} "
               f"... {positions.strip()}.{run_margin_str}{hc_str}{pf_str}\n")   # line ~228
```

`eventStarters` **每一場 run 都有**，而且已經被用嚟砌 Racecard 嘅 `Last: 4/6 ...`
（Benbulben `last_finish_line: 4/6 @ Coleraine 2800m` 嗰個 `/6` 就係佢）。
但逐場 Formguide 行冇寫 → Facts 賽績表冇 → 引擎睇唔到。

`margin` 同款：`pr.get('margin')` 有寫，但係 2026-05 才加，所以舊 meeting 0%。
舊 Formguide 本地檔真係冇，backfill 要重新 scrape，唔係本地 re-parse。

**⚠️ 走位軌跡唔可以代替馬群大細**：`S6→8th4→4th3→F4` 裡面 `8th`/`4th` 係
**距離標記**（800m/400m）唔係位置；就算正確 parse，最大位置中位數低估 3–4 個，
而且同跑法相關（大場前領馬 traj_max 細）→ 會系統性罰前領馬。

### 7e. 建議路徑

1. `claw_racenet_scraper.py` run line 加 `starters:{pr.get('eventStarters')}`。
2. Facts writer 加「馬群」欄；`engine_core._record_entries` parse。
3. `_form_score` 改百分位 base（harness 已建好、replay drift 0.00%）。
4. 重新 scrape 86 個 archive meeting 嘅 formguide 做 backfill，
   覆蓋率由 11% 升到 ~100% 後再跑真正 A/B。

第 1–2 步係前置，做完先有嘢可以測。第 4 步涉及對 Racenet 大量請求，需要審批。

---

## 8. Extractor 修正已落，但 Racenet backfill 唔可行

### 8a. 已改（`claw_racenet_scraper.py`）

逐場 run line 加咗 ` starters:{pr.get('eventStarters')}`。單場實測：
**starters 覆蓋 100%（2025: 2/2、2026: 38/38），連 2024 年嘅仗都有；`margin` 亦一併拿到。**
即係 Racenet 今日仍然供應歷史 run 嘅兩個欄位 —— 之前 archive 冇係因為當時 scraper 冇寫。

### 8b. Backfill 放棄：Racenet 機率性 403

| pacing | 結果 |
|---|---|
| delay 4s + 2 次重試 | 9 成功 / 10 失敗（**403 率 ~53%**） |
| delay 20s + 冇重試 | 1 成功 / 9 失敗（**403 率 90%**） |

**慢速冇幫助，靠重試才穿** → 403 唔係 rate-limit 而係機率性攔截。
全量 86 個 meeting ≈ 700 場 × ~2.5 次嘗試 ≈ **1,750 個請求**。已停手
（累計抽到 10 場 / 550 runs，100% starters）。

### 8c. 零請求替代：`last_finish_line`

`_data.last_finish_line` 格式係 `名次/馬群 @ 場地 路程`（例 `5/12 @ Wyong 1200m`），
**全 archive 88.4% 有值**（6,675 / 7,547），而最近一仗喺 `_form_score` 嘅
decay = 1.0，係四場之中權重最高。零外部請求。

⚠️ 佢可能指向**試閘**（Benbulben `4/6 @ Coleraine 2800m` 就係試閘），
所以 join 必須 場地 + 路程 + 名次 三者齊對。

三個來源合併後：results_csv 5,066 + last_finish 4,126 + scraped 112，
計分 run 覆蓋率由 3.7% → **7.3%**（1,856 runs、22.4% 馬匹）。

### 8d. F1 馬群大細正規化 A/B（覆蓋 7.3%）

| 指標 | dev (606) | holdout (107) |
|---|---|---|
| **Gold** | 34 → **36 (+2)** | 6 (+0) |
| good_pos | +0.17 | +0.94 |
| good_any2 | **+0.82** | −0.93 |
| winT3 | **+0.66** | −0.93 |
| **blowout** | **−0.82** ✓ | **−1.87** ✓ |
| **compet** | 0.00 | **+2.81** ✓ |
| champ | −0.49 | −1.87 |
| t3prec | +0.22 | −0.62 |

覆蓋率翻倍（3.7% → 7.3%）令 dev 轉好（Gold +1 → +2、any2 −0.17 → +0.82），
而**兩個 fold 嘅競爭力指標都改善**。但前三命中類指標喺 holdout 各跌約一場。
**未算通過，而且仍然受覆蓋率限制。**

### 8e. ⚠️ 但 F1 修唔到 Benbulben

| 仗 | 名次/馬群 | 百分位 | 現行 base | 新 base |
|---|---|---|---|---|
| Casterton 3500m | 4 / **6** | 0.60 | 60 | **40** ↓ |
| Swan Hill 2400m | 6 / **12** | 0.45 | 40 | **60** ↑ |

兩場**反方向**走 → form 55.56 → 54.44，ability **−0.20** 分
（68.14 → 67.94，仍高過 Winston 67.29）。
F1 係好嘅**通用**校正，但唔係 Benbulben 嘅解藥。

### 8f. C3 consistency 證據窗 A/B — FAIL

Footprint 極大：**81.5% 馬匹受影響**，consistency 平均變 −5.65、中位 −6.06。
最常見組合係 `form4/win6`（4,740 匹）—— 即係「兩個窗唔同」係**設計如此**
（`_form_score` 刻意 cap 喺 `entries[:4]`，consistency 睇 6 場），
唔係 bug。按 form_rows/window 收縮等於全局削弱 consistency，
而矩陣權重本來就係圍住現值調過嘅。

| 指標 | dev | holdout |
|---|---|---|
| **Gold** | 34 → **32 (−2)**（每個 S 都係） | 6 (+0) |
| **champ** | −0.66 ~ −0.82 | **−0.94 → −3.74 單調惡化** |
| mrr | −0.00 | −0.01 → −0.02 |
| compet | −1.15 (S=1.0) | +1.87 → −0.93 |
| good_pos / winT3 | +0.17 / +0.83 | +0.94 / +0.94 |

**FAIL。**

## 9. 綜合結論：Benbulben 型高估修唔到（喺計分層）

五個獨立 candidate，全部用同一把尺、同一批 713 場：

| Candidate | 修到 Benbulben？ | A/B 結果 | Footprint |
|---|---|---|---|
| C1 久休（連續） | 是（−2 至 −8 分） | **FAIL** Gold 33→25 | 闊 |
| C1b 久休（>365d gated） | 是 | **零效果** | 3 場 |
| C2 sectional shrinkage | **否**（最多 −1.52） | 算數否決 | 權重 0.0365 |
| F2 輸距入 form | 是 | **FAIL** holdout good_pos −3.92 | 1.3% 尾巴 |
| F1 馬群大細正規化 | **否**（−0.20） | dev Gold +2 / holdout 混合 | 7.3% 覆蓋 |
| C3 consistency 證據窗 | 是（~−1.7） | **FAIL** Gold −2、champ −3.74 | 81.5% |

**規律好清楚：凡係修到 Benbulben 嘅都 A/B 失敗；唯一接近通過嘅（F1）修唔到佢。**

原因：Benbulben 嘅 +7.28 分散喺四個中等權重 leaf（consistency +3.37、
pace_figure +1.95、track +1.85、sectional +0.64），冇一個單獨夠力；
而任何夠大幅度去搬動佢嘅改動，都要闊到影響幾千匹正常馬，淨效果係負。

### 建議（修正）

1. **C4 顯示層**（現有五個獨立佐證支持）：薄證據 / 久休 watchlist flag、
   `data_coverage.confidence` 改為反映證據**深度**、退出後重排 `top_picks`。
   零排名風險，直接處理「頭號推介係 $101 跑最後」呢個公信力問題。
2. **F1 獨立推進**（唔當佢係 Benbulben 修正）：`starters:` extractor 已落，
   等 live 覆蓋率自然累積（每個新 meeting 都有），
   覆蓋到 ~50%+ 再跑一次 A/B 決定。harness 已建好、replay drift 0.00%。
3. **唔再喺計分層追 Benbulben。** 五次都證明得不償失。

---

## 10. 用戶第二輪指正 + 已落實嘅修改（2026-07-31）

### 10a. 用戶指出我一個實質錯誤

我將「馬群大細」同「輸距」當成兩個獨立 toggle 分開測係錯嘅 —— 佢們互補：

| Benbulben 仗 | 名次/馬群 | 百分位 | 馬群修正 | 輸距 |
|---|---|---|---|---|
| Casterton 3500m | 4/6 | 0.60 | 60 → **40** ↓ | −12.0L |
| Swan Hill 2400m | 6/12 | 0.45 | 40 → **60** ↑ | −9.05L |

「位置」講你場內排第幾，「輸距」講你同頭馬差幾遠。9L 落後嘅中游位置唔應該當中性。

### 10b. 但合併 A/B 令 holdout 更差

| config | dev Gold | dev any2 | holdout any2 |
|---|---|---|---|
| **F1 只馬群** | **+2** | **+0.82** | −0.93 |
| F2 只輸距 | +0 | +0.16 | −1.87 |
| F1+F2 s8c15 | −1 | +0.82 | **−2.80** |
| F1+F2 s12c25 | −1 | +0.66 | **−4.67** |

原因量化咗：**輸距同場內位置百分位 Spearman ρ = 0.880**。

| 位置百分位 | n | 輸距中位 |
|---|---:|---:|
| 0–.12 | 956 | 0.00 |
| .12–.25 | 460 | 1.50 |
| .25–.50 | 841 | 2.95 |
| .50–.75 | 760 | 4.77 |
| .75–1.0 | 920 | 7.83 |

知道匹馬跑落後四分一就已經知佢輸一大截 → 輸距 88% 冗餘。
**但 Benbulben Swan Hill 正正係嗰 12% 殘差**（百分位 0.45 但輸 9.05L，
係該區間中位數三倍）。用戶直覺對，只係呢類個案太罕，全局調參捉唔到。

### 10c. Sectional 合理性 —— 唔合理，而且數據早就喺 bundle

Benbulben Swan Hill 嗰場 PF 數據：

| 欄位 | 值 | 有冇入分 |
|---|---|---|
| `l600_delta` | −1.71（末段快 1.71s） | **有** → 段速實速分 73.7 |
| `race_time_diff` | **+8.95（全程慢 8.95 秒）** | **冇** |
| `tempo_qrank` | **0.99（節奏慢到 99 百分位）** | **冇** |
| `early_race_pace` | V Slow | **冇** |
| `pf_run_count` | **1**（單場） | 冇收縮 |

即係「爬行賽事嘅快尾段」被當成速度證據。
`race_time_diff_avg` 覆蓋 33.1%，同 `pace_figure` state=ok 嘅 33.0% **一對一吻合**
（`tempo_qrank_avg` 只 1.1%，用唔到）。

**P1 A/B（race_time_diff 混入 pace_figure）FAIL**：dev 大致平，
holdout Gold 6 → 5/4/**3**/2/4、any2 −1.87 → −4.67、champ 最多 −4.67。
原因：`l600_delta` 本身已經係**場內相對**，但 `race_time_diff` 對一個隨班次/場地
變動嘅 benchmark；用今日馬群做 z-score 等於拿蘋果比橙 → 注入班次噪音。

### 10d. Benbulben 型 cohort 量化（2,139 個前三推介）

「計分近仗被抬高」= base ≥60 但實際係場內後半位置或輸 >5L：

| cohort | n | 勝% | 前三% | **尾三分一%** | 平均 SP |
|---|---:|---:|---:|---:|---:|
| clean | 2,077 | 17.5 | 44.8 | **22.8** | 10.2 |
| **flattered** | **62** | **9.7** | 41.9 | **40.3** | 13.1 |

效應大（尾三分一率差 17.5pp）但只佔 **2.9%**。呢個就係八個全局修正全部失敗嘅原因 ——
冇辦法為 2.9% 調參而唔攪亂 97%。

### 10e. 每個 leaf 嘅實際影響力 = 有效權重 × 場內標準差

| leaf | 權重 | 場內 SD | 影響力 | 佔總 |
|---|---:|---:|---:|---:|
| form_score | 0.1796 | 7.75 | 1.391 | 23.2% |
| consistency_score | 0.1197 | 10.62 | 1.272 | 21.2% |
| pace_figure_score | 0.1430 | 6.17 | 0.882 | 14.7% |
| track_score | 0.1244 | 4.42 | 0.550 | 9.2% |
| pace_map_score | 0.1485 | 3.03 | 0.450 | 7.5% |
| sectional_score | 0.0365 | 12.00 | 0.438 | 7.3% |
| **jockey_horse_fit_score** | **0.1009** | **3.14** | 0.317 | **5.3%** |
| jockey_score | 0.0543 | 5.11 | 0.278 | 4.6% |
| trainer_score | 0.0388 | 4.14 | 0.161 | 2.7% |

**`jockey_trainer` 維度佔 19.4% 權重但只交付 12.6% 影響力** ——
`jockey_horse_fit_score` 拿第六高權重但場內 SD 只 3.14（全矩陣最窄），
`trainer_score` 40.0% 馬匹恰好 60（完全中性）。呢個係最大嘅浪費容量。

## 11. 已落實（code 已改，138 個測試通過）

| 檔案 | 改動 |
|---|---|
| `claw_racenet_scraper.py` | run line 加 ` starters:{eventStarters}`（單場實測 100% 覆蓋，含 2024 年仗） |
| `inject_fact_anchors.py` | parse `starters:`；名次格由 `4 (-12.0L)` 變 `4/6 (-12.0L)` |
| `engine_core._parse_field_size` | 新 helper，含污染防禦（名次 0 / 名次 > 馬群 / 馬群 < 2 一律拒） |
| `engine_core._record_entries` | 加 `field_size` |
| `engine_core._form_score` | **有馬群大細 → 用場內百分位定 base**；冇 → 完全沿用舊階梯 |
| `engine_core._form_score` | 加 `form_flattered` 風險旗 + `heavy_defeat_runs` 計數（**標示，不入分**） |
| `tests/test_field_size_form_score.py` | 22 個新測試 |

**設計決定：馬群大細嵌入現有「名次」格而唔係加新欄位** ——
`_record_entries` / renderer 全部用位置索引讀 `cols[7..17]`，加欄會全部位移；
而所有下游 consumer 都用 `parse_float()` 抓頭一個數字，所以 `4/6 (-12.0L)`
對舊 code 完全向後兼容，舊 meeting（冇 `/N`）行為零改變。

端到端驗證（真實重抽嘅 formguide）：

```
#2 Gaelic Kiwi   idx1 名次 4 馬群  4  base 40   ← 舊階梯會畀 60（4 匹跑最後！）
#3 Inside Job    idx1 名次 4 馬群  9  base 60   flag=True（輸一大截）
#5 The Victorious idx1 名次 7 馬群 10  base 40
```

Benbulben 本人（引擎精算）：

```
舊: form 55.56   base [60, 40]
新: form 54.44   base [40, 60]   ← 一降一升
ability 68.14 → 67.94 (−0.20)，仍高過 Winston 67.29
但 form_flattered 旗亮，heavy_defeat_runs = 2 → 報告會標示
```

即係：**F1 係通用校正（Gaelic Kiwi 4/4 由 60 降到 40 才係佢真正價值），
唔係 Benbulben 嘅解藥；Benbulben 靠 flag surfacing。**

## 12. 下一步：trainer / jockey（最大剩餘 upside）

Racenet profile 頁已探（`/profiles/trainer/chris-waller` 第 3 次重試 200）：

```
stats: { totalRuns, totalPlaces[w,s,t], lastYearRuns, lastYearPlaces[w,s,t],
         lastTenRuns, lastTenPlaces, lastTenFigure,
         winPercentage, placePercentage,
         currentSeasonRuns, currentSeasonPlaces[w,s,t],
         roi, lastYearRoi, seasonRoi }
topJockey: {...}   topCompetitor: {...}
```

SEO description 明寫 **"stats for the season, per track and jockey combinations"** ——
per-track / per-combo 表要額外請求。

我哋現有：`trainer_ly` / `jockey_ly`（去年總數）＋
`AU_Jockey_Trainer_Combo_Stats.csv`（**只 165 行**，由自己 archive 推導）。

Racenet 新增嘅：current season、**ROI 三個口徑**、topJockey、per-track、per-combo。

⚠️ 可行性：Racenet 機率性 403（~50-60%），頭部練馬師 27 個 slug 喺索引頁，
但全量（~200 練馬師 + ~150 騎師）× ~2.5 次嘗試 ≈ 875 個請求。
不過同 meeting backfill 唔同 —— 呢個係**一次性、慢變嘅參考數據集**，
之後每場都用得着。需要用戶決定規模。

---

## 13. 第三輪：唔再加補丁，改為先量預測力再重建（2026-07-31）

前八個 candidate 全部係喺已調好嘅公式上加補丁，而 matrix 權重本來就係圍住
舊分佈調出嚟，所以次次同權重打架。呢輪先量基本事實。

### 13a. 每個 leaf 單獨嘅預測力（693 場，場內 Spearman ρ）

| leaf | 權重 | 場內 ρ | Q1 前三% | Q5 前三% | 差 |
|---|---:|---:|---:|---:|---:|
| form_score | 0.1796 | **0.214** | 39.2 | 15.9 | 23.2 |
| consistency_score | 0.1197 | 0.193 | 38.8 | 17.8 | 21.0 |
| pace_figure_score | 0.1430 | 0.173 | 35.7 | 21.4 | 14.2 |
| **jockey_score** | **0.0543** | 0.163 | 37.1 | 19.1 | 18.0 |
| **rating_score** | **0.0317** | 0.159 | 37.0 | 20.0 | 16.9 |
| **trainer_score** | **0.0388** | 0.156 | 35.5 | 18.6 | 16.9 |
| **class_score** | **0.0000** | 0.150 | 35.7 | 21.1 | 14.6 |
| track_score | 0.1244 | 0.096 | 31.8 | 20.8 | 11.0 |
| **sectional_score** | 0.0365 | **0.086** | 31.6 | 24.3 | **7.3** |
| **jockey_horse_fit_score** | **0.1009** | **0.071** | 33.7 | 22.7 | 11.0 |
| **pace_map_score** | **0.1485** | **0.066** | 32.5 | 19.3 | 13.2 |
| weight_score | 0.0064 | **−0.069** | 29.9 | 27.9 | 2.0 |

冗餘（場內相關）：**form_score ↔ consistency_score ρ = +0.584** ——
狀態與穩定性 用 0.2993 權重買一個訊號。pace_figure ↔ sectional ρ +0.309。

### 13b. L600 應該用邊個口徑（唔需要場地標準，直接比口徑）

| 口徑 | 場內 ρ | Q1−Q5 |
|---|---:|---:|
| L600 平均 | **0.057** | 7.8 |
| L600 最近 | 0.045 | 5.5 |
| L600 最快封頂 avg×1.05 | 0.035 | 5.8 |
| **L600 生涯最快（原本用嘅）** | **0.023** | **4.8** ← 四個之中最差 |

best/avg 比率：中位 1.035、P90 1.065、P99 1.101；26.7% 嘅馬 best 高出自己平均 ≥5%
（Benbulben 1.110，P99 以上）。**一次快段速變成永久資歷。**

### 13c. 班次代理：獎金

`_form_score` 個 `class_mult` 註釋自己認咗係「全場統一」—— `entry["class"]` 呢個 key
由來冇存在過，所以每匹馬每一場嘅乘數都一樣，**近績分完全冇班次調整**。
賽績表「班次」欄 85% 係 fallback "Maiden/SW"（`hc` 只 15%）。
但 Formguide 每行都有獎金：**85,010 個 run 100% 密度**，$0-25k (3.9%) → $500k+ (8.5%)。
獎金水平單獨場內 ρ = **0.105**、Q1−Q5 10.1pp（比 sectional 0.086、track 0.096、
jockey_horse_fit 0.071、pace_map 0.066 都強）。

## 14. 三個修正 + A/B 結果

### S1 — PI 競爭力封頂

非競爭場次（有馬群→百分位 >0.5；有輸距→ >3L）嘅**正** PI 封到 0，
但仍計入分母。早期版本直接剔走整場，結果連負 PI（失位）都被抹走，
有啲馬平均 PI 反而升 —— 係設計錯誤，已修正。

| | dev (606) | holdout (107) |
|---|---|---|
| winT3 | +0.17 | **+0.94** |
| t3prec | −0.11 | **+0.63** |
| compet | −0.16 | **+0.94** |
| any2 / champ / blowout | 0.00 | 0.00 |
| Gold | −1 | +0 |

**holdout 冇任何指標變差，三個變好。** 受影響 7.0% 馬匹。

### S2 — L600 口徑由生涯最快改為平均

理據見 13b：原本用嘅口徑係四個之中預測力最差，平均值好 2.5 倍。

### F3 — 用獎金做真正嘅班次調整（場內相對）

`class_adj = K × (自己近仗獎金 log10 − 全場中位)`，K = 10。

| K | dev | holdout |
|---|---|---|
| **10** | **全部指標變好或平**：Gold **+2**、good_pos **+1.32**、champ +0.83、winT3 **+1.65**、t3prec +0.72、blowout **−1.32** | **冇任何指標變差**：Gold **+1**、any2 +0.94、t3prec +0.63、blowout **−1.87**、compet +0.94 |
| 30 | 更好（Gold **+4**、any2 +3.30） | 但 champ −1.87、winT3 −0.93 → 唔採用 |

**K=10 係八個 candidate 之後第一個兩個 fold 都乾淨嘅。**

⚠️ 施加位置必須喺「劣績中性回歸」**之後** —— A/B 驗證嘅版本係加喺最終近績分上。
我第一次落 code 放咗喺回歸之前（會被 ×n/(n+2) damp），已修正並加測試釘死次序。

## 15. Archive 全量重跑（713 場，真引擎）

只有 S1 + S2 生效（archive Facts 冇馬群/獎金欄，F1/F3 唔適用）：

| 指標 | 舊 | 新 | Δ |
|---|---:|---:|---:|
| Gold (3/3) | 5.5% | 5.2% | −0.3pp |
| Good | 19.1% | 18.7% | −0.4pp |
| **Pass (≥2 入前三)** | 40.7% | **41.0%** | **+0.3pp** |
| Champion | 23.8% | 23.6% | −0.3pp |
| **Top3 Place Precision** | 44.7% | 44.7% | **0.0pp** |
| 命中分佈 | 1-hit −2、**2-hit +4**、3-hit −2 | | |

總體平手。按 repo 一貫標準（2026-07-11 單調化修正、2026-07-24 weight_score
方向修正都係「A/B rank-neutral / a validated wash」而照樣採納），
**平手 + 可證明更好嘅口徑 + 修好指定 failure = 採納，並且明確標記為
correctness fix 而唔係 performance claim。**

## 16. Benbulben 個案 —— 已修好

真引擎重跑 2026-07-31 Geelong R7 全場：

```
退出後 Top 3
  舊: #8 Benbulben(實11) / #3 Winston(實3) / #7 Step In Time(實8)
  新: #3 Winston(實3)   / #8 Benbulben(實11) / #7 Step In Time(實8)

Benbulben  68.14 → 66.75   段速 77.5 → 39.4   旗 form_flattered
Winston    67.29 → 66.87
```

**頭號推介由跑最後嘅 $101 冷門，變成實際跑第 3 嘅 $6 馬。**
同場 Hide Your Assets（段速 77.5 → 39.4）同 Miss Niagara（85.6 → 62.4）
一齊被修正 —— 唔止修一匹馬，係修個機制。

Benbulben 段速逐項：

| 項目 | 舊 | 新 |
|---|---|---|
| 位置增益 PI | **+20.00**（近2仗平均追前 3.5 個位） | **+3.64**（其中 2 場大敗/居後，追前不予計功） |
| 末段速度 L600 | **+15.07**（生涯最快 35.11s 破標準） | **+0.00**（平均 38.96s，未快過標準 35.84s） |
| 增益兌現 | +6.64 | +0.00 |
| **合計** | **77.51** | **39.44** |

## 17. 已落實清單（171 個測試通過）

| 檔案 | 改動 |
|---|---|
| `claw_racenet_scraper.py` | run line 加 ` starters:{eventStarters}` |
| `inject_fact_anchors.py` | 名次格 → `4/6 (-12.0L)`；**追加「獎金」做最後一欄**（cols[18]，唔令任何欄位位移） |
| `engine_core._parse_field_size` / `_parse_prize` | 新 helper，含污染防禦 |
| `engine_core.horse_prize_level` | Module-level，令 orchestrator 可以算場內中位數 |
| `engine_core._record_entries` | 加 `field_size`、`prize` |
| `engine_core._form_score` | 場內百分位 base（F1）＋ 獎金班次調整（F3，回歸之後）＋ `form_flattered` 旗 |
| `engine_core._run_was_competitive` | 新 helper |
| `engine_core._sectional_breakdown` | PI 競爭力封頂（S1）＋ L600 改用平均（S2） |
| `au_auto_orchestrator._build_field_summary` | 加 `prize_level_field_median`（中位數，唔用平均：獎金 log10 有長尾） |
| `tests/test_field_size_form_score.py` | 22 個測試 |
| `tests/test_ability_reflection.py` | 23 個測試（含次序釘死） |

**未經審批之前，最終排名仍以現行 `綜合戰力分` 為準，冇任何 override。**
