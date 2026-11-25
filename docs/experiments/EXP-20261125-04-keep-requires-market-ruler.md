# EXP-20261125-04 AU／HKJC 模型 KEEP 改為要過市場尺（市場尺 m2）

- 日期：2026-11-25　平台：AU／HKJC　類型：**判決規則改動**（獨立改動，冇夾候選；合約「市場尺 m2」）
- 決定：Kelvin 2026-11-25「ok 用市場尺做 KEEP 條件」。Claude 事先講明代價：大部分純排名改善會 REJECT、dashboard 排名難再進步。

## 新規則
KEEP 要：(1) 市場尺 B PASS（AU：SP PASS＋BSP 獨贏 ΔΔ 點估計 ≥ 0；HKJC：`--window dev` PASS、holdout 確認）；
(2) 排名尺 Δlog-loss 95% CI 下界 ≤ 0（唔准顯著差咗）而且護欄過；(3) leakage、功效預估、ablation 照舊。
例外：正確性修正、數據管線、純顯示；Kelvin 明確「分析用途上線」（寫入記錄、唔准支持落注）。

## 工具改動
- `market_ruler.py` VERSION `m2`；HKJC `--window dev|holdout|terminal`：walk-forward 照用所有之前賽日訓練，只計窗內場次。
- 測試：`ScoreWindowTest`（只計窗內、訓練用之前日子）。

## 基準（現行 live，用新規則嘅窗）
- HKJC dev（2020-09 → 2024-07，3,220 場／352 日）：獨贏 Δll −0.00018 [−0.00044, +0.00007] → 冇市場以外資訊。
- AU（SP／BSP）同 EXP-20261124-90／-92。

## 影響
- 唔追溯：11-25 之前判咗嘅 KEEP 照舊；跑緊嘅 forward 照用登記時嘅尺。
- 之後新候選要搵「市場唔知嘅資訊」先 KEEP 到；開實驗前先跑 `power_precheck.py`。
