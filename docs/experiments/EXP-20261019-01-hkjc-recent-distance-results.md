# EXP-20261019-01 結果 — 同程只計近 N 仗：REJECT（Gold／Good 互換，閘門分辨唔到）

- **登記**：`EXP-20261019-01-hkjc-recent-distance-protocol.md`（commit `1c80d937`，跑之前已 push）
- **baseline**：完整往績（現行 live）；同 EXP-20261018-13 完整往績回放逐場 **0 場唔同**（接線一致）
- **判決**：三個 N 都冇 WIN（Holm 後最細 0.432），全部 |Δ| < MDE → **REJECT**；live 維持完整往績。

| N | 變動場 | Gold Δpp [CI] | Good Δpp [CI] | NDCG@5 | 判決 |
|---|---:|---|---|---:|---|
| 6 | 152 | −0.58 [−1.47, 0.00] | **+1.16 [+0.28, +2.31]** | +0.0002 | REJECT（primary_regression） |
| 10 | 82 | −0.29 [−0.88, 0.00] | +0.58 [0.00, +1.46] | +0.0008 | REJECT（primary_regression） |
| 15 | 25 | −0.29 [−0.88, 0.00] | +0.29 [0.00, +0.90] | +0.0014 | REJECT（primary_regression） |

時間塊（N=6）：Gold −1.7、0、0、−1.7、0、0；Good +3.4、0、+1.6、+1.7、0、0。
10-07 起嘅 29 場：三個 N 都 0 變化（新賽日數據少，唔代表冇效果）。
Holm：N=6 Good 原始 p 0.027 → 0.459；N=15 平均名次 p 0.024 → 0.432。

## 解讀

- 窗口越短，**Good 升、Gold 跌**：N=6 約 +4 場 Good、−2 場 Gold。EXP-13 嘅「完整往績 Good −1.45pp」大部分可以由 N=6 收返，
  但代價係 Gold。即係唔係純粹「完整往績變差」，而係 Gold／Good 嘅取捨。
- 幅度全部細過閘門 MDE（Gold ±1.96、Good ±1.76）—— 判唔到邊個真係好啲。

## 結論

- 唔改 live（完整往績）。唔換 N 再試（換參數救候選 = REJECT）。
- 「剷走同程調整」未測；EXP-20261007-04 判過佢係結構上要留嘅 component（distance_fit AUC 0.60）。
- code（完整往績注入 ＋ arm）喺 branch `claude-hkjc-recent-distance-20261019`，唔 merge。
