# EXP-20260826-03 — 2026-08-22 Randwick 十場逐場覆核：兩個修正、四個撤回

**狀態：SHIPPED（兩項），RETRACTED（兩項），REJECT（一項）**
**日期：** 2026-08-26 ・ **平台：** AU ・ **語料：** 1,611 場全歸檔 / 1,033 場 PF 可表達 / 809 場乾淨

## 起因

Kelvin 逐場覆核 2026-08-22 Randwick（R1–R10），觀察係「啲問題全部指向 pace_perf」。

先講語境：**呢日明顯差過平均**，所以唔可以由佢推結論（十場亦冇統計功效）。

| 指標 | 08-22 Randwick | 語料基準（745 場）|
|---|---:|---:|
| Pass | 40.0% | 50.3% |
| t3prec | 46.7% | 49.0% |
| 首選上名 | 50.0% | 60.3% |
| Gold | **0.0%** | 19.2% |
| champion | 30.0% | 26.6% |

## 追過但證實模型冇錯（八條）

| 線索 | 結果 |
|---|---|
| pace_perf 權重太高 | 五種量法全部反對（EXP-20260826-02）|
| PF 只係 rating 冗餘 | 唔係：rating 高/低兩半各加 +7.45 / +5.33pp，ρ=0.123 |
| rating 壓住贏馬（R5 Boniface）| rating_score −12.77→+10.83pp 單調，市場之上仲有增量 |
| jockey_trainer 壓住 $6 熱門（R7）| jockey 0.5896 / trainer 0.5850 AUC，高過 rating 0.5812 |
| 「Tier 1 精英馬房」係硬編碼 | 校準啱：n=90，+12.47pp，全表最高 |
| 模型 #1/#2 跑包尾（R6/R7）| 100% 覆蓋、零風險旗；blowout 率本身 16–19% |
| Anthracite 排 11 卻上名（R4）| 第 11 位上名 = 2.23% 事件，排啱咗 |
| Prima Bella 贏但 PF 26.3（R6）| PF 逐段單調 −7.83→+10.38pp，中性點 −0.23pp |

## 撤回（我自己量錯，記低以免再犯）

**1. `_JOCKEY_LY_PRIOR = 0.365` 唔係錯。** 我拎騎練嘅**季度**上名率（平均 34.87%）
同語料嘅 **runner-level** 上名率（29.68%）比 —— 兩個唔同 population。對返啱個
population，prior 只差 1.3–1.6pp，而且佢本身係搜索調出嚟嘅，唔係聲稱嘅經驗常數。

**2. `class_score` 冇任何一項方向調轉。** 我最初見到三個「調轉」嘅分值
（56.8 / 60.7 / 62.0），但嗰啲係**組合格**唔係單項。逐個 micro-term 反解再 bootstrap：
四個方向啱（career5_placed +11.00pp ✅、career5_unplaced −3.66pp ✅、
career15_unplaced −8.18pp ✅、career15_placed +4.98pp ✅），五個分唔開，**零個調轉**。

教訓：**組合格嘅超額唔可以當單項證據。** 要反解到 term 再逐個量。

## 修正一：`weight_score` 「降班配輕磅」方向調轉（SHIPPED）

`engine_core._weight_score`。舊 `+3`，判語「降班配輕磅，實際任務下降」。

| nudge | n | 超額 | 95% CI | |
|---|---:|---:|---|---|
| 降班配輕磅 **+3** | 1050 | **−5.64pp** | [−8.21, −3.10] | ❌ 調轉 |
| 升班兼高負磅 −3 | 1024 | +2.50pp | [−0.29, +5.39] | · 分唔開 |
| 爛地孭重磅 −4 | 711 | +2.98pp | [−0.40, +6.30] | · 分唔開 |

同 2026-07-24 基礎分審計同一個成因：**讓磅官係按能力派磅**。「降班仲要只獲輕磅」
係讓磅官睇低佢，唔係任務變易。改做 `−3`，判語改為「降班仍只獲輕磅，讓磅官對佢
評價偏低」。另外兩個唔顯著，**唔郁**（唔好靠點估計去「修」嘢）。

`weight_score` 2026-07-30 已退出排名，所以呢個係敘述真確性修正，**唔影響名次**。

## 修正二：`pace_perf` display gain 喺污染語料上 fit（SHIPPED，排名不變）

`MATRIX_DISPLAY_GAINS["pace_perf"] = 0.9909` 係喺一個**一半場次入面呢個維度係常數**
嘅語料上 fit。2026-05 之前嘅歸檔冇段速抽取，`pace_figure_score` 成場都係 60，
嗰 4,788 匹馬 raw SD 只有 **0.64**。

| 語料 | raw SD | 11/SD |
|---|---:|---:|
| 2026-05 之前（PF 全 60）| 0.64 | — |
| 2026-08-05 之前（設 gain 嗰陣）| 12.07 | 0.9115 |
| 2026-06+（PF 可表達）| 18.43 | 0.5969 |
| 2026-08-05+（乾淨）| 18.53 | **0.5937** |

舊 gain 完美符合公式 `11/11.10 = 0.991` —— 只不過餵咗個假 SD。後果係 pace_perf
成品顯示 SD 喺 live 語料係 **18.26**，其餘四維 10.16–12.81，即係大聲 1.68 倍：

| 維度 | ✅✅ | ❌❌ |
|---|---:|---:|
| stability | 8.3% | **0.4%** |
| pace_perf | 8.6% | **14.3%** |
| track | 11.2% | 0.4% |

**點樣做到排名一模一樣**：gain → 0.594，`MATRIX_WEIGHTS["pace_perf"]` 按
0.9909/0.594 補償到 0.203602，五個權重全體歸一（Σ 保持 1.0，所有工具嘅假設不變），
再由新常數 `MATRIX_ABILITY_SCALE = 0.9245976` 喺 `pure_7d_score` 度還原 ability 軸。

實測（1,611 場 / 16,253 匹）：

- ability max|Δ| **0.0016**（純 `round(...,2)` 噪音）
- grade 改變 **0**
- 頭三分差 max|Δ| 0.0027
- 排名改變 **2 場**（0.002 級數嘅平手換位）
- pace_perf 顯示 SD **18.26 → 10.95**（目標 11）
- golden：120 匹入面 118 匹 pace_perf 變，**綜合戰力分同 grade 一個都冇變**

⚠️ 過程中發現 ability 條式喺 repo 有**五份複本**（`engine_core`、`au_eval` ×2、
`au_matrix_refit` ×2、`golden_scoring`）。改一份唔改其餘，golden 同 A/B 就會靜靜
同真引擎分岔 —— 今次 `au_matrix_refit verify` 同 golden diff 兩重閘都捉到。五份已同步。

## REJECT：順手減 pace_perf 喺排名嘅份量

同一個 gain 修正，如果**唔**補償權重，就等於把 pace_perf 權重由 0.12205 減到 0.0732。
三個 gain 水平 × 三個語料 = 九格，**冇一格過閘**：主裁判（頭 5 位配對 AUC）全部跨 0，
而場數指標係 gold +0.56~+0.97 但 **pass −0.19~−1.45**。冇量到改善就唔改排名。

## 可重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out leaves.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data leaves.json
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform au
./檢查.sh
```

## 附帶：命名修正

`class_weight` 嘅顯示名由「級數與負重」改做「**官方評分對位**」。呢個維度嘅
`MATRIX_FORMULAS` 係 `rating_score × 0.70` —— 得一個 leaf。`class_score`
（2026-07-29）同 `weight_score`（2026-07-30）都已退出排名，叫「級數與負重」
會令人以為兩樣都入咗分，實情兩樣都冇。
