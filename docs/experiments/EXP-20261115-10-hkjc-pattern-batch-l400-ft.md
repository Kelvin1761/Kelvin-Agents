# EXP-20261115-10 — HKJC 候選批次（Kelvin 2026-11-15 批准）：12 個 pattern、L400 近 6 仗、FT 負磅 —— 全部 dev REJECT

- 日期：2026-11-15｜判法：v4 回放尺｜baseline = 現行 live（S 版＋FT＋L400 實測＋**上仗賠率**）
- 起因：EXP-20261115-09 診斷；Kelvin「happy with these … dig even deeper」。

## A. 12 個 pattern（`docs/experiments/patches/hkjc_patterns/{features,screen,build}.py`；只用日期早過今仗嘅 HKJC 馬匹頁＋賽果）
篩選（dev 殘差，對 live raw）：Kelvin 點名 8 個＋深挖 4 個（首次跑泥地 −3.5pp、上仗 2／3 名近頭馬 +2.2pp、14 日內再出 +1.7pp、加程 ≥200m −1.3pp）；
冇過篩：評分跌、休息 ≥90 日、復出第三仗、全場最高評分、體重大變、首次場地、首次騎練組合、連續兩仗入位、減程、新馬首戰。

| 候選（walk-forward，dev 2,488 場） | Δlog-loss | Gold | Good | 判決 |
|---|---|---|---|---|
| **主檢定：12 個合併** | −0.00089 [−0.00153,−0.00017] | −0.16 | −0.28（下界 −1.25） | REJECT（護欄） |
| 逐個（12 個） | 全部 CI 跨零（最好：14 日內再出 −0.00021、除去配備 −0.00017、加程 −0.00015） | ±0.4 內 | ±0.4 內 | 全部 REJECT |
全 dev β（raw 分）：自購馬首戰 −3.7、首次泥地 −3.0、上仗熱門休息 ≥90 日 −1.8（逐季 +3.2→−1.9，唔穩）、轉馬房 +1.7、降班＋換騎 +1.7、
上仗冷門入位 +1.1、14 日內再出 +1.1、加程 −1.3、上仗熱門轉場地 −0.9、除去配備 +0.8、近頭馬 +0.7、首次配備 −0.3。
**冇開 holdout。** 解讀：單變量殘差大（−7.7pp）但影響馬匹少、部分已被模型捉到、β 唔穩；合併只改善機率準度，揀馬冇改善。

## B. 末段 L400 近 6 仗＋逐仗負磅；FT 全程逐仗負磅（`docs/experiments/patches/hkjc_arm_l400_ft_weight.py`，引擎 arm，v3 回放）
- l400_6：入分 L400 = 近 6 仗每仗 L400 按 `l400_weight_seconds_per_lb(嗰仗路程)` 換算到今仗負磅，1/k 加權 → dev Δlog-loss **+0.00016** [−0.00003,+0.00036]、Gold −0.12 → REJECT
  （平均唔同路程嘅末段沖淡咗上仗最新資訊；路程標準化版本已經喺 forward `l400_standardised`）。
- ft_w：FT 全程每仗 + (今仗 − 嗰仗負磅) × 0.0112 s/km × 0.4 → dev +0.00001、Good −0.16 → REJECT（FT 已經對標準＋扣當日快慢，負磅差影響細）。
- baseline v3：現行 main（含上仗賠率）全部 6,047 場重新回放 → `hkjc-history/analysis/replay_all/v3/base.jsonl`。

## C. 方法問題（重要）
dump 上候選嘅 β 原本用「raw × 10＋lbfgs」fit —— **部分訓練集冇收斂**（跑法偏差喺上仗賠率之上：2021–2023 季 β ≈ 0，正確係 1.1／0.2／3.1）。
已改做標準化＋newton-cg（`hkjc_patterns/build.py`）；12 個 pattern 用新方法重跑結果一樣。之前用舊方法嘅判決（EXP-03／04／05／07／08）
β 都穩定、非零，但下次一律用標準化 fit。
