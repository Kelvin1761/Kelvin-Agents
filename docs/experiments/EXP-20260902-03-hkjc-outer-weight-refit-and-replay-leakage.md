# EXP-20260902-03 HKJC 七維權重 refit —— 兼發現回放 harness 一直有前視

- **日期**：2026-09-02
- **平台**：HKJC
- **提出人**：Kelvin —— 「檔位與走位最重、段速同狀態與穩定性咁輕，唔太合理」
- **假設**：`race_shape` 0.2737（七維最重）配 0.5473 場內 AUC（七維第二弱），
  而 `stability` 0.0983 配 0.6205（最準），權重同準確度錯配；重新 fit 應該有更好嘅版本。
- **搜索過嘅舊記錄**：`docs/experiments/` **零份 HKJC 記錄**（呢份係第一份）。
  Repo 內舊紀錄：`resources/04_walk_forward_calibration.md`（2026-07-30 competitiveness
  fit，`race_shape` 0.2560→0.2260）、`scratch/hkjc_competitiveness_outer_weight_fit_report.md`
  （ML learned `race_shape` 0.1923，recommendation **HOLD**）。memory
  `au-matrix-weights-tested-dont-change`、`leaf-auc-gains-do-not-convert-to-ranking`、
  `statistical-gates-do-not-catch-leakage`。
- **改到嘅檔案**：冇。全部係唯讀量度，model code 一行都冇郁。

## 零：先發現嘅嘢 —— 回放 harness 一直用緊未來資料

`engine_core.py:1353` 攞 `as_of_date = race_context.get("race_date")`，
`live_priors.temporal_source_is_safe()` 喺 `as_of_date is None` 時**直接返 True**。

而 264 份 `Race_*_Logic.json` 入面，`race_analysis` 得
`distance / field_horse_names / race_class / race_number / rail / speed_map / venue / verdict`
—— **零份有 `race_date`**。所以歷史守衛由頭到尾冇響過，回放 2026-04～07 嘅場次
時攞緊 `TrainerSignalPriors.temporal_mode = "latest_season_snapshot"`
同兩季 master stats，入面包住緊被評分嗰場賽果本身。

`review_auto_weighting.py`（生產覆核工具）行同一條路，所以佢出過嘅所有回測數字都受影響。

注入 `race_date` 之後（守衛生效、跌返 tier fallback）：

| | 洩漏版 | 乾淨版 | Δ |
|---|---:|---:|---:|
| `trainer_signal` 改變咗嘅 runner | — | — | **3,318 / 3,318 (100%)** |
| `trainer_signal` 平均分 | 61.52 | 70.20 | +8.68 |
| `trainer_signal` 場內 SD | 4.43 | 7.07 | +2.64 |
| `trainer_signal` 場內 AUC | 0.5968 | 0.5781 | **−0.0187** |
| gold_strict | 7.58% | 3.03% | **−4.55pp** |
| good | 27.65% | 23.48% | −4.17pp |
| champion | 27.27% | 26.14% | −1.14pp |
| NDCG@5 | 55.31% | 53.93% | −1.38pp |
| MRR | 0.4664 | 0.4546 | −0.0118 |

其餘六維 bit-identical（AUC Δ 全部 0.0000）—— 只有騎練線受污染。

⚠️ 乾淨版**唔等於**「當日真係會出嘅分」：生產環境喺賽前用當時嘅 master stats 係合法嘅，
守衛一響就跌落 tier fallback，係一個**降級代用品**。正解係按 meeting date 砌
point-in-time 快照（合約寫明要，但冇人實作）。所以而家兩個回放都唔係真相：
洩漏版樂觀、乾淨版悲觀。

## 一：refit 設定

- 語料 264 場 / 3,318 匹 / 26 個場次（2026-04-12 .. 2026-07-12，全季已完）
- 時間切分：dev 180 場（< 2026-06-13）／ holdout 84 場，holdout 冇參與任何擬合
- 目標函數：Plackett-Luce（官方頭三名次序），權重非負、和為 1，溫度由尺度吸收
- 選點：**200 次 dev bootstrap 取中位數（consensus，唔係 argmax）**
- 判決：Stage-4 式 —— primary = `gold_strict` / `good`，佐證 = `capture@5` / `NDCG@5`
- 兩個回放各跑一次

## 二：fit 出嚟嘅方向

| 維度 | live | 乾淨版共識 | 90% 區間 | 洩漏版共識 | 90% 區間 |
|---|---:|---:|---|---:|---|
| `race_shape` | 0.2737 | 0.1854 | [0.1449, 0.2347] **live 喺區間外** | 0.1678 | [0.1315, 0.2110] **live 喺區間外** |
| `trainer_signal` | 0.2362 | 0.1905 | [0.1387, 0.2525] | 0.2857 | [0.2122, 0.3610] |
| `stability` | 0.0983 | 0.1732 | [0.1216, 0.2312] **live 喺區間外** | 0.1372 | [0.0927, 0.1911] |
| `class_advantage` | 0.1428 | 0.1492 | [0.0404, 0.2764] | 0.1269 | [0.0318, 0.2476] |
| `sectional` | 0.1285 | 0.0887 | [0.0224, 0.1560] | 0.0664 | [0.0047, 0.1260] **live 喺區間外** |
| `horse_health` | 0.0404 | 0.1102 | [0.0000, 0.2327] | 0.1214 | [0.0005, 0.2256] |
| `form_line` | 0.0801 | 0.1028 | [0.0333, 0.1550] | 0.0946 | [0.0401, 0.1388] |

**兩個回放一致嘅只有一樣：`race_shape` 應該落到 0.17–0.19，比 live 低約 10pp。**
`stability` 兩邊都指向上（乾淨版顯著）。`trainer_signal` 兩邊符號相反 —— 純粹係 §0 嗰個
洩漏，未有 point-in-time 之前唔可信。`sectional` **兩個 fit 都要求向下**，Kelvin 直覺嗰半
唔成立。`horse_health` 兩邊都想加，但佢場內 AUC 0.4952（低過擲毫），係 fit 食緊噪音。

另外：ridge λ 用 dev 內部時間 fold 揀，**單調揀到最大值 λ=32**（收埋去均勻權重）。
即係 likelihood 對權重向量幾乎冇分辨力 —— 同 AU「edge-walking 讀到『最優』其實係『平坦』」
同一個病。

## 三：判決 —— REJECT

HOLDOUT（84 場）配對 bootstrap，consensus − live：

| 指標 | 乾淨版 | 洩漏版 |
|---|---|---|
| `gold_strict` | +2.42pp [−2.38, +7.14] | −1.09pp [−5.95, +3.57] |
| `good` | +1.16pp [−7.14, +8.33] | −2.43pp [−8.33, +3.57] |
| `champion` | **−5.93pp [−11.90, +0.00]** | +0.01pp [−3.57, +3.57] |
| `capture@5` | −1.55pp [−5.16, +1.98] | +2.02pp [−1.19, +5.16] |
| `NDCG@5` | −0.66pp [−3.16, +1.85] | +0.39pp [−1.90, +2.69] |

**冇一個 primary 指標喺任何一個回放贏到（CI 全部跨零），而乾淨版 `champion` 明顯輸。**
判 **REJECT** —— 同 AU 重配權重第五次 REJECT 完全同形。

功效前置條件亦唔成立：holdout 84 場，`gold_strict` 一場 = 1.19pp，
所謂「+2.42pp」係 **2 場**。呢個語料量根本判唔到七個權重。

## 四：留低嘅嘢

1. **回放前視係真缺陷，要修**：按 meeting date 砌 point-in-time 騎練快照
   （results DB 有兩季 176 個比賽日，夠料砌）。修好之前，HKJC 所有回測數字
   （包括我今日之前報嗰批）都要當受污染。
2. **`race_shape` 過重呢個方向，兩個獨立方法 + 今次 refit 三次都指同一邊**
   （2026-07-30 competitiveness fit 0.2260、ML learned 0.1923、今次 0.17–0.19），
   但三次都過唔到閘。呢個唔係「冇問題」，係「264 場判唔到」。
3. **`sectional` 想加權重呢個直覺唔成立** —— 兩個 fit 都要求佢向下。
4. 真正瓶頸唔喺配權，喺 `race_shape` 入面兩塊死 leaf（`fit_score` AUC 0.5089、
   `trip_score` 0.4887，佔沙田組合 45%）同語料量。
