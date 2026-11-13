# EXP-20261113-42 賽道直路數據補齊（純數據／報告層，排名零差）

- **日期**：2026-11-13；**平台**：AU；**baseline**：origin/main `355d9c08`。
- **來由**：EXP-20261113-41 發現 08-05 起 879 場（24%）冇直路長度，任何「直路 × 跑法」測試都睇唔到呢批場次。

## 發現

1. `au_track_geometry.json` 133 個場地只有 85 個有周長＋直路。缺嘅 48 個入面 37 個係 2026-10-09
   `backfill_track_classification_from_ra.py` 加入嘅（只有級別），生成器 `VENUES` 清單冇佢哋，所以由來冇抽過幾何。
2. **racinglife 而家對 script 回 ~100 bytes 防機械人頁（狀態碼 200）**。冇繞過；當「冇資料」處理（`RACINGLIFE_MIN_BODY`）。
3. **justhorseracing 有過期數**：Gawler 寫 2030／220，馬會官方（Gawler Barossa Jockey Club 場地資料）同 horise 都係 1840／300。
4. 生成器兩個陷阱：`--venue` 會將成個檔寫剩嗰幾行；全量重跑會洗走 RA 補嘅級別。

## 改動

- `fetch_au_track_geometry.py`：
  - 加第三個來源 **horise.com**（「circumference of … / … home straight」句式），次序 racinglife → horise → justhorseracing；
    任何兩個來源分歧超出容差 → 寫入 `conflict`。
  - `--fill-missing`：只抽未有周長＋直路嘅場地，其他行原封不動；`--venue` 亦改為部分更新。保留 `classification`／`classification_source`。
  - 抓唔到就保留舊行，唔用空行覆蓋。
  - 解析陷阱已加測試：「1,600m and a home straight」曾經被讀成直路 600m（數字邊界）；「600m into the home straight」唔係直路長度。
- `au_track_geometry.json`：有幾何場地 **85 → 108**（133 個）。新補 23 個：Armidale、Bairnsdale、Balaklava、Cootamundra、Donald、
  Gatton、Gawler、Geraldton、Gundagai、Hamilton、Kempsey、Kilmore、Kyneton、Launceston（justhorseracing slug `mowbray`）、Leeton、
  Lismore、Mornington、Morphettville Parks、Orange、Port Lincoln、Queanbeyan、Swan Hill、Tatura。
- 測試：`tests/test_fetch_track_geometry.py`（唔上網）。

## 核對

- **horise vs racinglife**（racinglife 已有嘅場地）：25 個兩邊都有，22 個喺容差內；3 個分歧（Rockhampton 2200/600 vs 1900/580、
  Sale 353 vs 400、Warrnambool 305 vs 350）。現有 racinglife 行冇改。
- **justhorseracing vs racinglife**：58 個兩邊都有，7 個分歧（12%）—— 所以 justhorseracing 排最後。
- 人手抽查（網上搜尋）：Mornington 1800/210、Launceston 1830/230、Gawler 1840/300 同補入嘅數一致。
- **排名零差**：兩個 worktree（舊幾何／新幾何）全語料重評 4,539 場，ability 0 匹變、leaf 0 匹變、排名 0 場變。
  幾何只入報告（場地尺寸、戰術劇本、`short_straight` 只餵 `_track_fit_brief`）。

## 未做

- 25 個場地三個來源都冇：Birdsville、Bordertown、Bowen、Bowraville、Broome、Carnarvon、Caulfield Heath、Cloncurry、Coleraine、
  Emerald、Ewan、Griffith、Gunbower、Gympie、Katherine、Longreach、Mt Isa、Narrandera、Roma、Thangool、Toodyay、Tuncurry、
  Warwick、York，加 Pakenham Synthetic（只有周長）。
- 只有 justhorseracing 一個來源嘅場地（今次 16 個）冇第二來源覆核；justhorseracing 實測約 12% 分歧。
- 冇用補完嘅數據重做 EXP-20261113-41（要另開預先登記）。

## 重跑

```bash
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/fetch_au_track_geometry.py --fill-missing
```
