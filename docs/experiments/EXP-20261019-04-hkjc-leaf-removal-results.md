# EXP-20261019-04 結果 — HKJC 逐 leaf 移除：全部保留，冇噪音可剷

- **登記**：`EXP-20261019-04-hkjc-leaf-removal-protocol.md`（commit `9886ce1e`，跑之前已 push）
- **Sanity**：`current` 重排同 production 0／365 唔同。345 場（剔死日）。
- **判決**：9 個 arm 全部 REJECT（剷走唔贏）→ **全部保留**。

| 剷走（設 60） | 有效權重 | 變動場 | Gold Δpp [CI] | Good Δpp [CI] | NDCG@5 | 判決 |
|---|---:|---:|---|---|---:|---|
| jockey_score | 0.130 | 334 | −1.16 [−3.52, +1.42] | **−4.35 [−7.44, −1.45]** | **−0.0286** | REJECT（Holm p≈0） |
| form_score | 0.049 | 319 | −0.58 | **−2.90 [−5.52, −0.29]** | −0.0049 | REJECT |
| weight_score | 0.051 | 248 | 0.00 | **−2.61 [−4.15, −1.18]** | +0.0003 | REJECT（Holm p≈0） |
| formline_strength_score | 0.080 | 310 | −2.03 [−4.21, 0.00] | −2.32 [−5.31, +0.59] | −0.0119 | REJECT |
| trainer_score | 0.106 | 271 | −0.58 | **−2.03 [−3.58, −0.30]** | −0.0007 | REJECT |
| class_score | 0.107 | 271 | 0.00 | −1.45 [−3.52, +0.57] | −0.0007 | REJECT |
| risk_score | 0.025 | 131 | −0.58 | −0.87 [−2.45, +0.30] | −0.0021 | REJECT |
| consistency_score | 0.039 | 271 | +0.58 [−1.46, +2.83] | +0.87 [0.00, +1.98] | −0.0006 | REJECT（ranking_metric_harm） |
| trackwork_trend_score | 0.010 | 73 | 0.00 | 0.00 [−1.16, +1.18] | −0.0014 | REJECT（too_weak） |

REJECT = 剷走會輸（或者判唔到）。

## 解讀

- 騎師分係全模型最重要嘅 leaf（剷走 Good −4.35pp、NDCG −0.029，Holm 後顯著）；負磅分調轉方向後（EXP-20260904-09）亦係顯著有貢獻。
- 兩個「冇可量度貢獻」：
  - **consistency_score**：剷走 primary 微升（Gold +2、Good +3 場）但前三平均名次變差；同 form_score 高度重疊。判唔到，唔剷。
  - **trackwork_trend_score**：剷走 0 變化（權重 1%）；同 EXP-20261019-02 wf_refit_tau 想將晨操權重設 0 一致。
- 冇一個 leaf 剷走後顯著更好 → 冇「噪音 leaf」可以剷。

## 工具

`hkjc_reflector/scripts/hkjc_leaf_removal_study.py`（離線，用 harness dump 嘅 leaf 分）。
