# EXP-20260907-04 `早段步速` 修唔到（PF payload 換咗）＋ 一條 `\s*` 食換行嘅污染路

- **日期**：2026-09-07
- **平台**：AU
- **假設**：Facts `早段步速` 欄 0% 有值係抽取缺陷，可以同配備變更一樣修好。
  **一半證伪** —— 呢個欄修唔到（來源冇咗），但沿路揸到另一個**真**嘅抽取 bug。
- **搜索過嘅舊記錄**：EXP-20260907-01/02/03、memory `pf-token-silently-vanished`、
  `au-race-level-l600-outweighs-own-sectional`、`scraper-silent-drop-failure-mode`
- **改到嘅檔案**：`.agents/scripts/inject_fact_anchors.py`（3 條 regex + 兩段註釋）、
  `au_racing_engine/engine_core.py`（剷 `early_pace`）、`tests/test_gear_change_display.py`

## 一、`早段步速` 修唔到：PF payload 整個換咗
`PF[...]` 容器仍然存在（**56,384 個區塊**），但內容喺 Racenet→Sportsbet 搬遷後換咗：

```
舊（PuntingForm）Last 600: … Runner Time: … Early Runner Pace: … RT Rating: …
新（Sportsbet）  Source: sportsbet_race_context L600 Delta: 1.76
```

新 payload **只有兩個 key**（`Source`、`L600 Delta`）。所以 `inject_fact_anchors`
嗰六條 regex 命中率**全部 0.0%**，連帶兩條 Facts 欄永遠空：

| Facts 欄 | 有值 | 成因 |
|---|---:|---|
| `早段步速` | **0.0%**（73,452 行） | `Early Runner Pace` 新 payload 冇 |
| `L600/RT` | **0.0%** | `Last 600` / `RT Rating` 新 payload 冇 |

✅ **但 L600 資訊冇丟。** 佢經另一條路：`backfill_pf_metrics()` 喺 runtime 由 Facts
讀 `L600 Delta` 砌 `pf_aggregates`，實測 **555/579 匹（95.9%）** 有
`l600_delta_avg` / `own_l600_delta_avg`，`pace_figure` 正常食到。

⚠️ 我一度報「`pf_metrics` 100% 空」—— 錯，我量緊**存檔嘅 Logic**，而佢係 runtime
backfill 嘅。**今日第三次中同一個陷阱**（[[ab-identical-means-unwired]] 嘅變體）。

**唔好「修」嗰六條 regex** —— 唔係 pattern 錯，係欄位冇咗。亦唔好用 `L600 Delta`
填 `L600/RT`：Delta 係場級差值，舊嗰個係逐駒絕對值，混埋就係
`au-race-level-l600-outweighs-own-sectional` 警告嗰種混淆。

另外 `early_pace`（`cols[12]`）**零 consumer** —— 全 repo 冇一處讀過，已剷；
欄位本身留住（下游位置解析）。`latest_early_runner_pace` 永遠 `null`，
只有 `au_ml_dataset` 讀佢做一個永遠 null 嘅 ML 特徵。

## 二、真 bug：`\s*` 食換行，令空欄位捕捉下一行
```python
re.search(r'^Video:\s*(.+?)$', race_block, re.MULTILINE)   # ← \s 包括 \n
```
Sportsbet `Video:` / `Note:` / `Stewards:` 三個欄實測 **21,127 行 0.0% 有內容**，
所以空欄位跳落下一行：

| 欄位 | 舊 regex 捕捉到 | 次數（915 block 樣本） |
|---|---|---:|
| `Video` | `'Note:'` | 188 |
| `Note` | `'Stewards:'` | 188 |
| `Stewards` | `'========================'` | 70 |
| `Stewards` | `'Belmont **(TRIAL)** R10 '` ← **下一場賽事標題** | 2+ |

**呢個就係 Facts「備註」欄 73,452 行 100% 都係 `Note:; Stewards:` 嘅成因** ——
一個常數扮成「100% 有數據」，會騙過任何覆蓋率審計（我今日就中過一次）。

而且係一條**活**路：`entry['stewards']` 餵入走位／跑法 token 掃描
（engine_core 7088 / 7109，掃 `" led"` / `"rails"` / `"Widest"` / `"WNC"` 等）。

修法：`\s*` → `[^\S\n]*`（只食同一行嘅空白）。
**實測 73,452 個 block：修前修後冇一個 token 命中狀態改變** → 行為不變，
但條污染路封咗。新增 5 個測試釘死。

## 檢查
- **leakage-audit**：PASS（只用賽前欄位）
- **golden_scoring**：AU **120/120 一致**
- **run_tests**：15 個 suite 全綠（gear/health/regex 共 20 個新測試）
- **退步**：冇

## 結論
1. **`早段步速` 冇得救** —— 唔係 parser 錯，係上游欄位喺搬遷時冇咗，而且冇對應
   替代品。同配備變更（regex 落差，已修）唔同類，要分開講。
2. **沿路揸到一個真 bug**：`\s*` 跨行捕捉，令三個空欄位互相偷值、甚至偷下一場
   賽事嘅標題。行為上今日冇後果，但係一條會咬人嘅路。
3. **今日第四個同一形狀嘅缺陷**：欄位在、code 行、test 綠，但值係常數或者空。
   四個之中兩個係 regex（`^Gear:`、`\s*`）、一個係 payload 換咗、一個係硬寫死
   （`[需判定]`）。
4. 量度紀律新增一條：**「100% 有值」同「0% 有值」一樣可疑** —— 要睇個值係咪常數。
