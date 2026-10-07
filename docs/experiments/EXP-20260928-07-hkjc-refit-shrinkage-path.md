# EXP-20260928-07 — HKJC hierarchical refit shrinkage path

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：REJECT_DEV / TERMINAL UNOPENED
- **上游**：EXP-20260928-06；terminal 未開。
- **假設**：EXP-06 嘅 refit 方向有 ranking 訊號，但 full step 太遠而犧牲 Gold／Good；
  向 refit consensus 只移動 10–50% 或可保留排序收益而守住 primary。
- **Harness**：`docs/experiments/patches/hkjc_refit_shrinkage_path.py`

## 固定設計

完全沿用 EXP-06 同一語料、日期 split、5 段 expanding-time、loss、regularization、
bounds、PIT surface、初出馬鎖定及 leakage 規則。唔重搜 optimizer。

只測兩條 path：

- `outer`：production outer → 每 fold training 出嘅 `outer_only` fit；shape 不變。
- `combined`：production outer/shape → 每 fold training 出嘅 `combined` fit。

固定 shrink fraction `α ∈ {0.10,0.20,0.30,0.40,0.50}`：
`candidate = production + α × (fit − production)`；outer/ST simplex 再正規化，HV scales
clip 回 EXP-06 bounds。唔測 α>0.50，因 full step已證明 primary 回歸；唔加新 feature。

## Dev selection 與 terminal

每個 `family × α` 必須：

1. aggregate dev Gold、Good 都不低過 baseline；
2. 至少 3/5 fold 同時 Gold、Good 不低過 baseline；
3. capture@5、competitive recall@5、NDCG@5 至少兩項 aggregate 正。

合格候選按固定順序揀第一個：`outer` 優先 `combined`，同 family α 由小至大；即係揀
最簡單、最接近 production 嘅 passing step，唔取最高分。只此一個候選用全 dev 80 次
meeting bootstrap consensus 後縮放，再開 terminal 一次。少過60次成功收斂就唔開。

terminal 判決完全跟 Stage-4 v2；Gold／Good 任一點估計負即 REJECT。報 venue/surface、
field-size cohort。結果揭示後唔改 grid、family order 或 gate。

## 結果

10 個候選全部 fail；`outer` 同 `combined` 路徑喺實際排序上近乎一致：

| α | Gold Δ | Good Δ | capture@5 Δ | recall@5 Δ | NDCG@5 Δ | primary 非負 folds |
|---:|---:|---:|---:|---:|---:|---:|
| 0.10 | −1.2270pp | −1.8405pp | +0.2045pp | +0.2761pp | +0.0915pp | 2/5 |
| 0.20 | −2.4540pp | −1.2270pp | +0.4090pp | +0.8374pp | +0.5104pp | 2/5 |
| 0.30–0.50 | −4.2945pp | 負 | 正 | 正 | 正 | 1/5 |

α=0.20 Gold 已有全負 CI；α 越大 ranking 越好，但 Gold 損失同步擴大。最細 10%
step 仍過唔到 aggregate primary 同 3/5 fold gate，所以冇 consensus bootstrap，terminal
繼續封存。原始輸出：`/tmp/hkjc_refit_shrinkage_path_20260928.json`。

**判決：REJECT_DEV。** 問題唔係 full-step 太進取；沿同一 refit direction 微調亦無安全區。
