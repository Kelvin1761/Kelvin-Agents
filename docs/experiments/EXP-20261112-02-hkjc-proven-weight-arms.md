# EXP-20261112-02 HKJC 重磅要喺呢個磅數證明過：兩個 arm A/B

- **日期**：2026-11-12
- **平台**：HKJC
- **假設**：EXP-20261112-01 量到嘅 cohort 差距（重磅 ≥130 未證明 − 證明過 −7.83pp）放入官方評分分，排名會改善
- **搜索過嘅舊記錄**：EXP-20261112-01（screening）；`au-cohort-gap-is-not-a-gain`（同類失敗）
- **改到嘅檔案／組件**：冇 live 改動。arm 只喺 harness 入面 monkeypatch `RacingEngine._weight_score`

## 配置（跑之前寫死，冇擬合）
- **baseline**：origin/main `4e6dae6a`
- 重磅 = 今仗實際負磅 ≥130；證明過 = 賽日前最近 6 仗有一仗頭三而嗰仗負磅 ≥ 今仗 − 2 磅；冇往績唔郁
- **arm A `proven_weight_gate`（只扣一邊）**：官方評分分本來 70 嘅馬，重磅而未證明 → 64
- **arm B `proven_weight_two_sided`（主 arm）**：重磅馬一律 —— 證明過 70、未證明 64
- 判決：`hkjc_eval_harness compare --stage4 fixed_rule`

## 數據
- PIT 回放 449 場，配對後 389 場／39 個賽日（60 場因死欄位／冇配對剔走，兩邊一樣）
- wiring：A 有 390 匹官方評分分跌、0 匹升；B 有 390 跌、292 升 —— arm 有接通

## 結果
| 指標 | arm A | arm B |
|---|---|---|
| 排名有變場次 | 74 | 127 |
| Gold | 0.00pp | −0.26pp [−0.79, 0] |
| Good 位置 | −0.26pp [−0.78, 0] | −0.77pp [−1.80, +0.26] |
| top3 capture@5 | 0.00 | −0.26pp [−0.69, +0.17] |
| NDCG@5 | +0.0005 [−0.0013, +0.0022] | **−0.0034 [−0.0066, −0.0003]** |
| 頭三平均模型名次 | +0.000 | +0.007（差咗，跨零） |
| 模型頭三換入／換出 | 入 8 匹上名 3；出 8 匹上名 1 | 入 18 匹上名 8；出 18 匹上名 6 |
| **判決** | **REJECT / primary_regression** | **REJECT / primary_regression** |

## 檢查
- **leakage-audit**：PASS（同 EXP-20261112-01）
- **golden_scoring**：冇郁；**退步**：live 冇改

## 結論
- A：74 場排名郁咗但所有指標等於零（Good 少 1 場）。頭三入面換入嗰 8 匹的確好過換出嗰 8 匹（3 vs 1 上名），
  但數量太細，改唔到場次級指標。**冇改善，亦冇證據話有害。**
- B：加埋「證明過 +」嗰邊反而差，NDCG CI 全負。即係 screening 入面「證明過被低估 +4.5pp」**放入分數後唔成立** ——
  同一批馬喺近績／穩定性已經攞咗分，再加係雙計。
- screening 差距係真（時間切半、12 格門檻同向），但同之前多次一樣：cohort 差距 ≠ 排名改善。
  官方評分分呢個位太細（6 分 × 細權重），而效應集中喺每場最多一兩匹馬。

**決定**：REJECT（兩個 arm）
**commit**：未 commit 任何 model code（arm 檔只係實驗腳本）

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_proven_weight_gate.py --out armA.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_proven_weight_two_sided.py --out armB.jsonl
python3 $H compare base.jsonl armA.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare base.jsonl armB.jsonl --stage4 fixed_rule --leakage-audit-passed
```
