# EXP-20261105-02 — 負磅分由「馬匹健康」搬入「級數優勢」（rank-neutral）

Status: **STRUCTURAL KEEP（語義搬位，唔聲稱改善）**

## 問題

Kelvin 2026-11-05 覆核報告：「級數優勢嘅班次分同負磅分好似同馬匹健康／新鮮感撞？」

搬之前 `weight_score`（讓磅官宣佈負磅）喺兩個維度各佔一份：

| 維度 | 權重 | 負磅份額 | 負磅實際權重 |
|---|---:|---:|---:|
| 級數優勢 | 0.1428 | 25% | 0.0357 |
| 馬匹健康／新鮮感 | 0.0404 | 38.9% | 0.0157 |
| 初出馬：級數 | 0.05 | 25% | 0.0125 |
| 初出馬：健康 | 0.30 | 38.9% | 0.1167 |

負磅係讓磅官對能力嘅評價，同健康無關。報告要喺健康格加一句
「⚠️ 呢格 38.9% 份額係負磅，同健康無關」先讀得明，即係放錯位。

## 唔做嘅嘢（之前已經判咗）

- **剷走健康嗰份負磅**：EXP-20260904-08 H1（Kelvin 當時要求）Gold 6.74→5.70、Good 24.87→23.83 → REJECT。
- **剷走成個負磅 leaf**：EXP-20261019-04 Good −2.61pp，Holm 後顯著 → REJECT。
- **重配兩個維度內部份額**：EXP-20261019-03 UNRESOLVABLE（NLL 改善 ≤0.0015）。

所以今次只搬位，總權重一分不變。

## 改動

- `horse_health` = 100% `risk_score`；權重 0.0404 × 0.611 = 0.0246844（初出馬 0.30 × 0.611 = 0.1833）。
- `class_advantage` = 班次分 + 負磅分；權重 0.1428 + 0.0404 × 0.389 = 0.1585156（初出馬 0.05 + 0.30 × 0.389 = 0.1667）。
  份額：標準 67.56% / 32.44%，初出馬 22.50% / 77.50%（`DimensionSpec.debut_leaves`）。
- **Shim `dimensions.LEGACY_WEIGHT_MERGE`**：舊結構兩個維度各自 round 到 2 位，直接改權重會令綜合分有 ±0.005 噪音。新級數值 =
  `(W_c·舊級數 + W_h·舊健康 − W_h'·新健康) / W_c'`，所以兩項加權和逐匹不變。`map_features_to_matrix_scores` 加 `debut` 參數揀權重。
- **唔可以 round shim**：綜合分經常啱啱落喺 x.xx5。round 到 6 位（誤差 ≤ 8e-8）已經令 5,365 匹有 2 匹 2 位小數翻轉；
  唔 round 最大誤差 1.4e-14、零翻轉。三個 shadow profile 原本 `round(base_matrix, 6)`（以前係 no-op）改為 `float()`。
- 同程舊調整（+0.43／−0.17，EXP-20261007-04）係經舊級數優勢計出嚟，改用 `LEGACY_CLASS_ADVANTAGE_WEIGHT = 0.1428` 同舊 75/25 式，唔讀 live 權重。
- 顯示尺重新量（5,365 匹）：級數 centre 63.24 / gain 2.0662（SD 4.840），健康 centre 69.00 / gain 2.1228（SD 4.711）。
  兩個維度意思變咗，所以佢哋嘅 ✅／➖／❌ 會變；**呢個係預期之內，唔影響排名**。
- 健康判讀剷走「38.9% 係負磅」警告；scoring contract 同模型說明更新。

## 驗證

| 檢查 | 結果 |
|---|---|
| 全語料 feature → 綜合分（5,365 匹，170 匹初出） | 最大 \|Δ\| 1.4e-14，2 位小數 **0 匹**唔同 |
| 真引擎重跑 4 個場次（11-04 HV、10-19 ST、05-09 ST、05-31 ST；538 匹） | `ability_score`、`rank`、`grade` 同其餘所有欄位逐格一樣；只有 `matrix_/matrixdisp_` 嘅 class／health 四欄變 |
| HKJC golden | 只有 `class_advantage`／`horse_health` 變；`ability`／`grade` 零變；已 `--record` |
| 單元測試 | 251 passed；新增 `test_weight_merge_rank_neutral.py`（3,000 隨機向量 × 標準／初出，places=10） |
| shadow `weight_refit_t02` | 繼承 `MATRIX_WEIGHTS`，同一條恆等式，唔郁 |

命令：

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform hkjc
python3 -m pytest -q .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests
# 全語料比對：scratch composite_dump.py（origin/main 54c089d7 vs 本分支），見 session 記錄
```

## 之後

Shim 要等 `class_advantage` 下次真正重建（refit 班次／負磅份額）先拆；拆之前要過 model-regression-gate。
