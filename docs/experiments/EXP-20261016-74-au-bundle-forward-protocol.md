# EXP-20261016-74 預先登記：今日改動合併 forward 確認 + walk-forward refit 權重 + GBM 對照

> 凍結之前寫。凍結檔（`EXP-20261016-74-forward/freeze.json`）同結果檔一經寫入就唔准改。

- **日期**：2026-10-16；**平台**：AU。
- **用戶指示**：「預先登記 forward 確認：今日所有改動合埋、walk-forward 權重 refit 同 GBM 對照，只用新賽日判。」
- **點解**：今日嘅改動全部喺同一個 41 日 OOS 窗判（重用多次）；要喺**冇見過嘅新賽日**確認合併效果，同時答「ML 搵權重／公式會唔會更好」。

## 四個 arm（全部喺凍結時固定）

| arm | 引擎 | 權重 | 角色 |
|---|---|---|---|
| **A0** | `d51796e1`（2026-10-15，今日改動之前） | 該 commit 嘅 live 權重 | 舊模型 |
| **A1** | 凍結時 main（今日全部改動，包括 EXP-01／05／06／07、12、13、18、70、71 F2、72 A、5c41c8be） | live 權重 | 而家 production |
| **B1** | 同 A1 | walk-forward refit 程序（`au_walkforward_refit.py`，hash `f92c8377…`）喺 **2026-08-05 → 2026-10-16 全部乾淨場次**一次 fit，凍結 | ML 權重 |
| **G** | 同 A1 嘅 leaf | GBM，凍結時訓練，模型檔 sha256 寫入凍結檔 | ML 公式（診斷） |

**GBM 規格**（固定）：`sklearn.ensemble.HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
min_samples_leaf=50, l2_regularization=1.0, random_state=7)`；特徵 = A1 全部 leaf（`FEATURE_KEYS`）+ wet／proven_class／full_time，
每個減場內平均（場內相對）；目標 = 入位（名次 ≤ 派彩位數）；排名分 = 預測機率。訓練資料同 B1 一樣（2026-08-05 → 2026-10-16）。

## 輸入：只用賽前不可改快照

同 EXP-20261016-03／-11：`pick_snapshot` 嘅 `pre_cutoff`（悉尼 11:00 前最後一個），簽名同逐檔 sha256 要夾；
抄去以場次命名嘅臨時目錄先評分（5c41c8be 之後原地都得，但 A0 引擎冇 `_meeting_dir`）。A0、A1 各自喺凍結 commit 嘅臨時 worktree 重評。

## 窗口同時機

- forward 窗：**2026-10-17 起**；有快照兼有賽果嘅賽日 ≥ **41**，之後**一次**。`status` 只數賽日，唔計指標。

## 判決（預先登記，唯一一次）

1. **合併確認** A1 vs A0，v3 `fixed_rule`：
   - `PRIMARY_WIN`／`RANKING_WIN` → 今日改動確認有效；
   - 任何 primary CI 全 < 0（`primary_regression` 而 CI 全負）→ **回退調查**：先逐個重測非 §7 改動（EXP-06 近績質素分、EXP-18、EXP-71 F2），用同一 forward 窗、Holm；
   - 其他 → 記錄「冇顯著分別」，維持現狀。
2. **ML 權重** B1 vs A1，v3 `fixed_rule`：WIN 而且 B1 vs A0 唔係 primary_regression → 可以上線 B1 權重（仍要用戶批准）；否則維持現行權重。
3. **ML 公式** G vs A1：**只作診斷，唔上線**。G WIN → 另開登記研究非線性結構；G 輸 → 記錄「線性組合已足夠」。
4. 2 同 3 係同一條「ML 會唔會更好」問題嘅兩個檢定，做 Holm。
5. 另報：頭兩名 $15+ 跑尾三分一、首選贏率。

## 唔准做

中途睇指標；改 arm、GBM 參數、訓練窗或者評估時機；因為結果再調參然後重開。
