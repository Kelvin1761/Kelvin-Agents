# EXP-20261010-06 — HKJC 9D 外層權重：中性起步 vs 現行 vs walk-forward refit

- **日期**：2026-10-10；平台：HKJC；Kelvin 第 1 條：「全部設中性，睇現行權重係咪最好」
- **語料**：harness `--dump-matrix`，main `13999e13`（9D），PIT priors，286 場（剔走 04 月 speed_score 死日）
- **工具**：`hkjc_reflector/scripts/hkjc_weight_study.py`（離線重排：保留 SIP／封頂等 residual，初出馬權重不變）
- **Sanity**：`current` arm 重排 = production 排名 **345/345**

## 預先登記 arms

| arm | 定義 | v3 模式 |
|---|---|---|
| neutral | 8 個加埋等於 1 嘅維度各 1/8；同程（centred）0.02 不變 | fixed_rule |
| wf_refit | 每個賽日只用之前賽日 fit（首 10 個賽日用現行）；場內 softmax，τ=3，權重 softmax(θ) ≥0 而且加埋 1，L2 λ=2 收縮返現行；L-BFGS | walk_forward_oos |

（第一版 wf_refit 用自己寫嘅 gradient step，步長大 25 倍，每次 fit 都塌落一個角（一個維度 1.0）；
係優化器 bug，唔係證據，改 L-BFGS 後重跑。τ、λ 冇改。）

## 結果（v3 全紀錄）

| | Gold Δ | Good Δ | NDCG@5 Δ | 賽日 Good SD |
|---|---:|---:|---:|---:|
| **neutral** | −1.40pp [−6.2, +3.1] | **−6.99pp [−11.5, −2.6]** | **−0.049 [−0.075, −0.026]** | 0.153 → 0.112 |
| **wf_refit** | −1.05pp [−4.5, +2.1] | −1.05pp [−3.7, +1.4] | −0.004 [−0.014, +0.006] | 0.153 → 0.157 |

neutral：冠軍首選 −9.4pp，六個時間塊 Good 五塊 ≤ 0 → **REJECT**，現行權重明顯好過全部平均。
wf_refit：全部 CI 跨零，primary 點估計各蝕 3 場 → **REJECT**，refit 贏唔到現行。

walk-forward 每次 fit 都想將 race_shape 由 27.4% 減到約 20–22%、級數優勢 14.3% → 16–19%、
健康 4.0% → 6–9%、晨操 1.0% → 4–5%，但 out-of-sample 冇改善。

## 結論

**維持現行外層權重。** 呢個係目前語料上嘅最佳已知答案：中性明顯差，refit 打和。同
[[hkjc-ranking-gains-cost-good]]「0.24–0.27 之間個目標平坦」一致。檔位結構性押注內檔
（EXP-20261010-02 附錄）嘅問題唔係外層權重可以解決 —— 要喺 race_shape 內部（檔位分嘅幅度）處理。
