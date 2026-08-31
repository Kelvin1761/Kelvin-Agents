# EXP-20260831-03 pace_figure 拆解：11.49% 權重，一個場級欄位

- **日期**：2026-08-31
- **平台**：AU
- **假設**：`pace_figure_score` 量緊嘅唔係本駒步速，而係佢跑過嘅賽事有幾快；
  用同一頁已有嘅逐駒數據個體化，可以提升判別力。
- **搜索過嘅舊記錄**：`EXP-20260826-01/02`（pace_perf 距離對調、權重重驗）、
  `EXP-20260826-03`（0822 Randwick，display gain 修正）、`EXP-20260831-02`
  （合成層失效 cohort）。**冇人試過重建個特徵本身** —— 之前全部係權重／
  gain／分層。
- **改到嘅檔案／組件**：冇（純拆解＋離線量度）

## 現行實作

`engine_core._pace_figure_score`（顯示名「**L600 環境分**」）：

```
value = pf_aggregates["l600_delta_avg"]        # 逐條往績嘅 l600_delta 平均
z     = (value − 場內平均) / 場內標準差
score = clip(60 − z × 20)
```

公式本身唔複雜 —— 一個場內 z-score。複雜嘅係上游 `_pf_aggregates`。

### 佢食緊咩數據：**得一個欄位**

`_parse_pf_token` 支援 12 個 per-run 欄位。實測 1,070 個 Logic /
73,806 條 pf_runs（2026-08-05 起）：

| 欄位 | 非空率 |
|---|---:|
| `l600_delta` | **100.0%** |
| `l600_time` / `runner_time` / `race_time_diff` / `l800_delta` / `l400_delta` / `l200_delta` / `tempo_qrank` / `rt_rating` / `early_runner_pace` / `early_race_pace` | **0.0%** |

`source` 全部係 `sportsbet_race_context`。嗰十個空欄位係 **Racenet 遺留**
（2026-08 剷走）。所以 `_pf_aggregates` 入面 7 個 `_PF_SPLIT_KEYS` 各計
`_avg`/`_best`、tempo、rating、early pace 全部係**死 code 喺一個欄位上空轉**。

### 語意問題（code 自己嘅 docstring 已經寫明）

> "Sportsbet values are **race-level and identical for runners from the same
> historical race**. They describe **speed tests faced, not the horse's own
> individual sectional**."

即係「呢匹馬跑過嘅賽事最後 600m 有幾快」，唔係「呢匹馬最後 600m 跑得幾快」。

## 未用嘅逐駒數據（同一條 form line 上面）

實測 1,005 場 / 69,790 條往績：

| 欄位 | 覆蓋 |
|---|---:|
| `starters` | 100.0% |
| `margin`（落後距離） | 97.4% |
| `400m 位置` | 78.6% |
| `800m 位置` | 77.8% |
| `WinningTime` | 60.8% |
| `Settled` 位置 | 43.7% |

⚠️ `finish:` / `RaceClass:` / `WinningTime` / `Source:` 大約 **2026-08-26**
先加入抽取層；之前嘅 formguide 冇。用 `finish:` 做必需欄位會令
113/138 個場次靜靜咁零往績（本實驗一度中招）。`margin` 冇呢個問題。

## 結果：場內 AUC（預測今場上名），1,000 場

| 候選 | AUC | 對現行差 | 95% CI | |
|---|---:|---:|---|---|
| 現行 `pace_figure_score`（CSV 實值） | 0.5326 | — | | |
| **A** 純場級 L600 平均 | 0.5329 | +0.0003 | [−0.0013, +0.0019] | 打和 → **重現無誤** |
| **B** 場級 + 本駒落後秒數（`margin×0.17`） | 0.5924 | **+0.0598** | [+0.0504, +0.0688] | ✅ |
| **C** 只用落後距離（完全唔要 L600） | **0.6205** | **+0.0879** | [+0.0704, +0.1063] | ✅ |
| **D** 場級 + 落後 + 400m 收放 | 0.5886 | +0.0555 | [+0.0449, +0.0665] | ✅ |
| **E** 場級 + 按馬匹數縮放落後 | 0.5886 | +0.0560 | [+0.0476, +0.0651] | ✅ |

候選 A 完美重現現行版，證明拆解無誤。

### ⚠️ 正交性代價（場內相關）

| 候選 | pure_7d | form | performance_quality | rating | 現行 PF |
|---|---:|---:|---:|---:|---:|
| A（現行） | 0.434 | −0.011 | **0.103** | 0.126 | 1.000 |
| B | 0.593 | 0.185 | **0.418** | 0.192 | 0.806 |
| C | 0.512 | 0.384 | **0.651** | 0.188 | 0.100 |

**C 單獨最強，但同 `performance_quality` ρ=0.651 —— 佢係喺重新推導 form。**
B 保住 0.806 同現行版嘅同一性（即係「個體化版嘅 pace_figure」），
但 `performance_quality` 相關由 0.103 升到 0.418。

### 接返 EXP-20260831-02 嘅失效 cohort

| 候選 | 懷疑組 AUC (n=222) | 其餘 (n=664) | 落差 |
|---|---:|---:|---:|
| A（現行） | **0.5126** | 0.5375 | −0.025 |
| B | 0.5705 | 0.5950 | −0.025 |
| C | 0.6137 | 0.6188 | **−0.005** |

**現行 pace_figure 喺合成層失效嗰 24–25% 場次係 0.5126 —— 等同擲毫，
而佢帶住 11.49% 權重。** C 幾乎冇 cohort 落差。

## 檢查
- **leakage-audit**：PASS —— 全部欄位嚟自**過往**賽事 form line；抽取層
  已經丟走賽日當日或之後嘅往績（`write_meeting` 嘅 `dropped` 計數）。
  今場結果只做標籤。
- **golden_scoring / data_contract**：冇郁（零 code 改動）
- **退步**：未量 —— **未行過排名 A/B**

## 結論

**診斷成立，候選未驗。唔可以就咁上。**

三件事係實錘：
1. `pace_figure` 食緊**一個場級欄位**，其餘十個支援欄位係 Racenet 死 code。
2. 佢喺模型最失效嗰批場次 AUC 0.5126（擲毫），而佔 11.49% 權重。
3. 個體化用嘅數據**一直喺同一條 form line 上面**，覆蓋 97.4%。

但係 `pace_figure` 過往七個修法全部 REJECT，原因係佢嘅價值喺**正交性**
（ρ 對 form −0.011、對 performance_quality 0.103），唔係單獨 AUC ——
同 `sectional_score` 單獨 AUC 0.469 但剷走 holdout −0.0151 一樣。
本實驗量到嘅 AUC 增益**必然**伴隨正交性下降（B: 0.103 → 0.418），
呢個 trade-off **只可以由排名層 A/B 判**，solo AUC 唔係把尺。

**下一步（按次序）**：
1. 先接通 B 做候選 leaf，行 `model-regression-gate`（dev + 時間 fold，
   holdout 最後確認）。B 而唔係 C —— C 同 performance_quality ρ=0.651，
   極可能係複製品。
2. 如果 B 過閘，再做 ablation 拆開「場級 L600」同「本駒落後」邊樣出力
   （D/E 已經係兩個變體，可以一齊入 ablation）。
3. 無論結果點，`_pf_aggregates` 嗰十個 0% 欄位應該清走或者明確標記
   —— 而家佢令人以為呢個特徵好豐富。
4. `finish:` / `WinningTime` 只有 08-26 之後先有，任何用佢哋嘅候選
   語料窗只有約 25 個場次，**唔夠**。用 `margin` 就冇呢個問題。
