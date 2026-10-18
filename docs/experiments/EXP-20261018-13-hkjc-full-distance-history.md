# EXP-20261018-13 — 同程往績用完整歷史：REJECT（§7 唔過）；同時更正 EXP-12

- **日期**：2026-10-18；平台：HKJC；**§7 候選 → REJECT，冇上線**
- **code**：branch `claude-hkjc-horse-distance-20261018` @ `be3c9e59`（保留做記錄，唔准 merge）
- **改動（未上線）**：`build_comprehensive_stats.horse_distance_table` → `horse_distance_stats.csv`；`live_priors.HorseDistanceRecords`
  （latest snapshot ＋ `temporal_source_is_safe`）；`_same_distance_record` 取賽果庫同 Facts 入面出賽次數多嗰個；
  `pit_backtest.inject_as_of` 注入 `Date < 賽日` 版本。

## 更正 EXP-20261018-12

逐賽日對賽果庫（PIT）：Facts「同程」截斷集中喺 **2026-10-04 或之前**（每日 54–96 匹少數、6–25 匹有上名被當冇），
**10-07 起幾乎 0**（10-07／10-11／10-14／10-19：少數 1／0／1／1，上名差 0）。原因：`c89a2f09`（2026-10-07）已經修咗 Facts 生成器
用完整往績。所以：
- **live 由 10-07 起本身已經係完整往績**，EXP-12 講「live 有 7.9% 漏 +4」係錯 —— 嗰個數係量 9 月至 10-04 嘅存檔。
- 問題其實喺**回放語料**：10-07 之前嘅存檔 Logic 仲係截斷版，所以回放量緊嘅同 live 唔一樣。

## 回放（harness 全語料，main `fa8a0e81` vs 修正）

- 365 場入面 133 場排名有郁，**全部喺 10-07 之前**（10-07 之後 0 場 —— 同上面一致）。
- Stage 4 v3 `fixed_rule`（345 場）：Gold +0.58pp [0.00, +1.47]、**Good −1.45pp [−2.66, −0.29]（CI 全負）**，時間塊
  −3.4／0／−1.6／−1.7／−1.9／0；NDCG −0.0004、competitive_recall −0.10pp；判決 `primary_regression`。
- 分層：**兩格 CI 全負** —— 11–12 匹 Good −2.41 [−5.33, −0.56]、首選 SP 4.1–7 Good −3.48 [−6.78, −0.81]。
- §7 條件 2（零顯著退步）**唔過** → 唔上線。

## 點解完整往績反而差（推斷，未驗證）

截斷版其實係「近期（賽績頁列出嗰十幾仗）喺呢個路程有冇上名」；完整版係「生涯有冇喺呢個路程上過名」。
舊上名（例如兩季前）同今仗關係弱，但一樣攞 +4，令一批狀態已過嘅馬升位。

## 對 live 嘅含意（重要）

live 由 10-07 起用緊完整版。按呢個回放，完整版比截斷版 Good 低約 1.45pp。即係 `c89a2f09` 可能令 live 變差，
但嗰個改動當時冇做同程部分嘅回放（佢係「修 evidence coverage 同 distance readout」）。
**下一步建議（未做）**：預先登記「同程上名只計近 N 仗／近 N 個月」，喺現行 live（完整版）為 baseline 做 A/B。
