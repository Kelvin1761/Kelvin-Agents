# EXP-20261016-02 結果：Sportsbet 全程速度（情境標準）

- **預先登記**：[protocol](EXP-20261016-02-au-sportsbet-total-speed-protocol.md)（commit `d8156d13`，量度之前）
- **baseline**：production F6a（commit `73343245` 之後；試閘分退出排名）。dump 同 EXP-20261016-01
  嘅 F6a arm 逐匹一致。
- **來源 availability 仍係 FLAG**：正式判決全部 `REJECT / leakage_audit_failed`；下面係研究診斷。

**決定：NEEDS MORE TESTING。** S2 嘅 refit arm 判 `RANKING_WIN`，但 Holm 後 p = 0.078，
未達 0.05；S1 `primary_regression`。冇嘢上線。

## 實作細節（登記冇寫明、量度之前定）

- 事件總時間（`ContextStandard` 嘅 `total`）用**頭馬時間**：Sportsbet 冇全場逐駒時間，
  外部版本用全場中位數。場內 z 會抵銷常數差。
- `ContextStandard` 用稀疏矩陣算（同一條正規方程、penalty、IRLS）：同原版 4,000 場事件
  逐個預測最大差 **4.0×10⁻¹³**。
- S1 疊加值捨入到 4 位小數（refit 工具嘅 numpy 加速喺 8 位小數半數位捨入唔同，verify 拒絕）；
  每匹最多差 5×10⁻⁵。

## G0 數據

- 389,176 條往績行；剔走試閘／非標準 114,496；有頭馬時間兼負距 162,261；
  頁面有 `WinningTime` 162,265（差嘅 4 行有時間冇負距，parser 0 遺漏）。
- 25,560 場事件；48 場頭馬時間衝突**成場隔離**；3 個 Formguide 檔名唔合格式，跳過。
- 乾淨窗目標馬匹覆蓋 **86.1%**（20,615 / 23,949），2,273 場可比較。
  外部官方計時版本覆蓋只有 12–16%（Codex EXP-20261015-12）。

## G1 估算時間 vs 官方逐駒時間 —— **一模一樣**

11,090 條重疊往績：Pearson r **1.0000**，差距中位 0.000 秒、IQR [−0.003, +0.002]、
第 90 百分位 0.007 秒。

即係**官方逐駒完成時間本身就係由頭馬時間 + 負距推出嚟**，唔係獨立量度。
live 全程速度疊加項同 Sportsbet 版本係同一份資訊，分別只係覆蓋率。
（Codex EXP-20261015-08 已經指出 HKJC 嘅換算會化簡成 `margin × 0.17`；今次喺 AU 實測證實。）

## G2 純訊號同正交 —— **過**

| | 數值 |
|---|---|
| A_sb 場內配對 AUC | **0.6193** [0.6119, 0.6277] |
| 同一批馬 pace_figure AUC | 0.6010 |
| A_sb − pace_figure | **+0.0183** [+0.0080, +0.0292] |
| ρ(A_sb, pace_figure) | **0.300**（停止線 0.60） |
| ρ(A_sb, form) | 0.368 |
| ρ(A_sb, performance_quality) | 0.450 |

舊簡單標準版本 AUC 0.5872、ρ(own-L600) 0.418（EXP-20260831-07）；情境標準令佢更準又更正交。

## G3 §8 四 arm（1,482 場／41 日 OOS）

| | Gold | Good | Pass |
|---|---:|---:|---:|
| A0 現行 | 19.91% | 26.79% | 50.34% |
| S1 A1 | 20.18% | 26.45% | 50.67% |
| S1 B1 | 20.38% | 26.72% | 50.20% |
| S2 A1 | 19.97% | 26.52% | 50.74% |
| **S2 B1** | **20.58%** | **27.33%** | 50.40% |
| B0（現行 leaf refit） | 20.11% | 26.52% | 50.27% |

### S1 疊加項 —— REJECT（primary_regression）

- fixed：Good −0.34pp [−0.91, +0.23]；NDCG **+0.0027 [+0.0007, +0.0048]**、
  Top5 AUC **+0.0018 [+0.0001, +0.0036]**
- refit：Good +0.20pp、Gold +0.27pp，NDCG **+0.0031 [+0.0001, +0.0059]**；但 Gold 時間塊唔夠 4/6 不負
- 排序指標升，但 primary 點估計有負 → 依規則 REJECT

### S2 入 `pace_perf` —— refit arm RANKING_WIN，Holm 後未過

- fixed：Gold +0.07pp、Good −0.27pp → primary_regression；NDCG **+0.0048 [+0.0008, +0.0087]**
- **refit（B1 vs B0）**：Gold +0.47pp [−0.64, +1.59]、Good +0.81pp [−0.33, +1.92]、
  Top3@5 **+0.0050 [+0.0002, +0.0098]**、Top5 AUC **+0.0031 [+0.0001, +0.0061]** → `RANKING_WIN`
- Holm（fixed／refit 兩個 arm）：refit p **0.078** → `arm_multiplicity_not_significant`
- live guard（B1 vs A0）：`ranking_evidence_too_weak`（冇傷害）
- 現行權重未過時（B0 vs A0 仍然唔贏）

**refit 想要乜權重**（S2 每窗共識）：`pace_perf` 由 0.114 → **0.19–0.22**（6 窗 5 個），
`stability` 0.371 → 0.27–0.31、`class_weight` 0.383 → 0.28–0.32。過閘 draws 10–22 個
（現行 leaf 只有 2–5 個）。呢個就係 §8 要捉嘅情況：修好速度 leaf 之後，舊權重低估咗佢，
其他維度攞住佢之前嘅份額。

## 下一步（建議，未做）

S2（固定設計 + 用上線日之前全部乾淨數據 fit 嘅共識權重）做 **forward shadow**：
由 2026-10-17 起嘅新賽日、凍結配置、一個 family 只開一次（v3 forward holdout）。
唔准喺呢 41 日再調等分比例、gain 或者 z 尺度。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
python3 scratch/au_paceperf_dump_20261016.py --variant f6a --out $S/prod_f6a.json
python3 scratch/au_sb_total_speed_20261016.py --dump $S/prod_f6a.json --out $S/asb.json --check-sparse
python3 scratch/au_sb_total_speed_gates_20261016.py --dump $S/prod_f6a.json --asb $S/asb.json --out $S/gates.json
for a in S1 S2; do
  python3 scratch/au_sb_total_speed_arms_20261016.py --dump $S/prod_f6a.json --asb $S/asb.json --arm $a --out $S/arm_$a.json
  python3 scratch/au_paceperf_refit_20261016.py --variant f6a predict --data $S/arm_$a.json --out $S/wf_$a.json
  python3 scratch/au_paceperf_s8_20261016.py --base $S/wf_f6a.json --cand $S/wf_$a.json --label $a --out $S/s8_$a.json
done
```
refit procedure hash `f92c8377…e033`（baseline、S1、S2 一樣）。
