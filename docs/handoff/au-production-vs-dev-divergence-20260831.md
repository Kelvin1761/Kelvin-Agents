# `au-production` 同開發線分叉了 —— 排名表現一樣，但顯示同工具唔同

**日期**：2026-08-31
**結論**：**唔影響分析表現**（已量，四位小數之內一樣），但兩邊各自缺對方嘅嘢。

## 量度

同一份語料（1,782 場 / 17,838 匹），兩邊各用**自己嘅 code** dump + eval：

| | `au-production` | `claude/au-pace-figure-rebuild` |
|---|---:|---:|
| 頭 5 位 AUC (all) | **0.6828** | **0.6828** |
| dev / holdout | 0.6800 / 0.6905 | 0.6799 / 0.6906 |
| 全場 AUC | 0.6686 | 0.6686 |
| gold | 18.65% | 18.65% |
| gold_strict | 6.80% | 6.80% |
| good_positional | 23.09% | 23.09% |
| pass | 45.39% | 45.39% |
| champion | 24.27% | 24.27% |
| winner_in_top3 | 56.29% | 56.29% |
| t3prec | 47.02% | 47.02% |

**排名表現完全一樣。** 唔係巧合 —— `EXP-20260826-03` 嗰個 gain 修正**特意**
設計成排名不變（權重同步補償、`MATRIX_ABILITY_SCALE` 還原 ability 軸，
1,611 場實測 ability max|Δ| 0.0016、grade 改變 0）。

## 具體差異

### `au-production` 缺（開發線有）

| | 影響 |
|---|---|
| `MATRIX_DISPLAY_GAINS["pace_perf"]` 0.9909 → **0.594** ＋ 權重補償 ＋ `MATRIX_ABILITY_SCALE` | **顯示** —— pace_perf 成品 SD 18.26 vs 其餘維度 10.16–12.81，即係大聲 **1.68 倍**，兩端 band 都爆（❌❌ 佔 14.3%，stability/track 只 0.4%）。就係「一隻唔對板嘅馬又衝上頭位」嗰個觀感。**排名不變。** |
| 配備變更抽取＋顯示 | 報告內容（刻意唔入排名）|
| 賽前市場盤預填落注格 | 落注格顯示 |
| 場次名稱被截斷修正（貪婪 `[^>]*` 食咗 title 屬性）| 顯示 |
| `au_feature_ab --min-depth` 會靜靜清空語料 | **研究工具** —— 用錯會量到假結果 |
| `MATRIX_ABILITY_SCALE` 喺 validation 度漏咗嘅修正 | 驗證層 |

### 開發線缺（`au-production` 有）

| | 影響 |
|---|---|
| **Stage 4 v2 評估閘**（`8664ea9b`）| `au_eval` 標題由「判決 = 頭 5 位配對 AUC holdout 區間」變「Stage 4 v2 = Gold/Good primary + ranking evidence」—— **判決規則唔同** |
| Stage 4/5 central governance plane、research registry、評估把尺凍結 | 平台 |
| 排程韌性（timeout 斬死自己、slot 衝突、Telegram、TCC、dashboard 收斂）| 營運 —— 部分同開發線用唔同 hash cherry-pick 咗兩邊 |

⚠️ **最要留意嗰樣**：兩邊嘅 `au_eval` **判決規則唔同**。今日所有實驗都係用開發線
嗰把尺（頭 5 位配對 AUC + 功效前置條件）判嘅。如果將來用 `au-production` 嗰邊
嘅 Stage 4 v2 重判，結論可能唔同 —— 唔可以混住比。

## 已廢棄嘅對齊嘗試

`codex-au-production-reconcile` 停喺 2026-08-13，落後 `au-production` 98 個
commit、領先 0。**唔係進行中嘅工作。**

## 狀態

兩條分支 2026-08-31 都已 push：
- `origin/claude/au-pace-figure-rebuild`（新分支，PR 未開）
- `origin/au-production`（`1ddf33e0..774c1355`，93 個 commit）

## 已對齊（2026-08-31 同日）

三個對生產有實質影響嘅已經 cherry-pick 落 `au-production` 並 push：

| commit | 內容 | 驗證 |
|---|---|---|
| `8701b6d8` | **pace_perf 顯示尺** gain 0.9909 → 0.594 ＋ 權重補償 ＋ `MATRIX_ABILITY_SCALE` | 1,782 場 / 17,838 匹：`ability` max\|Δ\| **0.0017**、grade 改 **4/17,838 = 0.02%**；pace_perf 顯示 SD **18.26 → 9.31**、❌❌ 佔比 **14.3% → 3.3%**；七個維度全部落喺 7.94–12.94（目標 11）|
| `61753932` | 場次名稱被截斷（貪婪 `[^>]*` 食咗 title 屬性）| 測試已帶埋 |
| `1cff8a19` | `au_feature_ab --min-depth` 會靜靜清空語料（研究工具）| 測試全綠 |

排名表現前後一致：頭 5 位 AUC **all 0.6828 · dev 0.6799 · holdout 0.6905**，
gold 18.65% / pass 45.39% / t3prec 47.02% —— **同修之前四位小數之內一樣**，
正如設計意圖。

衝突解決方式：
- `au_eval.py` —— **union**，保住生產嘅 Stage 4 v2（`model_evaluation_decision`）
  再加 `MATRIX_ABILITY_SCALE` import
- `docs/experiments/INDEX.md`、`au_unused_field_power.py` —— union / 取新增側
- 模型說明、`scoring_golden.json` —— 重新生成

### 仲未對齊

**開發線缺嘅嘢一樣都未帶過去**（Stage 4 v2 評估閘、Stage 4/5 platform、
research registry）。⚠️ 所以 **兩邊 `au_eval` 判決規則仍然唔同**：
生產係「Stage 4 v2 = Gold/Good primary + ranking evidence」，
開發線係「頭 5 位配對 AUC holdout 區間」。今日十個實驗全部用開發線嗰把尺判。

其餘未帶：配備變更抽取＋顯示、賽前市場盤預填落注格（綁住 dashboard
`static_template` 8,714 行改動，要拆）。

## 建議

1. **唔急**（排名表現一樣），但**應該做** —— 主要為咗把 pace_perf 顯示尺修正
   帶落生產，同埋令研究工具（`au_feature_ab`）兩邊一致。
2. **合併之前一定要先決定用邊把尺** —— 兩邊 `au_eval` 判決規則唔同，
   而 `AGENTS.md` 明文寫住「改動判決規則 = 改動把尺，要當獨立改動先論證」。
3. 合併之後要重跑：`golden --record`、`data_contract --calibrate`、
   `更新模型說明.sh`，然後用**同一把尺**重驗今日十個實驗嘅結論。
