# EXP-20260907-01 配備變更抽取修復：兩個 regex 落差，零排名影響

- **日期**：2026-09-07
- **平台**：AU
- **假設**：`health_score` 空殼嘅成因之一（配備欄位 0% 有值）係抽取缺陷，唔係「Sportsbet 冇呢啲數據」。**成立。**
- **搜索過嘅舊記錄**：**EXP-20260826-07**（配備做排名特徵，REJECT）、
  EXP-20260905-04、`docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`、
  memory `scraper-silent-drop-failure-mode`、`au-written-field-is-not-a-filled-field`
- **改到嘅檔案**：`au_racing_engine/engine_core.py`（三處）、`tests/test_gear_change_display.py`

## 缺陷一：`^Gear:` 對唔上 `SportsbetGear:`
`claw_sportsbet_form` 寫落 Formguide 嘅係
```
SportsbetGear: Changes: Blinkers FIRST TIME, Tongue Tie OFF
```
而 `_summarize_formguide_section` 用 `_capture(section, r"^Gear:\s*(.+)$")`（`re.M`）。
`^` 錨定行頭，所以 `SportsbetGear:` **永遠唔會 match** ——
`_data["gear_line"]` 全語料 8,224 匹 **0% 有值**（key 100% 存在）。

實測證明（同一段真 Formguide）：
```
現行 ^Gear:                        → ''
修正 ^(?:Sportsbet)?Gear:          → 'Cross-over Nose Band FIRST TIME, Tongue Tie FIRST TIME, Winkers FIRST TIME'
```

## 缺陷二：`has_blinkers` 查一個唔存在嘅格式
`"Blinkers: Yes" in gear_line` —— 呢個字串**全語料唔出現**。真實文字係
`Blinkers FIRST TIME` / `Blinkers AGAIN` / `Blinkers OFF`。
改為 `\bBlinkers\b(?!\s+OFF)`（有戴、而且唔係除下）。

## 來源優先次序：Formguide 行先
2,366 個 runner 位（2026-09-01→09-04）逐匹對兩個來源：

| | n | |
|---|---:|---|
| 兩邊都有 | 434 | 其中 **140（32%）Racecard 截短咗** |
| **只有 Formguide** | **94** | Racecard 執唔到 |
| 只有 Racecard | **0** | —— |
| 兩邊都冇 | 1,838 | |

Racecard 係 Formguide 嘅**嚴格子集**，而且會截短：
```
Racecard  Blinkers FIRST TIME
Formguide Blinkers FIRST TIME, Cross-over Nose Band FIRST TIME
```
→ `gear_change` 改為 Formguide 行先、Racecard fallback。
報告覆蓋 **18.3% → 22.3%**，另外 140 匹由截短變完整。

⚠️ 揀「長嗰個」唔安全（長度唔等於完整），所以用明文優先次序。

## 剷走 `health_score` 兩個 gear 分支
修好 regex **之前**佢哋由來冇 fire 過（`gear_line` 一直空、`Blinkers: Yes` 唔存在），
所以剷走係**零分數變化**。但唔剷嘅話，regex 一修好就會由「一直死」突然變成
「配備入分」—— 而 EXP-20260826-07 已經 REJECT：訊號真（除下配備 −3.86pp
[−6.94, −0.75]）但同 `form_score` 重複（有變更嘅馬 form 平均 59.83 vs 62.10），
四個扣分幅度冇一個過閘。已加 test 防止有人加返。

## 檢查
- **leakage-audit**：PASS —— 配備係**賽前公告**，天生 point-in-time 安全
- **golden_scoring**：AU **120/120 一致** → 排名 bit-identical，確認配備冇入分
- **run_tests**：15 個 suite 全綠（新增 11 個 gear test）
- **退步**：冇

## 結論
1. 「Sportsbet 冇配備數據」係錯嘅 —— 數據一直喺度（85.9% Formguide 有呢一行），
   一個 token 落差食咗佢。**呢個 repo 第 N 次同一個形狀**：欄位在、code 行、
   test 綠，但值係空。
2. 修完之後**排名一格都冇郁**（golden bit-identical），因為配備由頭到尾唔入分 ——
   呢個係刻意嘅，唔係副作用。
3. `health_score` 仍然係空殼（八個 input 得兩個活），呢次只係令佢**唔會**因為
   抽取修好而靜靜變成配備評分。佢自己嘅去留仍然未決。
