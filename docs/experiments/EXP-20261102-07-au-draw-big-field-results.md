# EXP-20261102-07 結果：AU 大場次檔位分 —— 四個 arm 全部方向正，Holm 後未夠顯著（REJECT，建議 forward）

- **預先登記**：[protocol](EXP-20261102-07-au-draw-big-field-protocol.md)（`996f2d06`，量度之前）。
- **語料**：`abcf8958` 全語料 dump（同 EXP-20261102-04 定稿 `final_code.json` 一樣）；判決 2026-08-05 起 3,283 場、v3 `walk_forward_oos`；
  β 逐賽日用之前賽果擬合，頭 21 個賽日 warmup（β = 0）。

## 判決（Δ 單位 pp）

| arm | 郁咗場數 | Gold | Good | NDCG@5 | top5 AUC | v3（未 Holm） |
|---|---:|---|---|---|---|---|
| Z8（≥8 匹，z） | 2,093 | +0.15 [−0.27, +0.61] | +0.06 [−0.45, +0.56] | +0.25 [+0.02, +0.48] p 0.031 | +0.15 [−0.02, +0.32] | RANKING_WIN |
| Z10（≥10 匹，z） | 1,321 | +0.00 | −0.03（塊 4/6） | +0.17 [+0.00, +0.35] p 0.049 | +0.11 | primary_regression |
| R8（≥8 匹，raw 檔位格數） | 2,093 | **+0.30** [−0.09, +0.71] | +0.24 [−0.28, +0.77] | +0.22 p 0.068 | +0.16 | too_weak |
| ZD8（≥8 匹，按路程分 β） | 2,093 | +0.12 | +0.18 | +0.26 [+0.05, +0.47] p 0.017 | +0.15 [+0.01, +0.30] | RANKING_WIN |

**Holm（4 arm）**：ZD8 0.068、Z8 0.093、Z10 0.098、R8 0.098 —— **冇一個 < 0.05 → REJECT（arm_multiplicity_not_significant）**。
冇任何預先聲明分層 CI 全負。

## 睇到嘅嘢

- **方向一致正**：四個 arm 嘅 NDCG／AUC 全部正，Gold 冇一個負。同 2026-08-21「檔位輸畀冇檔位」相反 —— 嗰陣檔位值對真值只 47.4%（08-31 先修）。
- **β 穩定上升**：Z8 由 warmup 後 ~0.6–1.0 升到最後 1.43 綜合分／SD；ZD8 三段最後 1.32／1.52／1.48 —— **長途同短途 β 差唔多**，分路程冇帶嚟額外嘢。
- **「20 匹 vs 8 匹」**：R8（20 匹最外檔自然罰得更重）Gold、Good 點估計最高，但 NDCG 證據弱過 Z8；14+ 匹只約 150 場，Gold −1.3pp（n 細，CI 闊）。
  證據未夠揀邊條公式。
- 為咗避免「睇完揀最好」，**唔可以**因為 ZD8 未 Holm 嘅 p 最細就上線。

## 決定

REJECT（Holm 後唔顯著）。證據方向一致，值得做 **forward shadow**：凍結一個公式同 β，喺之後未睇過嘅賽日量
（要另外登記，同時加入 `au_forward_tracker.py`）。等 Kelvin 決定。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/draw-bigfield"
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out $S/dump.json   # abcf8958
python3 scratch/au_draw_bigfield_arms_20261102.py --dump $S/dump.json --outdir $S/arms
for a in Z8 Z10 R8 ZD8; do python3 scratch/au_draw_bigfield_judge_20261102.py $S/arms/base.json $S/arms/$a.json $S/judge/$a.json; done
```

證據：`EXP-20261102-07-evidence/`（判決 JSON 連分層、逐週 β）。
