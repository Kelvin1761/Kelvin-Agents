# EXP-20261028-15 結果：出賽經驗校準 —— REJECT

- **預先登記**：[protocol](EXP-20261028-15-au-career-starts-calibration-protocol.md)（`6076fb01`，量度之前 commit；歷史保存喺分支 `claude-au-starts-cohort-prereg-20261028`）。
- **語料**：`dump_new`（main `93f8050f` 引擎），2026-08-05 起；walk-forward 扣 warmup 後測試 2,012 場／53 個賽日、8 個窗。
- **決定**：S1、S2 **REJECT**（`primary_regression`）。AA REJECT（把尺正常）。冇改動上線，forward shadow 唔開。

## 判決

| arm | 改到場數 | Gold | Good 位 | top5 AUC | 分層 CI 全負 |
|---|---:|---|---|---|---|
| AA | 0 | 0 | 0 | 0 | 冇 |
| **S1**（九組） | 740 | −0.20pp [−0.87, +0.49] | +0.20pp [−0.28, +0.71] | +0.0013 [−0.0004, +0.0029] | **首選 20+ 仗 Gold −0.88 [−1.73, −0.20]** |
| S2（3 仗＋20+） | 338 | −0.15pp [−0.46, +0.20] | +0.30pp [+0.05, +0.61] | +0.0012 [+0.0000, +0.0024] | 冇 |

Gold 21.82% → 21.62%（S1）／21.67%（S2）；Good 位 26.04% → 26.24%／26.34%。

S2 嘅 Good 位 CI 下界 > 0（p 0.04），但 Gold 點估計 < 0 → 第 2 步已經 `primary_regression`；
而且 S2 有挑選偏差，按 protocol 唔可以單獨上線，Holm 之後亦唔顯著（p 0.08）。

## offset（逐窗，綜合分點）

- **3 仗**：+1.02 → +1.53 → … → +1.53，八個窗全部正，穩定。全紀錄 +1.63。
- **20+ 仗**：+0.25 → +0.09 → −0.12 → … → −0.46，**由正變負**，即係早期數據根本唔支持「老馬被高估」。全紀錄 −0.52。
- 其餘：1 仗 −0.79、5 仗 −0.92、4 仗 +1.02，其他 |x| < 0.5。全部細過一分。

## 解讀

- 校準方向冇錯（排名指標三個都輕微正），但幅度細（±1.6 分），換到嘅只係頭 5 名入面嘅次序，
  **唔係揀中前三** —— 同 EXP-11 封頂、EXP-14 G5 一樣嘅形狀。
- 20+ 仗：入位率對齊名次之後係偏低（−0.9pp），但扣分之後首選係 20+ 仗嘅場次 Gold 顯著跌。
  即係模型將佢哋排第一嘅時候，佢哋其實贏得到；入位率低係集中喺「排第一但輸」以外嘅情況。
  cohort 差距冇反解到一個可以扣分嘅 term（記憶 `cohort-cells-are-not-term-evidence`）。
- 3 仗馬嘅低估係真同穩定，但單獨加 +1.5 分（S2）都換唔到 Gold。
- **結論**：出賽經驗本身唔需要校準。2 仗 vs 6 仗嘅公平問題喺 EXP-11 更正已經答咗（冇偏差）；
  呢次證實連見到差距嗰幾組，修正都冇收益。

## 檢查
- **leakage-audit**：PASS —— `career_starts` 係排位表賽前欄位；offset 只用測試窗之前賽日 fit。
- **golden_scoring**：冇郁（冇改 model code）。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/exp-20261028-fq-weight-class"
for a in AA S1 S2; do python3 scratch/au_starts_offset_wf_20261028.py --dump "$X/dump_new.json" --arm $a --out "$X/starts_$a.json"; done
```

證據：`EXP-20261028-15-evidence/`。
