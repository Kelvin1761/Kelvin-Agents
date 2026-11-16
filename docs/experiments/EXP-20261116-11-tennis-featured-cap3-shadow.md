# EXP-20261116-11 — Tennis：精選 shadow arm「cap3」（賠率 <3.0）

- 日期：2026-11-16；平台：Tennis；類型：**預先登記 forward shadow**（紙上、唔發 Telegram 注單、唔上 dashboard、唔收實盤）。
- Kelvin 2026-11-16 批准開新 arm。
- 起因：EXP-20261116-08。正式精選（EXP-20261105-10）賠率 ≥3 嘅 10 注 0 中；大樣本 odds ≥3 模型平均 ~0.5，
  去水市場 ~0.2，賽果跟市場。精選按 raw edge 排名，令呢類注排頭位。
- 正式精選規則**冇改**。

## 規則（寫入任何 pick 之前鎖定）

- 同正式精選完全一樣（同一批 `featured.candidates`、同一個 `choose`：每場一注、edge→EV→賠率排序、每日 10 注、
  首次發出價凍結、23:00／09:00 只補未入選而未開賽嘅場次），**唯一分別：候選賠率一定要 < 3.0**（3.0 本身唔收）。
- 同正式精選喺同一刻（`publish_featured`）寫入 `featured_shadow_picks`（`arm='cap3'`），所以兩個 arm 見到同一批價。
- 結果：`prop_tracker` 結算（同一本帳），每注 1u。
- 判決：同 EXP-20261105-10 一樣嘅 `forward_verdict` —— 250 注第一次判（CI 下限 >0 → ELIGIBLE_FOR_RELEASE_REVIEW；
  CI 上限 <0 → REJECT；否則延至 600，600 仍未證實 → NOT_PROVEN）。按場 bootstrap 4000、seed 20260826。
- 次要（只描述，唔判）：同期（同一批 match_date）正式精選 ROI。
- 夠數推 Telegram（primary）：`shadow_forward_milestones`，state key `cap3:250`／`cap3:600`，存喺
  `data/logs/featured-forward-state.json`。系統唔會自動改精選規則。
- 改規則 = 新 arm 新名，唔准改 `cap3`。

## 預期

誠實預期：EXP-20261116-08 顯示 <3 嘅模型 value 注 ROI 都係 −10% 左右，所以 cap3 最可能係「蝕少啲」而唔係賺錢。
佢係安全欄測試，唔係 edge 測試。

## 檔案

`tennis-wong-choi/src/tennis_wc/select/featured_shadow.py`、`publish/telegram.py`（`publish_featured` 寫入、
`shadow_forward_milestones`）、`scripts/tennis_daily_schedule.py`（18:00 daily 檢查）、`tests/test_featured_shadow.py`。
