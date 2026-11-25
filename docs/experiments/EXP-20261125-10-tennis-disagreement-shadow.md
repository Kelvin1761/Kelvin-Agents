# EXP-20261125-10 — Tennis 精選 shadow arm「max_disagree20」：唔揀模型同市場差距 >20pp（預先登記）

- 日期：2026-11-25（喺第一注之前鎖定）；平台：Tennis；類型：**紙上 shadow arm**（唔發 card、唔上精選、唔上 ROI 板、唔落注、唔改真精選）。
- 決定人：Kelvin（2026-11-25 批准）。

## 假設

精選揀注係「每場 edge 最大嗰注」，所以有 winner's curse：edge 越大，越多係模型噪音而唔係真優勢。
2026-11-25 唯讀診斷見到 edge ≥0.20 嗰幾格 ROI 大約 −20%。
假設：剔走模型同市場差距 >20pp 嘅候選，改揀同場下一注，ROI 會**少蝕**。
**預期係減少虧損，唔係製造 edge** —— 呢個 arm 過唔過 `ELIGIBLE_FOR_RELEASE_REVIEW` 都唔會令精選變成有正 edge 嘅證據以外嘅嘢。

注意：個 −20% 係**睇咗之後**先開呢個 arm，所以佢唔可以做證據；呢個 arm 就係用之後嘅新數據測佢。

## 規則（鎖定）

精選規則（EXP-20261105-10）一模一樣，只改一樣：候選嘅 `edge` 要 **≤ 0.20**。
`edge` = 精選排序用嗰個數（`prop_tracker.edge` = 模型機率 − 去水後公平市場機率，`pricing/props.py`，四位小數）。
0.20 本身保留，0.2001 剔走。同一場如果最好嗰注超過 20pp，就揀同場下一注（edge → EV → 賠率）；冇就嗰場唔揀。
同真精選同一時間（21:00／23:00／09:00）、同一批候選、同一個價寫入 `featured_shadow_picks`（arm = `max_disagree20`），
凍結規則一樣，每日最多 10 注。

## 開始日期同範圍

2026-11-25 起，**只做前向**。shadow arm 嘅設計本身唔會 backfill（`featured_shadow.record` 只喺每日精選 run 寫入當日候選），
所以過去嘅精選唔會補入呢個 arm。

## 判決

同真精選同一把尺（`featured.forward_verdict`）：250 注已結算第一次判，600 注終判，唔准中途停（no optional stopping）；
夠數第一次經 `shadow_forward_milestones` Telegram 推 Kelvin（primary）。forward 總板（`publish_forward_board`）同 dashboard
（`tennis_tracking._shadow_arms`）都係逐個 `ARMS` 列，所以自動出現。
描述性（唔計判決）：同期真精選 ROI（`real_arm_same_dates`）。
功效：250 注只捉到大約 +13% 以上嘅 ROI；呢個 arm 同真精選大部分注重疊（只有 edge >0.20 嗰啲場會唔同），
所以兩者差距要好大先睇得出。

永遠唔會自動改真精選。改呢個 arm = 開新名嘅 arm。

## Code

`tennis-wong-choi/src/tennis_wc/select/featured_shadow.py`（`ShadowArm.max_disagreement`、`ARMS["max_disagree20"]`；
現有 arm `max_disagreement=None`，行為不變），測試 `tests/test_featured_shadow.py`（邊界、現有 arm 不變、milestone、總板）。
