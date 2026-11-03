# EXP-20261103-06 §7：薄樣本騎師改中性、練馬師證據標籤修正

- **日期**：2026-11-03；**平台**：AU；**baseline**：`9a7b7894`（EXP-20261103-05 簡化）。
- **用戶**：「rebuild this section with simplest code and removing all the bugs and dead code」。
- **⚠️ 呢個冇通過表現閘，唔係一個已證實嘅改善** —— §7 正確性修正。

## 錯處（唔靠績效數字證明）

1. **同一樣嘢兩把尺。** LY ≥10 場：騎師用勝率（prior 0.1271、spread 247）。少過 10 場（而冇資料庫 tier）就跌落一條
   舊公式：上名率 prior 0.365、spread 100 —— 另一個 prior、另一個斜率、甚至另一個指標。練馬師同樣情況係中性 60，
   而統一率嘅最低場數門檻本身就係「10 場以下講唔到嘢」。例：John Velazquez（世界級騎師）去年澳洲 1 騎 0 上名 → **58.3**，
   低過中性；5 騎 1 上名 → 56.7。
2. **練馬師證據標籤永遠係 observed。** `_feature_evidence_state` 用「base_label 冇『資料庫無記錄』」判斷，但呢句
   由來冇出現過。冇統一率又冇 tier 嘅練馬師（全語料 1,999 匹）都算有證據，令「資料覆蓋」偏高。唔入分。

## 改動

- 騎師 LY 少過 10 場（冇 tier）→ 中性 60，說明寫「去年官方僅 N 騎…未達 10 場可信門檻」；`jockey_trainer.thin_jockey_score` 剷走。
- 練馬師 `trainer_detail["source"]` = unified／db／neutral；證據標籤 observed 只限前兩個。

## 量度（v3 fixed_rule，08-05 起 3,302 場）

全語料 96 匹分數郁（全部係薄樣本騎師），94 場分數郁、13 場次序變、4 場頭 4 變。

| 指標 | Δ | 95% CI |
|---|---|---|
| Gold | 0.000pp | [0.000, 0.000] |
| good_positional | 0.000pp | [0.000, 0.000] |
| top3_capture_at5 | 0.000 | [0.000, 0.000] |
| ndcg_at5 | −0.002 | [−0.005, 0.000] |
| top5_pairwise_auc | −0.006 | [−0.015, 0.000] |

判決 `REJECT / ranking_evidence_too_weak`；§7：primary 冇顯著負、預先聲明分層冇 CI 全負 → **上線**。
證據標籤修正唔郁分數（dump 確認）。

## 可重現

    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out {base,new}.json
    python3 scratch/au_track_simplify_judge_20261103.py base.json new.json judge.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/jt-review/`。
