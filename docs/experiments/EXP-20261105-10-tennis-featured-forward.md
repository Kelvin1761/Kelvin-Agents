# EXP-20261105-10 — Tennis 精選（一場一注、每日最多 10 注）前向測試 + 21:00 出 card

- 日期：2026-11-05；平台：Tennis；類型：**選注政策 + 前向測試登記**（模型數學 `tennis-v1` 冇改）。
- 決定人：Kelvin（2026-11-05 對話）。計劃：`docs/plans/2026-11-05-tennis-strategy-and-rebuild-plan.md`。
- 已搜舊記錄：EXP-20261027-05（短賠熱門可行性，NEEDS MORE TESTING／不採用）、
  EXP-20260826-09、performance-audit-2026-08-21、統一研究計劃 15 個 REJECT_DEV。

## 量度（live DB 唯讀，2026-11-05，只計 `is_point_in_time=1`）

| 範圍 | 注 | ROI | 95% CI |
|---|---:|---:|---|
| 全部 value prop 注 | 1,357 | −10.7% | [−15.7, −5.7] |
| 回填批（`is_point_in_time` 空，唔算） | 1,495 | +11.2% | — |
| 正式推薦子集（10-28 起） | 188 注／77 場 | +2.2% | 按場 [−16.1, +21.1] |
| 一場一注（edge 最高），全期 | 636 | −6.5% | [−14.8, +1.5] |

- 每個 family 都負或者 CI 跨零；模型 Brier 0.2098 輸市場 0.1902；edge 欄排唔到結果。
- 同場多注：264 場多注賽事，edge 最高嗰注減同場其餘平均 **+15.1pp [+4.2, +25.9]**（歷史探索）。
- 每日頭 10 注按 edge／EV／機率排：冇改善；按機率最差（−16.4%）。
- card 由 10-28 起每日「資料未就緒」（封鎖理由係累計歷史數字），三星期冇出過正式推薦。
- Sportsbet 2026-11-05 22:36 已列出翌日 36 場，部分已有齊 props。

## 預先登記嘅規則（鎖定，之後唔准睇結果再改）

精選 = 以下全部成立：
1. `is_value=1` 且過 `strategy.meets_formal_profile`（凍結定價證據嘅 source_quality）。
2. family ∈ {讓局、首盤勝方、贏至少一盤、首盤讓局、讓盤、球員總局數}；Aces／雙誤／全場 Aces／盤數波膽暫停。
3. 賽事唔係 DISPUTED／mock；定價早過開賽；揀嘅時候未開賽。
4. 一場一注：edge → EV → 賠率 最高。
5. 每個 Sydney 日最多 10 注，按同一次序；0 注照出。
6. 平注 1 單位；以**第一次發出嘅價**計（`featured_picks.odds`），之後唔改，只加唔減。

時間：21:00 揀聽日（主 card，必定推）；23:00 同 09:00 只為新開盤嘅場次補充（有先推）。

## 判決（預先登記）

- 起點：第一注寫入 `featured_picks`（重播唔寫入）。
- ROI，bootstrap 4,000 次，seed 20260826，95% CI；一場一注所以按注重抽 = 按場重抽。
- 250 注已結算：CI 下限 > 0 → `ELIGIBLE_FOR_RELEASE_REVIEW`；上限 < 0 → `REJECT`；否則延到 600。
- 600 注：仍然跨零 → `NOT_PROVEN`（唔落真錢），之後唔再延。
- 功效：每注 SD ≈ 1.0；250 注 CI 約 ±12.8%（只捉到 +13% 以上），600 注約 ±8%。
- 夠數第一次推 Telegram（`check_featured_forward_milestone`，state 喺 `data/logs/featured-forward-state.json`）。
- 永遠唔會自動改模型或者開真錢。

## 描述性重播（唔計入判決）

`featured.candidates(pending_only=False)` + `choose`，10-28 至 11-05 用每日第一次定價時間：
66 注，已結算 60，+3.88u，ROI +6.5% [−18.3%, +31.1%]。11-04 冇任何 value 注。

## 改動

- `tennis_wc/featured.py`（新）：選注、凍結、成績、判決、Telegram 格式；`featured_picks` 表。
- `scripts/tennis_night_card.py`（新）+ launchd `.night`（21:00、23:00）。
- `tennis_daily_schedule.py`：取消舊 card／早報推送（同時刪 `daily_bet_message`／`notify_daily_bets`）；
  09:00 card 改為補充精選；統一 ROI 板 tennis 行改用精選；前向夠數提示。
- launchd：card 取消每朝健康心跳；daily 取消早報開關。
- Dashboard：`tennis_tracking.py` 輸出精選紀錄（凍結價）；tennis 頁精選放主位，其餘紙上注預設收起。

## 重現

```bash
cd tennis-wong-choi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_featured.py tests/test_scheduler.py
```

量度用嘅唯讀查詢喺 session scratchpad（`roi.py`、`sel.py`、`timing.py`），數字已全部寫入上表。
