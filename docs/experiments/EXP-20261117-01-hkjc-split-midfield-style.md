# EXP-20261117-01 — HKJC：守中再拆「守好位」—— dev REJECT，全 Wong Choi 維持 3 類跑法

- 日期：2026-11-17｜Kelvin「守中要唔要再拆守好位？」｜腳本 `patches/hkjc_draw_style/build4.py`（由 `build.py` 改，加 mode 3／4）
- 尺：HKJC 歷史回放尺 v4；base = `v3/base.jsonl`（冇檔位×跑法）；對照 = 同一腳本 mode 3（3 類 SD，即 live）。
- 忠實度：mode 3 輸出同上線用嘅 `v3/ds_SD.jsonl` 6,047 場逐匹 raw 差 0。

## 預先登記（跑之前固定）
SD4：跑法 ≤0.30 放頭、0.30–0.45 **守好位**、0.45–0.60 守中、>0.60 後上、冇 = 未明（切點 = 守中段中位，唔調）；
其餘（組別、檔位段、K=200、逐檔曲線、β 逐季 walk-forward）同 live SD 一模一樣。

## 結果（dev 2,488 場）
| | Δlog-loss | null | AUC | Gold | Good | 頭二 | 判決 |
|---|---|---|---|---|---|---|---|
| SD4 − SD3 | **+0.00009 [−0.00005,+0.00022]** | 32% | −0.0005 | +0.12 | +0.04 | −0.08 | **REJECT** |
β_style 逐季 SD4 同 SD3 差唔多（2022 起 20–24），即係多咗一類冇帶到新資訊，只係多咗格要估（每格樣本變細）。holdout 冇開。

## 決定
唔拆。跑法標準（`hkjc_racing_engine/run_style.py`）維持放頭／守中／後上 3 類；舊報告「前置／守好位／守中／後上」4 類死 code
同一個 release 剷走（Kelvin「一樣嘢只准一個標準」）。
