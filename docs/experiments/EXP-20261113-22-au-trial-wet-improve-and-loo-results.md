# EXP-20261113-22 結果：試閘「只計今次備戰期」、場地×濕地減半全部 REJECT；逐個消融 —— 只有「高班實績證明」剷咗唔蝕

- **預先登記**：[protocol](EXP-20261113-22-au-trial-wet-improve-and-loo-protocol.md)（`27eba863`，睇結果之前 commit）。
- 語料／判決窗／判決器同 EXP-20261113-21：BASE `d59f67e6`，2026-08-05 起 3,736 場，v3 `fixed_rule`，賽日 bootstrap 2000 次。
- P1／T1／T2 用研究開關 `WC_AU_TRIAL_ARM` 重 dump（`engine_core._formguide_trial_counts`／`trial_speed_raw`／`trial_performance_applies`
  只保留 `fg_last_formal_date` 之後嘅試閘；T1 另外取消 ≥6 場門檻）。開關已拆走，冇 commit。W1／W2／LOO 喺 BASE 離線重算。

## A. 改善 arm（Δpp [95% CI]，b = 6 塊入面 ≥0 塊數）

| arm | Gold | Good 位置 | top3 capture | NDCG@5 | top5 AUC | 判決 |
|---|---|---|---|---|---|---|
| P1 試閘備戰只計今次備戰期 | −0.21 [−0.50, +0.08] b1 | 0.00 b2 | **−0.20 [−0.35, −0.05]** | **−0.24 [−0.35, −0.13]** | **−0.16 [−0.25, −0.07]** | REJECT |
| T1 試閘 L600 今次備戰期＋冇 ≥6 場門檻 | −0.11 b2 | +0.03 b4 | +0.02 | −0.10 | −0.08 | REJECT |
| T2 試閘 L600 今次備戰期（保留門檻） | −0.08 b3 | +0.05 b5 | +0.07 | −0.05 | +0.00 | REJECT |
| W1 場地維度地況部分 ×0.5 | −0.05 b3 | +0.08 b5 | +0.03 | +0.01 | −0.01 | REJECT |
| W2 濕地 overlay ×0.5 | −0.05 b3 | +0.29 [−0.06, +0.67] b4 | +0.13 | +0.10 | +0.05 | REJECT |

**點解試閘「只計今次」反而差**：多數試閘喺復出之前跑，匹馬跑咗一兩場正式賽之後，「上一場之後」就冇試閘。
P1 令試閘備戰分中性比例由 64.5% 升到 **95.6%**，T2 令試閘 L600 分由 91.0% 升到 97.2% —— 收窄咗本來已經窄嘅覆蓋，而且排序指標 CI 全負。
即係**舊試閘仲有資訊**（多數係反映匹馬本身質素，唔只係今次狀態）。改善方向應該係**擴闊**覆蓋，唔係收窄；
「保留全部試閘、只係取消 ≥6 場門檻」未有登記，唔喺今次測（下一個候選）。

**場地×濕地**：減半任何一邊都只係 D1／D2 嘅一半效果 —— W2 Good +0.29 但 Gold −0.05（點估計負）。
EXP-20261113-21 加今次四個 arm 一致：Good 位置同 Gold 喺呢條軸上係 trade-off，冇一個固定值兩邊都唔輸。所以兩份都留，**只做歸組顯示**。

冇 arm 判 WIN，Holm 唔使調整。§8：P1／T1／T2 只做咗 fixed arm（AU walk-forward refit 工具未整理），唔過唔代表特徵本身冇用。

## B. 其餘組件逐個消融（診斷）

| 剷走 | Gold | Good 位置 | 最差 ranking | 分層 CI 全負 | 冇代價簡化？ |
|---|---|---|---|---|---|
| 近績質素分 | **−2.92 [−4.09, −1.75]** b0 | **−3.56** b0 | top5 AUC −2.06 | 26 格 | ❌ 最重要 |
| 騎師分 | **−1.07** b0 | **−1.61** b1 | NDCG −1.29 | 8 | ❌ |
| 練馬師分 | **−0.91** b3 | −0.11 | NDCG −0.45 | 4 | ❌ |
| L600 環境分 | **−0.75** b2 | −0.21 | top3 −0.60 | 3 | ❌ |
| Rating 分 | −0.29 b4 | −0.11 b3 | — | 0 | ❌（Gold < 0） |
| 人馬配搭分 | −0.21 b2 | +0.03 | top5 AUC −0.29 CI 全負 | 0 | ❌ |
| 大場次檔位 | −0.24 b2 | −0.51 b2 | top5 AUC −0.33 CI 全負 | 0 | ❌（forward 中，只報告） |
| 逐駒全程速度 | −0.03 b5 | +0.05 b6 | 全部 ±0.03 | 0 | ❌（Gold < 0，幅度細到量唔到） |
| **高班實績證明** | **+0.13 [−0.16, +0.42] b5** | **+0.05 [−0.33, +0.42] b4** | top5 AUC −0.00 | **0** | **✅ 符合** |

連同 EXP-20261113-21（試閘 L600、試閘備戰、級數分、場地維度、場地地況部分、濕地 overlay），**每一個入分組件都做咗剷走測試**。
只有「高班實績證明」（`proven_class_feature`）剷咗唔蝕。照登記**冇自動剷**，交 Kelvin 決定；佢係「冇代價簡化」，唔係改善
（兩個 primary CI 都跨零）。

## 同時上線嘅顯示（排名零差）

- dashboard 維度行：overlay 擺返落佢所屬維度，例如「場地與地況適性 +1.4 · 連濕地往績調整 +4.6 ＝ 合計 +6.0」
  （`renderDimensionStrip`，測試 `AU overlay is shown beside the dimension it belongs to`）。報告嘅「🧩 按維度合計」係 EXP-21 加。
- 賽績線 parser 修正驗證：11 月 5,616 匹有對手線嘅馬，舊引擎 215 匹（3.8%）同上游「強組比例」一致，修正後 **5,616／5,616**
  （`scratch/au_formline_consistency_20261113.py`）。

## 重跑

```bash
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-noise-20261113"
python3 scratch/au_noise_judge_20261113.py "$D/BASE.json" "$D/arms22" 22            # W1／W2／LOO
python3 scratch/au_track_rebuild_judge_20261102.py "$D/BASE.json" "$D/P1.json" OUT  # P1／T1／T2（dump 要研究開關，已拆）
python3 scratch/au_formline_consistency_20261113.py 2026-11-01
```

## 用戶決定（2026-11-13）：剷走高班實績證明

Kelvin：「剷走」。改動：`class_rating.PROVEN_CLASS_LIVE = False`（`WC_AU_PROVEN_CLASS_LIVE=1` 即時回退）—— `proven_class_overlay` 永遠回 0；
欄位 `proven_class_feature` 保留（評估工具、forward、dashboard 唔使改）。報告公式行、overlay metadata、`RANKING_OVERLAYS`（模型說明）唔再列；
數據合約唔再觀察佢（永遠 0 唔係死欄位），並已重新 `--calibrate`。

**真引擎驗證**：用新 code 重評全 archive（`FINAL.json`），對 `BASE − proven_class` 最大差 0.0001，冇一匹馬仲有非零值；
判決同離線 arm 一樣：Gold +0.134 [−0.161, +0.417] 5/6、Good +0.054 [−0.330, +0.417] 4/6，top5 AUC −0.002，分層冇 CI 全負
（`EXP-20261113-22-evidence/FINAL_proven_class_removed.verdict.json`）。性質係**冇代價簡化**，唔係改善。golden 唔覆蓋 overlay，所以 120/120 不變係預期。
