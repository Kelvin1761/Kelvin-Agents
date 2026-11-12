# EXP-20261111-11 HKJC L400 標準化 forward 登記

- **日期**：2026-11-11（登記；未睇任何 forward 結果）
- **平台**：HKJC
- **觸發**：Kelvin 揀「先做 L400 標準化」；發現 EXP-20261105-03 已經做過 A/B，Kelvin 決定登記 forward 確認
- **前置**：EXP-20261105-03 B1 —— 回放 ≤ 2026-10-10（286 場）`fixed_rule` Gold **+1.40 [+0.34, +2.78]**、Good −0.35 [−1.73, +0.72]
  → REJECT（primary_regression）；refit 後 Gold 0；Holm 後唔顯著。EXP-20261020-01 篩選 +0.0064 跨零
- **改到嘅檔案**：`hkjc_forward_tracker.py` 加 `l400_standardised`；**冇改模型**

## 設計（預先寫死）
- arm：`docs/experiments/patches/hkjc_arm_l400_standardised.py`，**原封唔改**（上仗 L400 − 上仗（場地／跑道, 路程）cell 平均
  ＋ 全體平均，平均只用目標賽日之前嘅 Logic，cell ≥30，再套現行門檻）
- 窗：`since = 2026-10-11` —— EXP-20261105-03 協議已將呢段留做 forward holdout，A/B 只用到 10-10，冇人睇過 B1 喺呢段嘅結果
- 登記時已有 **90 場**（≥ 60），下一次排程 `judge_ready` 會即刻判
- baseline 係**今日 live**（已含 EXP-20261111-10 評分差距）；arm 只加 L400 標準化
- 判決（`harness_ab` 固定規則）：Gold、Good、NDCG@5 Δ 全部 ≥ 0 → Telegram「建議上線（等你決定）」；否則維持絕對值。
  永遠唔會自動改模型
- 唔換窗、唔換 cell 定義、唔加 L400 趨勢去救

## 結果
（夠數後由 `hkjc_forward_tracker` 自動判同凍結；結果補喺呢度）

## 順手修正：已 decided 嘅 forward 照樣會被自動判
`judge_ready` 只跳過「已凍結判決」，冇跳過 `decided`（人手判完）。即係 `weight_rating_gap`（EXP-20261111-10 已上線、
已標 decided）夠 60 場時仍然會對住**已改咗嘅 live** 跑 arm，再發「建議上線／維持現狀」—— 誤導。
而家 `decided` 一律唔再自動判（同欄位註解「之後只顯示，唔再提醒」一致）。測試：`test_decided_harness_ab_is_never_auto_judged`；
另加 `test_post_live_revert_says_old_version_did_not_lose`（EXP-20261111-10 上線後 forward 嘅字眼）。

## Forward 結果（2026-11-12，登記命令原封跑；排程每週 review 會自己再凍結一次）
since 2026-10-11，99 場（門檻 60）、67 場排名有變，baseline origin/main `4e6dae6a`：

| 指標 | Δ | 95% CI |
|---|---|---|
| Gold | −2.02pp（少 2 場） | [−5.00, 0.00] |
| Good 位置 | +1.01pp（多 1 場） | [0.00, +3.09] |
| NDCG@5 | −0.0036 | [−0.02, +0.01] |

過關條件係三樣全部 ≥ 0 → **唔過，維持絕對值**。回放時 Gold +1.40／Good −0.35，forward 調轉咗符號 —— 回放嗰個 Gold 升幅冇延續。
