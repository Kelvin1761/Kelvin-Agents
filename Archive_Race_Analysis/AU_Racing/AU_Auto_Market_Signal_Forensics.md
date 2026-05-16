# AU Auto Market Signal Forensics

## Why This Report Exists

- 目標唔係再由大盤盲修，而係專睇 `0-hit / 1-hit` 入面市場本身已經有明顯競爭訊號嘅頭馬。
- 呢批馬理論上最值得模型睇得更清楚，因為如果連熱門或市場前列馬都經常完全睇唔到，代表訊號消化仍有實質缺口。

## Overall Low-Hit Sample

- `0-hit + 1-hit` races: **191**
- `0-hit` races: **42**
- `1-hit` races: **149**

## Market-Signal Winner Subset

- 市場訊號頭馬樣本: **125 / 191 = 65.4%**
- 其中 `0-hit`: **26**
- 其中 `1-hit`: **99**
- 頭馬仍排 model `4-6`: **40**
- 頭馬跌出 model `7+`: **29**

Interpretation: `4-6` 比較似 rerank / tightening 問題；`7+` 更似上游 feature depth 未夠。

## By Market Bucket

| Bucket | Races | Share |
|---|---:|---:|
| Favourite | 64 | 51.2% |
| Short SP<=4 | 13 | 10.4% |
| Market Top3 | 48 | 38.4% |

## Most Common Missing Signals In Market-Signal Winners

| Section | Count |
|---|---:|
| 騎練訊號低估 | 43 |
| 場地適性低估 | 29 |
| 級數與負重低估 | 28 |
| 形勢與走位低估 | 26 |
| 狀態與穩定性低估 | 24 |
| 段速與引擎低估 | 17 |
| 賽績線低估 | 12 |

## Most Common Overtrusted Signals In Failed Top Picks

| Section | Count |
|---|---:|
| 級數與負重可能過信 | 74 |
| 形勢與走位可能過信 | 65 |
| 狀態與穩定性可能過信 | 63 |
| 場地適性可能過信 | 53 |
| 賽績線可能過信 | 51 |
| 騎練訊號可能過信 | 42 |
| 段速與引擎可能過信 | 24 |

## Common Race Buckets For Market-Signal Misses

- Condition: Good/Firm 91, Soft 25, Heavy 9
- Race class: BM58-70 43, Other 34, Group 2/3 24, Group 1 10, BM72-84 6, Maiden 5, BM88+ 3
- Field size: Field 9-12 71, Field 13+ 41, Field <=8 13

## High-Value Cases To Review First

| Race | Miss | Market | Winner Rank | Winner | Main Missing Signals | Main Overtrust Signals |
|---|---|---|---:|---|---|---|
| 2026-02-14 Flemington Race 1-10 R9 | 1-hit | Favourite / $1.60 | 5 | Sixties | 級數與負重 +7.6, 狀態與穩定性 +1.3 | 騎練訊號 -16.3, 形勢與走位 -3.0 |
| 2026-04-11 Randwick Race 1-10 R6 | 1-hit | Favourite / $1.60 | 1 | Tempted | 狀態與穩定性 +3.2, 賽績線 +2.1 | 級數與負重 -5.8, 形勢與走位 -0.1 |
| 2025-11-01 Randwick Race 1-10 R8 | 1-hit | Favourite / $1.75 | 2 | Autumn Glow | 狀態與穩定性 +4.5, 騎練訊號 +2.3 | 級數與負重 -6.3 |
| 2026-03-07 Flemington Race 1-10 R3 | 1-hit | Favourite / $1.80 | 3 | Medicinal | 級數與負重 +4.6, 場地適性 +2.2 | 狀態與穩定性 -4.3, 賽績線 -2.8 |
| 2026-01-17 Flemington Race 1-10 R10 | 0-hit | Favourite / $2.05 | 4 | Sass Appeal | 場地適性 +3.1, 級數與負重 +2.2 | 狀態與穩定性 -7.0, 賽績線 -3.4 |
| 2026-04-25 Flemington Race 1-8 R3 | 1-hit | Favourite / $2.15 | 1 | Blind Raise | 騎練訊號 +4.6, 場地適性 +2.2 | 賽績線 -1.6, 形勢與走位 -1.1 |
| 2025-11-01 Flemington Race 1-9 R2 | 1-hit | Favourite / $2.20 | 1 | Sheza Alibi | 形勢與走位 +5.7, 狀態與穩定性 +5.0 | 騎練訊號 -6.8 |
| 2026-01-17 Flemington Race 1-10 R3 | 1-hit | Favourite / $2.25 | 3 | Our Chief | 形勢與走位 +3.9 | 騎練訊號 -3.5, 級數與負重 -3.1 |
| 2026-02-07 Randwick Race 1-10 R6 | 1-hit | Favourite / $2.25 | 1 | Cinsault | 狀態與穩定性 +10.2, 賽績線 +4.4 | 級數與負重 -3.3, 形勢與走位 -2.1 |
| 2026-03-07 Randwick Race 1-10 R5 | 1-hit | Favourite / $2.30 | 4 | Beadman | 騎練訊號 +5.8, 場地適性 +5.7 | 級數與負重 -8.2, 形勢與走位 -5.1 |
| 2025-08-02 Flemington Race 1-9 R6 | 1-hit | Favourite / $2.30 | 2 | Zou Sensation | 級數與負重 +2.2, 段速與引擎 +1.7 | 形勢與走位 -3.1, 場地適性 -3.0 |
| 2025-12-26 Randwick Race 1-8 R1 | 1-hit | Favourite / $2.30 | 1 | Man Of Worth | 狀態與穩定性 +4.1, 形勢與走位 +3.3 | 騎練訊號 -1.0 |
| 2026-03-07 Flemington Race 1-10 R1 | 1-hit | Favourite / $2.35 | 4 | Legacy Bound | 狀態與穩定性 +7.2, 場地適性 +4.1 | 級數與負重 -9.7, 騎練訊號 -3.2 |
| 2025-12-27 Randwick Race 1-10 R5 | 1-hit | Favourite / $2.40 | 7 | Ice Kool | 場地適性 +0.3 | 騎練訊號 -11.9, 狀態與穩定性 -8.1 |
| 2026-01-17 Flemington Race 1-10 R8 | 1-hit | Favourite / $2.40 | 3 | Saint George | 級數與負重 +7.1, 賽績線 +0.7 | 場地適性 -5.5, 形勢與走位 -2.7 |

## Working Read

- 如果市場前列頭馬多數都只係排 `4-6`，下一刀應該偏向 `rerank / place-tightening`。
- 如果市場前列頭馬經常跌出 `7+`，就唔係小修 ranking 可以解決，而係 `class / track / jockey_trainer / stability` 上游 digest 仲有漏位。
- 呢份報告應該配合 `AU_Auto_Zero_Hit_Race_Audit.md` 一齊睇：前者聚焦市場可見訊號，後者聚焦全體失手模式。
