# EXP-20261111-08 HKJC「能力高過評分」（well-in）screening

- **日期**：2026-11-11（假設同判決規則喺睇結果之前寫）
- **平台**：HKJC
- **觸發**：Kelvin：「評分做 base，負磅做調整……如果隻馬勁過評分即係有負磅優勢，應該有更好嘅 class score」；
  「我哋個 model 應該點樣體現到一隻馬有負磅優勢？」
- **搜索過嘅舊記錄**：EXP-20260904-03（評分直接入 class_score 9 個 arm REJECT）、EXP-20261029-30（評分差距代替負磅，
  forward `weight_rating_gap` 30/60 中）、memory `hkjc-top-weight-is-the-missing-signal`（控制模型排名後頂磅 +8.7pp）、
  AU `au-handicapper-undercompensates`（AU well-in 殘差 AUC 0.4989）。**HKJC 冇測過 well-in**
- **改到嘅檔案／組件**：**冇。純量度**；唔郁 `weight_rating_gap` forward

## 假設
同一場之內，**模型自己對能力嘅估計（唔含負磅／班次維度）固定之後，官方評分越低越著數**
（即係評分低過實力 = 負輕磅 = well-in）。可證伪：條件係數係正（評分越高越好）就 REJECT。

## 定義（預先定）
- **語料**：`hkjc_eval_harness run --dump-matrix`（PIT 回放，baseline 引擎），排除初出馬同死欄位場次
- **評分**：排位表官方評分（`_parse_racecard_meta`），賽前資料
- **模型能力 A**：`ability_score_raw − W_class_advantage × matrix.class_advantage`（拎走包住負磅同班次嘅維度；
  場內常數唔影響排序）
- 兩者都做**場內 z-score**；只計讓磅賽（第一至第五班）；評分場內冇變化嘅場剔走
- **主測試**：場內上名（頭三）logistic `place ~ zA + zR`，`zR` 係數同 95% CI（按場次 bootstrap 1,000 次）
- **輔助**：well-in 組 = 場內 A 排頭三分一 **而且** R 排尾三分一；對比 A 頭三分一其餘馬，上名超額（相對場內期望）
- **對照**：`place ~ z(raw) + zR`（評分喺完整模型之上仲有冇用、乜方向）

## 判決規則（只開一次）
- **PASS（值得做引擎 A/B）**：主測試 `zR` 係數 < 0 而且 CI 上界 < 0，**同埋** well-in 組超額 > 0 而且 CI 下界 > 0
- `zR` 係數 > 0 而且 CI 下界 > 0 → **REJECT**：讓磅官評分知道嘅嘢多過我哋模型，well-in 用我哋嘅能力估計做唔到
- 其他 → **REJECT（冇訊號）**
- 唔換能力定義、唔換分組切點、唔加非讓磅賽去救

## 數據
- **語料**：`hkjc_eval_harness run --dump-matrix`（PIT 回放，baseline origin/main `7bc10b28`）441 場 → 讓磅賽、非死欄位、
  評分場內有變化、≥5 匹：**343 場 / 4,185 匹**（2026-05-03 → 2026-11-08），初出馬已剔
- 場內 ρ(模型能力 A, 評分 R) = **+0.180**（兩樣大致獨立，所以測試有意義）；ρ(weight_score, R) = +0.830（負磅分確實係評分代理）

## 結果

### 主測試：`place ~ zA + zR`
| 係數 | 估計 | 95% CI（場次 bootstrap 1,000） |
|---|---|---|
| **zR（評分）** | **+0.0280** | **[−0.0541, +0.1082]** |
| zA（模型能力） | +0.7580 | [+0.6697, +0.8578] |

模型能力固定之後，評分高低對上名**冇可量度嘅影響**；點估計仲係正（評分高少少好），即係唔係 well-in 方向。

對照 `place ~ z(完整模型) + zR`：zR −0.0172 [−0.1003, +0.0639] —— 完整模型（已經包負磅分）之上評分冇剩餘。
（舊 memory「控制模型排名後頂磅 +8.7pp」係 2026-09-04 負磅方向調轉**之前**、用「頂磅 dummy × 模型排名 4+」量嘅；
呢度係評分線性項，唔係同一個測試，只可以話「調轉之後完整模型之上評分冇線性剩餘」，冇重做頂磅 dummy。）

### 輔助：well-in 組
A 排場內頭三分一而 R 排尾三分一（357 匹）vs A 頭三分一其餘（1,132 匹）：
**−2.28pp [−8.33, +3.38]**（上名率 36.7% vs 39.0%）。well-in 馬跑得**唔好過**同樣被模型睇好、但評分較高嘅馬。

### A 三分位 × R 三分位（上名超額 pp；括號 n）
| | R低 | R中 | R高 |
|---|---|---|---|
| A高 | +12.67 (357) | +11.92 (480) | **+17.17** (652) |
| A中 | −3.29 (416) | −4.17 (480) | −2.86 (519) |
| A低 | −12.51 (488) | −12.48 (451) | −14.19 (342) |

差異幾乎全部由模型能力（行）解釋；同一行入面評分（列）冇一致方向。

## 檢查
- **leakage-audit**：PASS —— 評分讀排位表（賽前）；模型分係 PIT 回放；冇用賠率
- **功效**：zR CI 半寬約 0.08（相對 zA 0.76 約十分一）；中等大小嘅 well-in 效應會睇到，細嘅可能睇唔到
- **golden_scoring**：冇郁（冇改 code）；**退步**：冇

## 結論
HKJC **冇 well-in 訊號**。用我哋模型（拎走負磅／班次維度）做能力估計，評分高過或低過能力都唔影響上名；
「能力高、評分低」嗰組反而稍差（CI 跨零）。即係**我哋嘅能力估計未準到可以搵出讓磅官評錯嘅馬** ——
同 AU（well-in 殘差 AUC 0.4989）一樣。負磅優勢喺而家嘅模型入面冇可用嘅表達方式；
評分本身嘅資訊已經由負磅分（ρ 0.83）帶入，`weight_rating_gap` forward 會判「用評分定負磅」呢個較細嘅問題。

**決定**：REJECT（冇訊號）—— 唔開引擎 A/B
**commit**：未 commit 任何 model code

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out dump.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_well_in_screen.py dump.jsonl
```
