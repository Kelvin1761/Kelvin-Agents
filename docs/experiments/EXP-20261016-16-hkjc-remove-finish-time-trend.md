# EXP-20261016-16 — 剷走 HKJC 段速「完成時間趨勢 ±5」（§7 正確性修正）

- **日期**：2026-10-16；平台：HKJC；**合約 §7 正確性修正**（唔走候選流程）
- **決定**：Kelvin 2026-10-16 —— 剷走成條規則（另一個 §7 選擇「修標籤」見 EXP-20261016-14，打和）
- **改動**：`engine_core._apply_finish_time_trend` 同三個 call site、`scoring.FINISH_TREND_MICRO_WEIGHTS`、
  `_matrix_reasoning` 嘅「完成時間對標趨勢」特例、異常仗 shadow 嘅 `finish_time_trend` 抑制分支；
  `test_zero_start_season` 期望值同步。

> **呢個冇通過表現閘，唔係一個已證實嘅改善。**

## 1. 錯處（獨立證明，唔靠績效）

- 2026-06-19 `2731dd6a` 接線時註釋寫「ML-validated ±5」。
- 引擎搵 `"進步"`，但 Facts（`inject_hkjc_fact_anchors.py`）寫嘅係 `📈改善中`／`📉退步中`／`📊穩定`。
  全語料 `進步` 出現 **0 次**：1,290 匹 `📉退步中` 被 −5，1,027 匹 `📈改善中` 攞 0。
- 即係**上線嘅規則（單邊 −5）同驗證過嘅規則（對稱 ±5）係兩樣嘢**，前者從未驗證過。
- 同一個完成時間偏差已經由 `SpeedScorer`「步速修正等級」（−8 … +6.52）計分，單邊 −5 係重複扣分
  （大至尊 2026-10-14：同一仗休後差仗被 L400 趨勢、能量、步速修正、呢條規則扣四次）。

§7 試金石「如果績效數字相反，你仍然會改佢嗎？」—— 會：一條聲稱對稱但實際單邊、而單邊版本從未驗證嘅規則，
唔應該留喺 live。剷定修係 Kelvin 嘅取捨；修標籤 = 上線一個從未喺 production 跑過嘅 +5，剷走 = 回到冇呢條規則。

## 2. 零顯著退步（harness，production 路徑 + PIT，306 場，31 賽日）

| 指標 | Δ | 95% CI（賽日 bootstrap） |
|---|---:|---|
| Gold | +0.33pp | [−0.92, +1.58] |
| Good 位置 | +0.98pp | [−0.66, +2.59] |
| top3_capture@5 | +0.22pp | [−0.75, +1.05] |
| NDCG@5 | +0.0016 | [−0.0052, +0.0080] |
| competitive_recall@5 | +0.12pp | [−0.69, +0.84] |
| 實際前三平均名次 | −0.0065（越低越好） | [−0.0343, +0.0211] |

v3 `fixed_rule` 判決：`REJECT / ranking_evidence_too_weak`（即冇證據話佢更好 —— §7 唔要求）。
同 EXP-20261010-05 方向一致（+0.35／+1.40）。真 code 改動嘅排名同 EXP-05 arm **逐場完全一樣**（接線一致）。

預先聲明 cohort（Gold／Good Δpp [CI]）：

| cohort | n | Gold | Good |
|---|---:|---|---|
| 馬匹數 ≤8 | 8 | 0.00 | 0.00 |
| 馬匹數 9–10 | 17 | 0.00 | 0.00 |
| 馬匹數 11–12 | 146 | +0.68 [0.00, +2.42] | −1.37 [−4.35, +1.27] |
| 馬匹數 13–14 | 135 | 0.00 [−2.08, +2.14] | +3.70 [+0.75, +7.35] |
| 首選 SP ≤2.5 | 44 | +2.27 [0.00, +7.14] | **−2.27 [−7.32, 0.00]** ⚠️ 上界貼 0 |
| 首選 SP 2.6–4 | 92 | +1.09 [0.00, +3.57] | +2.17 [−2.11, +6.25] |
| 首選 SP 4.1–7 | 99 | −1.01 [−3.45, 0.00] | +1.01 [0.00, +3.19] |
| 首選 SP 7.1–12 | 55 | 0.00 | +1.82 [0.00, +5.88] |
| 首選 SP >12 | 15 | 0.00 | 0.00 |

**冇一個 CI 全負。** 首選 SP ≤2.5 嘅 Good 係 −1 場／44 場，上界 0.00，記低留意。

## 3. Leakage audit

剷走一條規則，冇加任何輸入 → PASS。

## 4. 其他閘

- `golden_scoring --platform hkjc`：120 匹全部一致（golden 只覆蓋 features→ability，唔包矩陣後調整；預期之內）。
- `data_contract`：leaf 分佈冇郁（`speed_score` leaf 冇改），唔使重新 calibrate。
- HKJC 模型說明已重新生成。
- HKJC auto tests 185 passed。

## 預期 live 影響

約 28% 有完成時間趨勢 `退步中` 嘅馬唔再被額外 −5 段速分（≈ −0.64 綜合分）；306 場回放入面 204 場排名有郁，
Gold／Good 淨變化 +1／+3 場左右，屬噪音範圍。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
git checkout 05dd1b20 && python3 $H run --out base.jsonl      # 改動前
git checkout <本 commit> && python3 $H run --out removed.jsonl
python3 $H compare base.jsonl removed.jsonl --stage4 fixed_rule --leakage-audit-passed
```
