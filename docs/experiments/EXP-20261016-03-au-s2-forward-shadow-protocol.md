# EXP-20261016-03 預先登記：S2 forward shadow

> 凍結之前寫。凍結檔（`EXP-20261016-03-forward/freeze.json`）同評估結果檔一經寫入就唔准改。

- **日期**：2026-10-16
- **候選**：S2（EXP-20261016-02）：`pace_perf` 入面 L600 同 Sportsbet 全程速度各佔一半，
  配 pooled refit 權重。喺 41 日 OOS 嘅 refit arm 判 `RANKING_WIN`，但 Holm p 0.078，
  所以要喺**未睇過嘅新賽日**確認。合約 v3：forward holdout，一個 family 只開一次。
- **用戶指示**：2026-10-16「為 S2 起 forward shadow：凍結設計同權重，由 2026-10-17 起新賽日量，
  一個 family 只開一次。」

## 凍結

| 項 | 值 |
|---|---|
| forward 窗 | 2026-10-17 起（10-16 做緩衝，唔入 fit、唔入窗） |
| 評估時機 | 有快照兼有賽果嘅賽日 ≥ **41**（同 EXP-02 OOS 一樣多），之後**一次** |
| A0 | 現行 leaf + 凍結時 live 權重 |
| B0 | 現行 leaf + pooled refit 權重：2,485 場（08-05 → 10-15），2 個 draw 過閘 |
| B1 | S2 leaf + pooled refit 權重：同一批場次，16 個 draw 過閘 |
| refit 程序 | `au_walkforward_refit.py`，procedure hash `f92c8377…e033`，兩邊一樣 |
| code | 引擎目錄全部 `.py` + 6 個工具檔逐個 sha256 寫入凍結檔；評估時任何一個唔夾就拒絕 |

凍結權重（`B1` 對 `B0`）：`pace_perf` 0.177 vs 0.108、`class_weight` 0.287 vs 0.405、
`stability` 0.321 vs 0.300、`jockey_trainer` 0.648 vs 0.607、`track` 0.130 vs 0.108、
`preparation` 0.360 vs 0.396。

## 輸入：只用賽前不可改快照

- 每個場次揀 `_prediction_snapshots/` 入面悉尼時間 11:00 之前最後一個（`pick_snapshot` 嘅
  `pre_cutoff`）；冇就跳過，**唔用** 11:00 之後嘅後備快照。
- 快照簽名同逐檔 sha256 一定要對得上，唔夾就跳過並記數。
- 引擎用凍結 code 重新評分快照入面嘅 Logic。核對：10-14 三個場次 138 匹重播同 production
  dump 逐匹差 **0**。
- A_sb 嘅往績事件只用 `first_seen` ≤ 目標日嘅（即係嗰日或之前已經有頁面列出）；
  目標馬嘅往績由快照入面嗰份賽前 Formguide 攞，唔用之後可能被重抽嘅 live 檔。
- 外部官方計時疊加項：重播用快照建立時間做 `prediction_at`，兩個 arm 一樣，唔影響比較。
- 賽果：`AU_Historical_Raw_Race_Results.csv`，同 dump 一樣嘅配對規則。

## 判決（預先登記，唯一一次）

1. **主比較** B1 vs B0，`evaluate_full_record(mode="walk_forward_oos")`，primary Gold／Good，
   ranking `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`，按賽日 bootstrap 2000、seed 7、六塊。
   要 `PRIMARY_WIN` 或 `RANKING_WIN`。
2. **live guard** B1 vs A0：唔可以係 `primary_regression` 或 `ranking_metric_harm`。
3. 兩樣都過 → `ship_eligible = true`，可以準備上線改動（仍然要用戶批准）。
   否則 S2 結案 REJECT，**唔准**再開第二個 forward family 救佢（除非設計本身改咗、另開新實驗）。
4. 另報 B0 vs A0（現行權重有冇過時），只作參考。
5. 輸入係快照證實嘅賽前資料，所以 `leakage_audit_passed=True` 喺呢度係有根據嘅；
   呢個係 EXP-01／02 冇嘅條件。

## 唔准做嘅嘢

- 中途睇指標：`status` 只數賽日同場次，`evaluate --dry-run-counts` 只數可重播場次，兩個都唔計指標。
- 改 code、權重、等分比例、z 尺度、評估時機或者指標。
- 因為 forward 結果再調參然後重開。

## 指令

```bash
export PYTHONDONTWRITEBYTECODE=1
git checkout <凍結 commit>      # code hash 一定要夾
python3 scratch/au_s2_forward_shadow_20261016.py status
python3 scratch/au_s2_forward_shadow_20261016.py evaluate   # ≥ 41 個賽日之後，一次
```
