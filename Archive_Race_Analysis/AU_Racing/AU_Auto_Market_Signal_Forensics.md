# AU Auto Market Signal Forensics

## Why This Report Exists

- 目標唔係再由大盤盲修，而係專睇 `0-hit / 1-hit` 入面市場本身已經有明顯競爭訊號嘅頭馬。
- 呢批馬理論上最值得模型睇得更清楚，因為如果連熱門或市場前列馬都經常完全睇唔到，代表訊號消化仍有實質缺口。

## Overall Low-Hit Sample

- `0-hit + 1-hit` races: **22**
- `0-hit` races: **5**
- `1-hit` races: **17**

## Market-Signal Winner Subset

- 市場訊號頭馬樣本: **16 / 22 = 72.7%**
- 其中 `0-hit`: **4**
- 其中 `1-hit`: **12**
- 頭馬仍排 model `4-6`: **5**
- 頭馬跌出 model `7+`: **5**

Interpretation: `4-6` 比較似 rerank / tightening 問題；`7+` 更似上游 feature depth 未夠。

## By Market Bucket

| Bucket | Races | Share |
|---|---:|---:|
| Favourite | 10 | 62.5% |
| Short SP<=4 | 0 | 0.0% |
| Market Top3 | 6 | 37.5% |

## Most Common Missing Signals In Market-Signal Winners

| Section | Count |
|---|---:|
| 狀態與穩定性低估 | 8 |
| 場地適性低估 | 5 |
| 賽績線低估 | 4 |
| 級數與負重低估 | 4 |
| 騎練訊號低估 | 3 |
| 形勢與走位低估 | 2 |
| 段速與引擎低估 | 1 |

## Most Common Overtrusted Signals In Failed Top Picks

| Section | Count |
|---|---:|
| 級數與負重可能過信 | 9 |
| 形勢與走位可能過信 | 8 |
| 騎練訊號可能過信 | 7 |
| 狀態與穩定性可能過信 | 6 |
| 場地適性可能過信 | 6 |
| 賽績線可能過信 | 5 |
| 段速與引擎可能過信 | 4 |

## Common Race Buckets For Market-Signal Misses

- Condition: Good/Firm 9, Soft 4, Heavy 3
- Race class: BM58-70 7, Other 6, BM72-84 1, Group 2/3 1, Maiden 1
- Field size: Field 9-12 7, Field 13+ 6, Field <=8 3

## High-Value Cases To Review First

| Race | Miss | Market | Winner Rank | Winner | Main Missing Signals | Main Overtrust Signals |
|---|---|---|---:|---|---|---|
| 2025-12-26 Randwick Race 1-8 R1 | 1-hit | Favourite / $2.30 | 1 | Man Of Worth | 狀態與穩定性 +3.7, 形勢與走位 +3.3 | 騎練訊號 -1.0 |
| 2026-03-07 Flemington Race 1-10 R1 | 1-hit | Favourite / $2.35 | 4 | Legacy Bound | 狀態與穩定性 +7.1, 場地適性 +4.1 | 級數與負重 -9.7, 騎練訊號 -3.2 |
| 2026-02-14 Randwick Race 1-10 R1 | 1-hit | Favourite / $2.90 | 9 | Warrior For Peace | 騎練訊號 +0.5 | 狀態與穩定性 -18.2, 賽績線 -7.5 |
| 2026-04-25 Randwick Race 1-8 R8 | 0-hit | Favourite / $3.00 | 8 | Nobler | 賽績線 +5.4, 狀態與穩定性 +1.3 | 級數與負重 -9.1, 騎練訊號 -4.1 |
| 2025-08-23 Randwick Race 1-10 R1 | 1-hit | Favourite / $3.00 | 1 | Signor Tortoni | 場地適性 +6.9, 騎練訊號 +6.6 | 級數與負重 -8.6, 段速與引擎 -0.8 |
| 2026-04-18 Randwick R10 | 1-hit | Favourite / $3.30 | 1 | Captain Furai | 場地適性 +7.8, 狀態與穩定性 +5.1 | 騎練訊號 -5.2, 賽績線 -3.5 |
| 2025-11-01 Randwick Race 1-10 R1 | 1-hit | Favourite / $3.70 | 2 | Rotagilla | 場地適性 +5.3, 級數與負重 +5.1 | 段速與引擎 -3.1, 形勢與走位 -1.6 |
| 2026-02-28 Randwick Race 1-10 R1 | 0-hit | Favourite / $3.90 | 7 | Bryant | 段速與引擎 +4.5, 狀態與穩定性 +2.5 | 形勢與走位 -5.7, 騎練訊號 -4.2 |
| 2026-03-28 Flemington R10 | 1-hit | Favourite / $3.90 | 4 | Al Duca | 狀態與穩定性 +2.5, 場地適性 +1.3 | 級數與負重 -8.6, 段速與引擎 -3.4 |
| 2025-11-04 Randwick Race 1-10 R7 | 1-hit | Favourite / $5.00 | 5 | Osipenko | 場地適性 +2.6 | 級數與負重 -21.1, 狀態與穩定性 -5.0 |
| 2026-03-07 Randwick Race 1-10 R1 | 1-hit | Market Top3 / $4.20 | 11 | Zenmaster | - | 狀態與穩定性 -8.4, 級數與負重 -7.1 |
| 2025-12-31 Flemington Race 1-8 R1 | 0-hit | Market Top3 / $4.40 | 9 | Somewhere | 級數與負重 +6.6 | 狀態與穩定性 -10.7, 賽績線 -5.4 |
| 2025-11-06 Flemington Race 1-9 R1 | 1-hit | Market Top3 / $4.80 | 1 | First Chorus | 騎練訊號 +4.5, 狀態與穩定性 +3.3 | 形勢與走位 -6.2, 場地適性 -3.0 |
| 2025-11-04 Flemington Race 1-10 R1 | 1-hit | Market Top3 / $5.00 | 2 | Tornado Valley | 賽績線 +5.0, 狀態與穩定性 +2.6 | 級數與負重 -0.9 |
| 2025-11-08 Flemington Race 1-9 R1 | 1-hit | Market Top3 / $5.50 | 5 | Calamari Ring | 騎練訊號 +0.8 | 賽績線 -15.0, 狀態與穩定性 -10.9 |

## Working Read

- 如果市場前列頭馬多數都只係排 `4-6`，下一刀應該偏向 `rerank / place-tightening`。
- 如果市場前列頭馬經常跌出 `7+`，就唔係小修 ranking 可以解決，而係 `class / track / jockey_trainer / stability` 上游 digest 仲有漏位。
- 呢份報告應該配合 `AU_Auto_Zero_Hit_Race_Audit.md` 一齊睇：前者聚焦市場可見訊號，後者聚焦全體失手模式。
