# AU Component Simplification Benchmark（港式中文）

目的：驗證 `confidence_score` 退出 ranking、`readiness_score` 重建、以及 `jockey_horse_fit_score` 拆件後，喺 archive 同 `2026-05-30` 三個 meetings 是否有改善。

## Stored Baseline

### Archive

## Archive stored python_auto

- Races: `316`
- Champion: `24.4%`
- Gold: `4.1%`
- Good: `20.9%`
- Pass: `38.9%`
- Top3 Place: `42.6%`
- 0-hit: `48`
- 1-hit: `145`

### 2026-05-30 三場合併

## 05-30 stored python_auto

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `14.3%`
- Pass: `21.4%`
- Top3 Place: `32.1%`
- 0-hit: `8`
- 1-hit: `14`

## Variant: 建議主線

移除 confidence ranking 作用，並將 health_score 重命名為 readiness_score，但 default 保持中性 placeholder。

### Archive

## 建議主線 / Archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `35.4%`
- Top3 Place: `41.1%`
- 0-hit: `50`
- 1-hit: `154`
- 對 stored baseline: gold `-0.3`, good `-3.5`, pass `-3.5`, place `-1.5`, 0-hit `+2`, 1-hit `+9`

### 2026-05-30 三場合併

## 建議主線 / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- 對 stored baseline: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`

## Variant: 實驗版 readiness 入分

將實驗版 readiness_score 正式入分，檢查會唔會比中性 placeholder 更好。

### Archive

## 實驗版 readiness 入分 / Archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `34.8%`
- Top3 Place: `40.9%`
- 0-hit: `50`
- 1-hit: `156`
- 對 stored baseline: gold `-0.3`, good `-3.5`, pass `-4.1`, place `-1.7`, 0-hit `+2`, 1-hit `+11`
- 對新主線: gold `+0.0`, good `+0.0`, pass `-0.6`, place `-0.2`, 0-hit `+0`, 1-hit `+2`

### 2026-05-30 三場合併

## 實驗版 readiness 入分 / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- 對 stored baseline: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`
- 對新主線: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## Variant: 建議主線 + 關閉 named DB

喺建議主線基礎上，停用大場 named jockey/trainer ratings。

### Archive

## 建議主線 + 關閉 named DB / Archive

- Races: `316`
- Champion: `20.6%`
- Gold: `4.4%`
- Good: `17.7%`
- Pass: `35.8%`
- Top3 Place: `41.2%`
- 0-hit: `52`
- 1-hit: `151`
- 對 stored baseline: gold `+0.3`, good `-3.2`, pass `-3.2`, place `-1.4`, 0-hit `+4`, 1-hit `+6`
- 對新主線: gold `+0.6`, good `+0.3`, pass `+0.3`, place `+0.1`, 0-hit `+2`, 1-hit `-3`

### 2026-05-30 三場合併

## 建議主線 + 關閉 named DB / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `14.3%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- 對 stored baseline: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`
- 對新主線: gold `+0.0`, good `-3.6`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## Variant: 建議主線 + 關閉 readiness

保留建議主線其他改動，但 track matrix 只用 track_score。

### Archive

## 建議主線 + 關閉 readiness / Archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.7%`
- Pass: `34.8%`
- Top3 Place: `41.0%`
- 0-hit: `49`
- 1-hit: `157`
- 對 stored baseline: gold `-0.3`, good `-3.2`, pass `-4.1`, place `-1.6`, 0-hit `+1`, 1-hit `+12`
- 對新主線: gold `+0.0`, good `+0.3`, pass `-0.6`, place `-0.1`, 0-hit `-1`, 1-hit `+3`

### 2026-05-30 三場合併

## 建議主線 + 關閉 readiness / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `32.1%`
- 0-hit: `8`
- 1-hit: `14`
- 對 stored baseline: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`
- 對新主線: gold `+0.0`, good `+0.0`, pass `+0.0`, place `-1.2`, 0-hit `+1`, 1-hit `-1`

## Variant: 建議主線 + 移除 combo 組件

人馬配搭只保留 familiarity + signals，移除場館騎練 combo / trainer-track component。

### Archive

## 建議主線 + 移除 combo 組件 / Archive

- Races: `316`
- Champion: `19.6%`
- Gold: `3.5%`
- Good: `17.1%`
- Pass: `34.5%`
- Top3 Place: `40.7%`
- 0-hit: `50`
- 1-hit: `157`
- 對 stored baseline: gold `-0.6`, good `-3.8`, pass `-4.4`, place `-1.9`, 0-hit `+2`, 1-hit `+12`
- 對新主線: gold `-0.3`, good `-0.3`, pass `-0.9`, place `-0.4`, 0-hit `+0`, 1-hit `+3`

### 2026-05-30 三場合併

## 建議主線 + 移除 combo 組件 / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- 對 stored baseline: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`
- 對新主線: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## Variant: 建議主線 + 移除 signals 組件

人馬配搭只保留 familiarity + combo，移除換騎訊號 / stage / apprentice component。

### Archive

## 建議主線 + 移除 signals 組件 / Archive

- Races: `316`
- Champion: `21.5%`
- Gold: `3.5%`
- Good: `19.3%`
- Pass: `35.4%`
- Top3 Place: `40.9%`
- 0-hit: `51`
- 1-hit: `153`
- 對 stored baseline: gold `-0.6`, good `-1.6`, pass `-3.5`, place `-1.7`, 0-hit `+3`, 1-hit `+8`
- 對新主線: gold `-0.3`, good `+1.9`, pass `+0.0`, place `-0.2`, 0-hit `+1`, 1-hit `-1`

### 2026-05-30 三場合併

## 建議主線 + 移除 signals 組件 / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `10.7%`
- Pass: `25.0%`
- Top3 Place: `34.5%`
- 0-hit: `7`
- 1-hit: `14`
- 對 stored baseline: gold `+0.0`, good `-3.6`, pass `+3.6`, place `+2.4`, 0-hit `-1`, 1-hit `+0`
- 對新主線: gold `+0.0`, good `-7.1`, pass `+3.6`, place `+1.2`, 0-hit `+0`, 1-hit `-1`

## Variant: 建議主線 + 只留 familiarity

人馬配搭只保留 horse-jockey familiarity / trial continuity / best-rider history core。

### Archive

## 建議主線 + 只留 familiarity / Archive

- Races: `316`
- Champion: `20.3%`
- Gold: `3.5%`
- Good: `17.4%`
- Pass: `33.2%`
- Top3 Place: `40.1%`
- 0-hit: `52`
- 1-hit: `159`
- 對 stored baseline: gold `-0.6`, good `-3.5`, pass `-5.7`, place `-2.5`, 0-hit `+4`, 1-hit `+14`
- 對新主線: gold `-0.3`, good `+0.0`, pass `-2.2`, place `-1.1`, 0-hit `+2`, 1-hit `+5`

### 2026-05-30 三場合併

## 建議主線 + 只留 familiarity / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `10.7%`
- Pass: `25.0%`
- Top3 Place: `34.5%`
- 0-hit: `7`
- 1-hit: `14`
- 對 stored baseline: gold `+0.0`, good `-3.6`, pass `+3.6`, place `+2.4`, 0-hit `-1`, 1-hit `+0`
- 對新主線: gold `+0.0`, good `-7.1`, pass `+3.6`, place `+1.2`, 0-hit `+0`, 1-hit `-1`

## 初步閱讀框架

- `new_mainline` 代表你而家要求嘅核心結構修正有冇整體提升。
- `experimental_readiness_live` 用嚟驗證實驗版 readiness 真係幫到手，定只會增加 noise。
- `readiness_off` 用嚟驗證中性 readiness placeholder 有冇存在價值；如果關掉後更好，代表 track matrix 可再簡化。
- `jt_no_combo` / `jt_no_signals` / `jt_core_only` 用嚟答『人馬配搭邊一層真係值得留』。
- `new_mainline_no_named_db` 用嚟答『named jockey/trainer DB 係咪值得為咗少量 edge 保留複雜度』。

## 結論

- `confidence_score` 可正式退出 ranking。主線已改成只保留 `coverage_score` metadata，用嚟提示證據鏈完整度，唔再當成贏面 signal。
- `health_score` 唔應再叫健康分。現階段主線已改名為 `readiness_score`，但 default 保持中性 placeholder；測試唔支持將實驗版 readiness 直接入分。
- `readiness_score` 以中性 placeholder 留喺 `track` matrix 比完全關掉略好，所以現階段保留 schema、唔保留進取 scoring。
- `jockey_horse_fit_score` 入面嘅 `combo` 組件唔應刪，移除後 archive 明顯變差。
- `signals` 組件有 mixed 訊號。佢對 `05-30` pass/place 有幫助，但 archive 唔夠乾淨支持直接全刪；現階段只建議保留拆件結構，之後再做降權測試。
- `core familiarity` 唔足夠單獨撐起整條 fit score，所以唔應將人馬配搭簡化成只剩 jockey/trainer 基礎分。
- `named DB` 關閉後整體只屬輕微 mixed 變化，簡化價值高過證據強度；若優先考慮 maintainability，可視作下一個可考慮移除嘅候選，但暫未屬於「一定要即刻刪」。
