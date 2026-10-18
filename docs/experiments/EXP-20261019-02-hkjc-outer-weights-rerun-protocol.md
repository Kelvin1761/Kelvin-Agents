# EXP-20261019-02 — HKJC 外層權重重跑（修 bug 後、τ 一齊 fit）：預先登記

- **登記日期**：2026-10-19，喺跑任何 arm **之前** commit
- **平台**：HKJC；Kelvin 2026-10-19：審完九個維度、修咗大約 8 個 bug 之後，再睇外層權重使唔使 refit。
- **上次**：EXP-20261010-06（neutral REJECT、wf_refit 打和）；10-15 修洩漏後重跑判決不變。

## 點解重跑

1. 10-10 之後模型改咗：同程鍵（live）、venue（回放）、見習減磅、消耗標籤、晨操趨勢、剷完成時間 −5、加最快第一段。
2. 語料改咗：venue 修正令 57 場回放郁；加咗 10-11、10-14 兩個賽日。
3. 方法：10-10 用固定 τ=3。EXP-20261018-51 量到 τ=3 太自信（自由模型分係數 −0.59），會令 likelihood 偏向噪音。

## Arms（`hkjc_reflector/scripts/hkjc_weight_study.py`）

| arm | 定義 | v3 模式 |
|---|---|---|
| current | 現行權重（sanity：一定要重現 production 排名） | — |
| neutral | 8 個加埋等於 1 嘅維度各 1/8；同程 centred 0.02 不變 | fixed_rule |
| wf_refit | 同 EXP-20261010-06 一模一樣（τ=3、λ=2、首 10 賽日用現行） | walk_forward_oos |
| **wf_refit_tau** | 同上，但每步 θ 同 log τ 一齊 fit（起點 3、範圍 0.5–30） | walk_forward_oos |

家族 = neutral、wf_refit、wf_refit_tau；Holm（3 × 6 指標）。λ、warm-up、語料唔准改。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
W=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_weight_study.py
python3 $H run --dump-matrix --out dump.jsonl
for a in current neutral wf_refit wf_refit_tau; do python3 $W dump.jsonl --arm $a --out $a.jsonl; done
python3 $H compare current.jsonl neutral.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare current.jsonl wf_refit.jsonl --stage4 walk_forward_oos --leakage-audit-passed
python3 $H compare current.jsonl wf_refit_tau.jsonl --stage4 walk_forward_oos --leakage-audit-passed
```

報埋每個 walk-forward 步 fit 出嚟嘅權重（`*.weights.json`）同 τ 軌跡。

## 判決後

- 有 arm **WIN（Holm 後）** → 用最後一步權重做候選，2026-10-19 起 forward ≥ 60 場一次性確認先上線。
- 冇 WIN → 維持現行權重，記錄 fit 想郁嘅方向。
- 同時報：如果 τ fit 收斂喺明顯唔係 3 嘅值，記低（之後 EXP-10 類篩選要用）。

## 結果

見 `EXP-20261019-02-hkjc-outer-weights-rerun-results.md`：三個 arm REJECT，維持現行；τ fit ≈ 5–6.4。
