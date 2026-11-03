# EXP-20261103-12 結果：近績質素分低端加斜 —— REJECT

- **預先登記**：[protocol](EXP-20261103-12-au-form-quality-low-tail-protocol.md)；**baseline**：`678107c8`。
- **決定**：**REJECT**。code 唔入 main（研究碼喺分支 `claude-au-fq-low-tail-20261103`）。

候選：場內 z < −1 嗰段斜率加倍（`40 + 40(z+1)`），其餘不變。全語料 3,302 場（08-05 起）有 2,916 場分數郁。

## v3 fixed_rule（08-05 起 3,302 場）

| 指標 | Δ | 95% CI | p |
|---|---|---|---|
| Gold | **−0.182pp** | [−0.353, −0.033] | 0.011 |
| good_positional | −0.030pp | [−0.098, 0.000] | 0.776 |
| top3_capture_at5 | −0.030 | [−0.118, +0.048] | 0.472 |
| ndcg_at5 | +0.028 | [−0.019, +0.075] | 0.252 |
| top5_pairwise_auc | −0.037 | [−0.085, +0.005] | 0.087 |

分層 CI 全負：≤8 匹 Gold、Soft 5–6 Gold、首選 $1–3 Gold。§7 唔過。

## §8 四個 arm（walk-forward 覆蓋 2,299 場、59 賽日）

`REJECT / both_arms_reject`。fixed Gold −0.13 [−0.33, 0.00]；refit Gold 0.00 [−0.51, +0.52]、Good −0.22 [−0.75, +0.29]。
refit 唔救到 —— 唔係權重冇跟上，係形狀本身冇用。

## 點解失敗（學到嘅嘢）

量得好清楚嘅 cohort 超額（最低 10% −7.65pp CI 全負）**落唔到排名**，同 「cohort 差距唔等於可上線收益」、
consistency 照 pooled 曲線改形（EXP 舊記錄）同一個形狀：嗰批馬本身已經排喺後面（多數模型名次 6+），
再壓低佢哋只會郁頭 4 以外嘅次序；反而有少數 z < −1 但其他維度強嘅馬被拉出頭 4，傷咗 Gold。
「同名次期望比較」量到嘅係殘差，唔等於 leaf 形狀錯 —— 呢個方向唔好再試。

## 可重現

    WC_AU_FQ_LOW_TAIL=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out SP.json
    python3 scratch/au_track_simplify_judge_20261103.py BASE.json SP.json judge_fixed.json
    python3 au_walkforward_refit.py predict --data {BASE,SP}.json --out wf_{BASE,SP}.json
    python3 scratch/au_track_sp_s8_judge_20261103.py DUMP_DIR judge_s8.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/fq-tail/`。BASE = `scratch/stability/minus4.json`（= `27ebe77a`）。
