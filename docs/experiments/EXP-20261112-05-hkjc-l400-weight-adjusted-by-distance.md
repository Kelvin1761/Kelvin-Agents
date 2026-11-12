# EXP-20261112-05 HKJC 段速按今仗負磅調整上仗 L400（C 跟路程）

- **日期**：2026-11-12
- **平台**：HKJC
- **觸發**：Kelvin：「試按路程版」
- **假設**：EXP-20261112-04 嘅調整改用實測、按路程嘅係數，排名會改善
- **搜索過嘅舊記錄**：EXP-20261112-04（固定 C=0.02 判唔到、0.04 微負）
- **改到嘅檔案／組件**：冇 live 改動；arm monkeypatch `SpeedScorer._data`

## 配置（跑之前寫喺 arm docstring）
- **baseline**：origin/main `4e6dae6a`
- **arm**：調整後 L400 = 上仗 L400 + C(上仗路程) ×（今仗實際負磅 − 上仗實際負磅）；
  C = 0.007（≤1200m）／0.016（1201–1799m）／0.021（≥1800m）秒／磅，EXP-04 三個點估計原封照用
- 只跑一個 arm；`fixed_rule`
- **注意**：三個 C 由 L400 對負磅估出嚟（唔係由上名結果），但用嘅往績同評估語料重疊，唔算完全樣本外

## 結果（389 場／39 個賽日）
段速分升 179 匹、跌 204 匹；排名有變 73 場。

| 指標 | Δ | 95% CI | 6 塊 |
|---|---|---|---|
| Gold | 0.00pp | [0, 0] | 全 0 |
| Good 位置 | **+0.51pp** | [0.00, +1.30] | 0, 0, +1.41, 0, 0, +2.56 |
| top3 capture@5 | −0.17pp | [−0.60, +0.25] | |
| NDCG@5 | +0.000 | [−0.003, +0.004] | |
| competitive recall@5 | −0.05pp | [−0.30, +0.19] | |
| 頭三平均模型名次 | −0.006（好咗） | [−0.019, +0.007] | |

模型頭三換入 14 匹上名 6；換出 14 匹上名 4。
分層（Good）：沙田草地 +0.44、跑馬地 +0.70、沙田泥地 0、直路 1000 0、今季 +0.54；Gold 全部 0；首選勝出 −0.26pp（1 場）。

**判決：REJECT / ranking_evidence_too_weak** —— 兩個 primary 都冇跌（Good 多 2 場），但排名證據全部跨零。

## 同固定 C 比較
| arm | 郁咗場次 | Gold | Good |
|---|---|---|---|
| C=0.02（EXP-04） | 102 | 0.00 | +0.26 |
| C=0.04（EXP-04） | 162 | −0.26 | −0.26 |
| **按路程（本實驗）** | 73 | 0.00 | +0.51 |

越貼近實測幅度，結果越乾淨；但三個之間嘅差距係 1–3 場，分唔開。

## 檢查
- **leakage-audit**：PASS（同 EXP-04）；**wiring**：383 匹段速分有郁
- **golden_scoring**：冇郁；**退步**：live 冇改

## 結論
物理上啱嘅調整，冇任何 primary 或者分層為負，但改善幅度（Good 多 2 場）細過閘門睇得到嘅範圍。
按規則係 REJECT（證據太弱），唔係「有害」。形狀同 §7 正確性修正一樣（方向有物理根據、冇分層負、未證實改善）——
上唔上線係 Kelvin 決定。上線要改管線（Logic 帶上仗負磅同路程）、加 forward 登記、重錄 golden、重新 calibrate。

**決定**：REJECT（按 `fixed_rule`）→ Kelvin 2026-11-12 決定行 §7 上線（EXP-20261112-13）
**commit**：未 commit 任何 model code

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --out base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 $H run --dump-matrix --arm $P/hkjc_arm_l400_weight_adjusted_by_distance.py --out dist.jsonl
python3 $H compare base.jsonl dist.jsonl --stage4 fixed_rule --leakage-audit-passed
```
