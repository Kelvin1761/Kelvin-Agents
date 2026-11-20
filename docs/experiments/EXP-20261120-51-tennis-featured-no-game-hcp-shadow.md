# EXP-20261120-51 — Tennis 精選 shadow arm「no_game_hcp」：剔走全場讓局（預先登記）

- 日期：2026-11-20（喺第一注之前鎖定）；平台：Tennis；類型：**紙上 shadow arm**（唔發 card、唔上精選、唔落注、唔改真精選）。
- 決定人：Kelvin（2026-11-20，「開剔走讓局 shadow arm」）。

## 點解

全場讓局（`player_game_handicap`）係唯一喺兩批數據都負嘅 family：
- 上線前可核實 value 注：349 注 −15.8% [−31.6, +0.6]（EXP-20261105-10 量度）。
- 精選前向：29 注已結算 −37.9% [−68.9, −6.6]（EXP-20261120-50）。

第二個數字係**睇咗之後**先開呢個 arm，所以佢唔可以做證據；呢個 arm 就係用之後嘅新數據測佢。

## 規則（鎖定）

精選規則（EXP-20261105-10）一模一樣，只改一樣：`player_game_handicap` 永遠唔係候選。
首盤讓局（`player_first_set_game_handicap`）照留。同一場如果最好嗰注係讓局，就揀同場下一注（edge → EV → 賠率）。
同真精選同一時間（21:00／23:00／09:00）、同一批候選、同一個價寫入 `featured_shadow_picks`（arm = `no_game_hcp`），凍結規則一樣，每日最多 10 注。

## 判決

同真精選同一把尺（`featured.forward_verdict`）：250 注已結算第一次判，600 注終判；
夠數第一次經 `shadow_forward_milestones` Telegram 推 Kelvin（primary）。
描述性（唔計判決）：同期真精選 ROI（`real_arm_same_dates`）。
功效：250 注只捉到大約 +13% 以上嘅 ROI；呢個 arm 同真精選大部分注重疊，所以兩者差距要好大先睇得出。

永遠唔會自動改真精選。改呢個 arm = 開新名嘅 arm。

## Code

`tennis-wong-choi/src/tennis_wc/select/featured_shadow.py`（`ShadowArm.excluded_families`、`ARMS["no_game_hcp"]`），
測試 `tests/test_featured_shadow.py`。
