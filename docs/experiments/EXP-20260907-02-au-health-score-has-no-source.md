# EXP-20260907-02 `health_score` 修唔到 —— 來源根本冇健康資料

- **日期**：2026-09-07
- **平台**：AU
- **假設**：`health_score` 八個 input 六個死，係抽取缺陷（同配備變更一樣），
  修好抽取就令佢有內容。**證伪。** 配備嗰個係抽取缺陷（已修，EXP-20260907-01），
  其餘全部係**上游冇數據**。
- **搜索過嘅舊記錄**：EXP-20260907-01、EXP-20260905-04、
  `docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`、
  memory `au-trial-video-comments-do-not-exist`、`scraper-silent-drop-failure-mode`
- **改到嘅檔案**：`au_racing_engine/engine_core.py`（`_health_score`、
  `_has_last10_warning` 註釋、剷走 orphan `_latest_official_text`）、
  `tests/test_gear_change_display.py`

## 一、實測：分數只有三個值，全部嚟自「距上仗日數」

跑真 `_health_score`，8,224 匹（2026-08-13→09-04）：

| 分數 | n | 來源分支 |
|---:|---:|---|
| 61.0 | 4,656 | 距上仗 14–45 日 → **+1.0** |
| 60.0 | 2,519 | 唔中任何分支 |
| 59.0 | 1,049 | 久休 >90 日 → **−1.0** |

**冇一個健康分支中過**（0 次）。個名同標籤講「健康」，實質係「距上仗日數」換個名。

⚠️ 量度陷阱：我第一次跑得出 **8,224 匹全部 60.0、零分支**，因為 harness 冇餵
meeting date，`_spell_days()` 回 0。`ab-identical-means-unwired` 套用喺自己身上 ——
**「全部一樣」先查 wiring**。餵咗日期之後即刻對得上語料嘅 59/60/61。

## 二、為咩修唔到：逐個 input 查來源

| input | 狀況 | 證據 |
|---|---|---|
| `Stewards:` / `Note:` / `Video:` | **0.0% 有內容** | 各 **21,127 行**，逐行核實，全部只有標籤冇內文 |
| `warning_line` | key **由來唔存在** | `_data` 8,224 匹 0% |
| 獸醫字眼掃描 | **100% 假陽性** | 全部係馬名／父母名：`Heart Of Vienna`、`Heartoni`、`Vetoed`、母系 `Cardiac`、`Lamerican`；真記錄 **0** 條 |
| `timing_trial_600m_avg_speed` | 100% key、**0% 有值** | Formguide **5,513 條試閘行冇一條**有 L600/RT 數字 |
| `gear_line` | ✅ 已修（0%→22.3%） | EXP-20260907-01 —— 但配備**唔准入分**（EXP-20260826-07 REJECT） |

⚠️ 我第一次量 `Stewards:` 用 `^Stewards:\s*(.*)$` 得出「100% 有內容」——
`(.*)` 會 match 空字串。逐行核實之後係 **0.0%**。
**唔好用會 match 空嘅 regex 去量覆蓋率。**

## 三、順手拆一個地雷
舊 `warning_text` 係 `warning_line + gear_line + _latest_official_text()` 拼埋，
再做 **substring** 獸醫 token 掃描。而配備抽取啱啱由 0% 修到 **22.3%**（590 種
唔同文字）。今日冇一個撞到 token（2,351 匹實測乾淨，golden 亦 bit-identical），
但 `vet` / `heart` / `lame` 做 substring 對住活數據 = 將來一個配備名就靜靜扣
1.5–2.0 分。已加 test（`Velvet Nose Roll`、`Heart Monitor`、`Lame Duck Bit`）。

## 四、改咗啲咩
剷走三個警告／獸醫分支 + 「久休但有試閘時間」rescue（`else` 分支永遠中，
所以保留 −1.0 = 行為不變）；`note` 同 source tag 由 `warnings+spell` 改
`spell_only`、文字改「出賽間隔分」。剷走 orphan `_latest_official_text()`（0 caller）。

**零分數變化** —— 全部被剷嘅分支由來冇 fire 過。

## 五、未處理（獨立一個改動）
`_has_last10_warning()` 仲有第二個 caller：`_confidence_score` 嘅 **−4**。
同一個死欄位、同樣永遠唔 fire。冇喺呢個改動一齊做，因為佢屬另一個 leaf，
要自己一份 golden 對照。已喺 code 註釋標明。

## 檢查
- **leakage-audit**：PASS（只用賽前欄位）
- **golden_scoring**：AU **120/120 一致**（`health_score` 本身零排名權重，
  而被剷嘅分支由來冇 fire）
- **run_tests**：15 個 suite 全綠（新增 5 個 health test，共 15 個 gear/health test）
- **退步**：冇

## 結論
1. **`health_score` 做唔到一個真嘅健康分 —— 因為 Sportsbet 唔出健康資料**，
   唔係我哋解析失敗。想有健康分，前提係**先有來源**（stewards report、
   vet scratching 公告等），唔係改公式。
2. 而家佢誠實咁只講「出賽間隔」，同埋唔再收埋一個 substring 地雷。
3. 「六個 input 死」呢句要拆開睇：**一個係抽取缺陷（配備，已修）、
   五個係上游冇數據。** 混住講會令人以為再挖抽取層會有收穫。
