# EXP-20261105-03 結果：近績直線名次＋剷穩定性分、L400 標準化 —— 7 個 arm 全部 REJECT

- **協議**：[EXP-20261105-03-hkjc-form-linear-and-l400-standardised-protocol.md](EXP-20261105-03-hkjc-form-linear-and-l400-standardised-protocol.md)
  （登記 `750de8c0` 之後；arm 同更正 `f1fe4035`，全部喺跑全紀錄之前 merge）
- **跑法**：`f1fe4035` detached worktree，`hkjc_eval_harness.py run --until 2026-10-10 --dump-matrix`，
  PIT priors；§8 refit 用 `hkjc_weight_study.py --arm wf_refit`。
- **語料**：351 場 replay → 配對 **286 場、29 個賽日**（剔 59 場死欄位／未配對）。1 場 ≈ 0.35pp。
- **判決**：全部 `REJECT / primary_regression`。冇一個 arm 需要 Holm 救，亦冇一個 Holm 前已經係 WIN。**冇開 forward，live 冇改。**

## 結果

| Arm | 模式 | 排序有郁 | Gold Δpp [95% CI] | Good Δpp [95% CI] | top3_capture@5 | NDCG@5 | 判決 |
|---|---|---:|---|---|---|---|---|
| A1 直線名次＋剷穩定性分 | fixed | 248 | +0.00 [−1.85, +2.06] | **−2.45 [−4.51, −0.35]** | +0.23 | −0.0023 | REJECT |
| A2 淨剷穩定性分 | fixed | 227 | −0.35 [−2.02, +1.05] | −0.70 [−3.19, +1.68] | −0.58 | −0.0010 | REJECT |
| B1 L400 標準化 | fixed | 156 | **+1.40 [+0.34, +2.78]** | −0.35 [−1.73, +0.72] | +0.23 | +0.0031 | REJECT |
| A1+B1 | fixed | 252 | +1.40 [+0.00, +3.07] | **−2.80 [−4.86, −1.04]** | +0.58 | +0.0011 | REJECT |
| A1 | wf_refit | 239 | +0.00 [−1.68, +1.75] | −1.75 [−4.18, +0.37] | +0.70 | +0.0010 | REJECT |
| B1 | wf_refit | 157 | +0.00 [−1.03, +1.03] | −0.35 [−2.02, +1.08] | −0.12 | −0.0026 | REJECT |
| A1+B1 | wf_refit | 245 | +0.70 [−1.03, +2.44] | −1.75 [−4.10, +0.35] | +1.17 [+0.00, +2.35] | +0.0034 | REJECT |

（refit 係對 `base` 同一程序 refit，即 B0 vs B1，`walk_forward_oos`。）

## 讀法

1. **A1（直線名次）真係差**：Good −2.45pp，CI 全負，大過 MDE（±1.76pp）。同更正段一致：
   對住 live 穩定性（有輸距覆核），直線名次 leaf 本身打和；剷埋輸距覆核穩定性分就蝕咗。
   refit 之後仍然係負（−1.75pp）。**現行「名次分檔＋輸距覆核穩定性分」唔使改。**
2. **A2（合併）判唔到，但冇證據話合併好**：Gold／Good 都係細負、CI 跨零（|Δ| < MDE）。
   即係穩定性分（輸距覆核）冇大貢獻，但剷走亦冇好處。按簡單優先原則可以考慮，
   但因為點估計兩個 primary 都 < 0，按規則 REJECT；**維持現狀**。
3. **B1（L400 標準化）Gold 升但 Good 跌**：Gold +1.40pp CI 全正（p 0.024），但 Good −0.35pp
   點估計 < 0 → primary_regression。Gold 嘅 +1.40 細過 MDE（±1.96），而且 7 個比較做 Holm 後
   p 0.024 一定唔顯著。refit 之後 Gold 跌返 0。**方向有啲意思，但證據唔夠上線。**
4. **A1+B1 疊加**：B1 嘅 Gold 改善保住，但 A1 嘅 Good 傷害照樣喺度 —— 兩樣冇互動，各自嘅效果直接加埋。

## 結論（交 Kelvin）

- **段速唔使做 AU 式加權**：篩選已經顯示加權平均冇幫到；標準化喺排名層判唔到。
- **近績分同穩定性分唔合併、唔改直線名次**：live 穩定性分有輸距覆核，已經做咗 AU「質素」想做嘅嘢；
  改直線名次反而蝕 Good。
- **唔加班次／獎金**：篩選時已經係負（香港贏升班、輸跌班）。
- 篩選教訓：**篩選一定要對住 live 嘅真分數**（存檔 Logic 入面），唔好用自己重砌嘅簡化版。
  今次篩選 +0.012 嘅「改善」完全係比較基準錯咗造出嚟。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
git worktree add --detach /tmp/exp03 f1fe403502fd2852b3e1ca14cc31469b0be17d5e   # 再 cp .wongchoi_*root
# 然後跟協議「量度」一節嘅命令
```

輸出（本機 scratch，唔入 repo）：`base/a1/a2/b1/a1b1.jsonl`、`*_wf.jsonl`、`compare_fixed.txt`、`compare_wf.txt`。
sample_hash（A1 fixed）`f6082046414423afc320196d96fec8890f39bc1898fcee2cc4b47f1a8ee9aa74`。
