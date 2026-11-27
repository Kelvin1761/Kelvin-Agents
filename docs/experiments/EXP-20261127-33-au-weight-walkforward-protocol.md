# EXP-20261127-33 預先登記：AU 排名權重 walk-forward refit —— v3 正式判決＋市場尺

> 寫於任何 v3 結果出現之前（2026-11-27）。承 [EXP-20261127-30](EXP-20261127-30-au-reeval-weights-and-draw-ladder.md)：
> refit 而家 19–26/400 過 fold 閘、方向穩定（pace_perf↑、track↓、jockey_trainer↑），但工具版 walk-forward（6 窗、2,400 場）
> Gold +0.25、Good −0.12、OBJ 2/6。嗰個係描述性，唔係合約判決。Kelvin 2026-11-27：「go ahead」（改善空間第 1 項）。
> 已睇過嘅數字：EXP-20261127-30 全部。所以呢度**唔准**按嗰啲數字揀設定 —— 下面嘅設定全部沿用工具預設同合約。

## 候選（`mode = walk_forward_oos`）

- **程序（凍結）**：`au_matrix_refit.fit_consensus`，目標 `place`（gold、good_pos、pass、t3prec），400 條 Dirichlet 候選，
  `min_folds = 4`（5 個 fold），seed 20260826；共識 = 過閘候選逐維度中位數，按現行係數總和歸一。
  冇候選過閘嗰段就用現行權重（= baseline，該段 Δ = 0）。
- **walk-forward**（合約 v3／m3 嘅 AU 規矩）：語料只用 2026-08-05 起乾淨 PIT 段；頭 20 個賽日唔計分；之後**每 7 個賽日重 fit 一次，
  只用嗰個賽日之前嘅場次**，預測下 7 個賽日。
- **baseline**：現行 `MATRIX_WEIGHTS`（main `c0e47dc2` 嘅 `dimensions.py`），固定。

## 判決

1. **排名尺**：`model_evaluation_decision.evaluate_full_record`，`mode = walk_forward_oos`，賽日 bootstrap 2,000、K = 6 時間塊；
   ranking metrics `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`。單一 arm、冇 Holm。
2. **市場尺**（合約 m3）：`market_ruler.py`（SP；有 BSP 就加報）報同市場差距 Δ（nll／場）同 95% CI。
3. **KEEP 路**：排名尺 `PRIMARY_WIN`／`RANKING_WIN` **而且**同市場差距唔變大（追市場軌），或者市場尺 B PASS（贏市場軌）。
   否則 REJECT。KEEP 都只係「可以上線」，上唔上係 Kelvin。
4. **安全**：baseline 同 candidate 同 sample hash、同場數；leakage：每次 fit 嘅訓練場次日期一定 < 預測賽日（工具要有測試攔住）；
   A/A（candidate = baseline 權重）一定要判 REJECT。

## 工具（同一個改動交付）

`au_racing/au_wong_choi_auto/scripts/au_weight_walkforward.py`：輸入 leaves dump，輸出逐匹 walk-forward ability（baseline＋candidate）
畀 `evaluate_full_record` 同 `market_ruler`。即係合約 §8 講嘅「AU walk-forward refit 預測產生器」。有測試：時間洩漏守衛、A/A REJECT。

## 唔准做

改 fit 程序、目標、seed、重 fit 頻率、起點；判完再試其他設定救；用 EXP-20261127-30 嘅窗口結果揀設定。
