# EXP-20260904-01 — 試閘分搬去有份量嘅維度

- **日期**：2026-09-04；**平台**：AU
- **baseline**：`2106b065` + 已驗證嘅 T2／T3 清理（`/private/tmp/au-t23-shipped.json`，
  1,891 場／18,871 匹）。
- **假設**：`trial_score` 場內 AUC **0.5587**、非中性覆蓋 **98.6%**，準過
  `preparation_score`（0.5466）同 `jockey_horse_fit_score`（0.5507），
  但佢坐喺 `pace_perf` 嘅 **5.8256%**，傳導率只有 **0.0070** 對佢哋嘅 **0.2524**。
  即係「準嘅 leaf 坐咗喺冇份量嘅位」。
- **搜索過嘅舊記錄**：EXP-20260903-03（本輪前身）、EXP-20260831-12、
  EXP-20260901-04／05（重配權重反覆失敗）、EXP-20260826-02／03。

## 預先登記

三個配置**喺讀任何結果之前就寫死喺 `scratch/au_trial_reallocation_20260904.py`
嘅 `VARIANTS` dict 入面**，冇行過階梯搜索，亦冇試過第四個配置
（`au-matrix-weights-tested-dont-change` 記錄過 edge-walking 會把「平」讀成「最優」）：

- **a25**：`pace_perf` = pace_figure 0.75 + trial 0.25
- **a50**：`pace_perf` = pace_figure 0.50 + trial 0.50
- **b50**：`preparation` = preparation 0.50 + trial 0.50；`pace_perf` = pace_figure 1.0

只改維度組成，唔改 `MATRIX_WEIGHTS`，亦唔重新評分 —— dump 已經有齊每個 leaf，
`map_features_to_matrix_scores` 由佢哋重砌矩陣。先 dev；任何 primary dev 回歸即停，
唔開該候選 terminal。過 dev 嘅先做**一次** terminal 確認。

⚠️ 呢個屬「重配權重」family，而該 family 喺呢個 repo 反覆失敗
（EXP-20260901-04／05、`au-only-half-the-leaves-score`）。開之前已知，唔會因為
dev 好睇就當已贏。

## dev 結果（1,384 場）

| 配置 | 分數有變 | top-4 有變場次 | gold | good位 | pass | champion | t3prec | 決定 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| a25 | 95.36% | 373 | **−0.65123** | −0.07236 | +0.14472 | +0.28944 | −0.02412 | 停 |
| a50 | 95.41% | 687 | **−0.36179** | −0.07236 | +0.65123 | −0.14472 | +0.19296 | 停 |
| **b50** | 95.38% | 662 | **+0.65123** | **+0.36179** | +0.86831 | +0.07236 | +0.38591 | **開一次 terminal** |

方向好一致而且解釋得通：`pace_figure_score` 場內 AUC **0.5714** 高過
`trial_score` 0.5587，所以由佢手上攞份額（a25／a50）會蝕；
而 `preparation_score` 0.5466 **低過** trial，所以兩者溝埋（b50）會賺。
即係話問題唔係「試閘分應該多啲權重」，而係「佢應該擺喺邊個維度」。

## terminal（只開一次，b50）

| 指標 | dev (1,384) | **terminal (507)** |
|---|---:|---:|
| gold | **+0.6512pp** | **−0.9862pp** ⟵ 符號反轉 |
| good_positional | +0.3618pp | +0.3945pp |
| pass | +0.8683pp | +1.1834pp |
| champion | +0.0724pp | +0.3945pp |
| top-3 precision | +0.3859pp | +0.5917pp |

頭 5 位配對 AUC：dev **+0.002508**、terminal **+0.000033**，
95% CI **[−0.004711, +0.004947]** —— terminal 上實質等於零。

**Stage 4 v2 判決：`REJECT / primary_regression`。**

如實講：五個指標入面有四個喺 terminal **都係正**，`good_positional` 兩個窗口
同向（+0.36 / +0.39）。但 primary 規則係 gold ＋ good_positional 兩者，
而 gold 由 dev +0.65 反轉到 terminal −0.99，所以 REJECT 成立。
**唔准因為「四比一」就改判**；換指標救候選喺合約入面等同 REJECT。

## 結論

1. 「準嘅 leaf 坐錯位」呢個假設**造得出 dev 訊號，但過唔到 terminal**。
   dev +0.65 → terminal −0.99 係典型過擬合形狀，而 terminal AUC ≈ 0
   進一步話俾我哋知冇真嘅排序增益。
2. 方向性結果照樣有用：由 `pace_figure`（AUC 0.5714）手上攞份額一定蝕
   （a25 −0.65、a50 −0.36），同 `preparation`（0.5466）溝埋先至喺 dev 有得賺。
   即係**份額應該跟 leaf 相對準確度走**，呢點站得住；企唔住嘅係「郁咗就會贏」。
3. 連同 EXP-20260901-04／05、`au-matrix-weights-tested-dont-change`，
   呢個係**第五次**獨立確認：喺呢個模型度重新分配維度份額過唔到 holdout。
   我建議之後唔好再喺「重配份額」呢條線度花時間，除非有新資訊源。

**決定**：a25／a50 **dev 停**；b50 **REJECT（terminal primary 回歸）**。
**commit**：只 commit 記錄同研究腳本，冇 commit 任何 model code。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-t23-shipped.json
for v in a25 a50 b50; do
  PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_trial_reallocation_20260904.py \
    --data /private/tmp/au-t23-shipped.json --variant $v --phase dev
done
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_trial_reallocation_20260904.py \
  --data /private/tmp/au-t23-shipped.json --variant b50 --phase terminal
```
