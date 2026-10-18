# EXP-20261019-03 — HKJC 維度內部份額 walk-forward refit：預先登記

- **登記日期**：2026-10-19，喺跑任何 arm **之前** commit
- **平台**：HKJC；Kelvin 2026-10-19 審查計劃第 2 步（外層權重已判維持現行，EXP-20261019-02）
- **範圍**：四個兩 leaf 維度。檔位與走位內部配方已判死（EXP-20260902-08），唔做。

| 維度（外層權重） | leaf A | leaf B | 現行 A 份額 |
|---|---|---|---:|
| 騎練訊號（0.236） | jockey_score | trainer_score | 0.55 |
| 狀態與穩定性（0.088） | form_score | consistency_score | 0.556 |
| 級數優勢（0.143） | class_score | weight_score | 0.75 |
| 馬匹健康（0.040） | risk_score | weight_score | 0.611 |

存檔 leaf 分重現維度分：殘差 0（騎練有除去配備 −3，照當殘差保留）。

## Arms（`hkjc_reflector/scripts/hkjc_inner_share_study.py`）

- `current`：現行份額，sanity 一定要重現 production 排名。
- `wf_<維度>` ×4：walk-forward，每個賽日只用之前賽日 fit A 份額 s'（sigmoid，0–1）同 τ（log τ，起點 6，範圍 0.5–30）；
  L2 λ=2 拉返現行份額；首 10 個賽日用現行。綜合分 = 原始 + 外層權重 ×（s' − s）×（A − B），其餘不變。
- v3 `walk_forward_oos`；家族 = 4 個 arm × 6 指標，Holm。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
I=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_inner_share_study.py
python3 $H run --dump-matrix --out dump.jsonl        # dump 而家包埋 leaf 分（"f"）
for a in current wf_trainer_signal wf_stability wf_class_advantage wf_horse_health; do python3 $I dump.jsonl --arm $a --out $a.jsonl; done
for a in wf_trainer_signal wf_stability wf_class_advantage wf_horse_health; do python3 $H compare current.jsonl $a.jsonl --stage4 walk_forward_oos --leakage-audit-passed; done
```

## 判決後

- WIN（Holm 後）→ 最後一步份額做候選，2026-10-19 起 forward ≥ 60 場確認先上線。
- 冇 WIN → 維持現行份額，記錄 fit 想郁嘅方向同 τ。

## 結果

見 `EXP-20261019-03-hkjc-inner-shares-results.md`：REJECT，但 λ=2 令份額郁唔到 → 實際 UNRESOLVABLE。
