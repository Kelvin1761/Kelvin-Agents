# EXP-20261110-02 HKJC SpeedPro 能量差 —— 篩選結果＋forward 預先登記

- **日期**：2026-11-10
- **平台**：HKJC
- **狀態**：篩選 PASS_SCREEN（探索性）；forward 收集中，**未入分、未證實**
- **上游**：2026-10-14 發現 SpeedPro `sg_race_N` 從未使用、冇歷史檔，即日開始收集
  （`hkjc_race_extractor/scripts/collect_speedpro.py`，排程 best-effort）。
- **追蹤**：`hkjc_forward_tracker.FORWARD_TESTS["speedpro_energy_diff"]`（kind `speedpro_races`，150 場）

## 假設

馬會 SpeedPro 嘅 `speedproenergydifference`（預計能量 − 今場所需能量）喺控制咗我哋模型排名之後，
仲有上名資訊。點解值得睇：2026-11-10 全面掃描（440 場 PIT 回放）顯示現有九個維度嘅資訊已經用盡 ——
外層 refit 三次、內部份額、GBM、clean-room logit 全部過唔到閘 —— 要再升只可以靠新資訊。

## 洩漏審查

- SpeedPro 喺賽前一日公布（`lastupdatetime` 早過賽日），係馬會自己嘅能量評估，唔係賠率。
- 只用賽日 03:00 UTC（香港 11:00）之前抓嘅快照；資料夾名就係抓取時間，永不覆蓋。
  沙田日賽最早約 04:30 UTC 開跑，跑馬地夜賽約 10:40 UTC。
- 未查清：馬會點計 `speedproenergy`（有冇用到試閘／晨操以外嘅嘢）。佢係公開賽前資料，所以唔係洩漏，
  但如果將來入分，要當「外部評分」處理，同官方評分一樣。

## 篩選（2026-11-10，探索性，唔係 A/B）

- 語料：2026-10-14 → 11-08，8 個賽日、79 場、963 匹（全部有賽前快照）。
- 模型分：`hkjc_eval_harness.py run --dump-matrix`，main `5b45a24e`，PIT priors。
- 命令：
  `python3 docs/experiments/patches/hkjc_screen_speedpro.py <base.jsonl> --since 2026-10-14 --until 2026-11-08`
- 統計量：每場按欄位攞頭三，按模型排名每兩名一段分層，計「頭三 vs 其餘」上名率差（MH 權重）；賽日 bootstrap 2000 次。

| 欄位 | 場內 AUC [95% CI] | 覆蓋 | 分層上名率差 [95% CI] |
|---|---|---:|---|
| 模型原始分（對照） | 0.6667 [0.6349, 0.6936] | — | — |
| **`diff`（能量差）** | 0.6690 [0.6480, 0.6917] | 100% | **+15.3pp [+8.0, +23.9]** |
| `energy`（預計能量） | 0.6258 [0.5984, 0.6562] | 100% | +5.8pp [−0.2, +12.1] |
| `fit`（狀態評分） | 0.6348 [0.5992, 0.6667] | 100% | +1.5pp [−6.9, +11.7] |
| `lastrun` | 0.6249 [0.6001, 0.6474] | 94.2% | +5.9pp [−2.5, +13.3] |
| `bestlast12months` | 0.5476 [0.5078, 0.5886] | 94.1% | −2.6pp [−9.4, +4.9] |
| `bestatdistance` | 0.5630 [0.5242, 0.6030] | 69.6% | +2.3pp [−3.3, +9.2] |

補充（同一批場次）：

- `diff` 對模型原始分嘅場內 Spearman 約 +0.60。
- 模型排 7 名或以後：能量差頭三上名 32.5%（n=40）vs 其餘 14.4%（n=450）。
- 場內 z-score 簡單混合（模型 + w×diff，in-sample）：AUC 0.6667 → 0.6839（w=0.25）／0.6880（w=0.5），
  但 **Good 16 → 17／15、Gold 9 → 6／8** —— 冇改善。79 場一場 = 1.3pp，判唔到。

### 點解唔可以當係已證實

- 8 個賽日、in-sample；六個欄位入面揀咗最好嗰個（Bonferroni ×6 之後 `diff` 仍然過，但窗口好短）。
- 呢個 repo 已經多次見過「cohort 差距大、落唔到排名」（頂級騎師 +5.5pp、同程最佳時間、前置習慣）。
- 今季 9–11 月本身係模型偏弱嘅時段（AUC 0.669 vs 上季 0.718），外部評分睇落特別有用可能係時段效應。

## Forward 預先登記（睇任何 forward 數據之前寫）

- **窗口**：2026-11-11 起嘅賽日。上面 79 場用嚟揀欄位，**唔入判定**。
- **樣本**：有賽果而且有賽前快照嘅場次，第一次 ≥ 150 場就判，只判一次。
  （每星期約 20 場，預計 2027 年 1 月頭。）
- **判定欄位**：只有 `diff`。其他欄位照印但唔可以事後換。
- **命令**（原封重跑，唔准改腳本入面嘅凍結規則）：
  ```bash
  H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
  PYTHONDONTWRITEBYTECODE=1 python3 $H run --since 2026-11-11 --out <scratch>/base.jsonl
  python3 docs/experiments/patches/hkjc_screen_speedpro.py <scratch>/base.jsonl --since 2026-11-11
  ```
- **判決**：
  - `diff` 分層上名率差 95% CI 下界 > 0 → **PASS_SCREEN**：可以預先登記一個排名 arm（`fixed_rule`，
    幅度喺睇 forward Gold／Good 之前寫死），再行 `model-regression-gate`。PASS_SCREEN **唔等於**可以上線。
  - 否則 → **REJECT**，記錄，SpeedPro 留喺報告層或者唔用。
- **唔准做**：夠數之前偷睇再調欄位／分層／窗口；用篩選嗰 79 場去證明 arm。
- **永遠唔會自動改模型**；上唔上線由 Kelvin 決定。

## 已知限制

- 收集器係 best-effort，冇歷史檔可以補。追蹤表會數「有賽果但冇賽前快照」嘅場次；
  20 場以上而一份快照都冇就報 stalled。
- 150 場對 Gold／Good 嘅功效唔夠（Good 1 SE ≈ 3.4pp），所以 forward 第一步判嘅係分層上名率差，唔係 Gold／Good。
