# AU performance-quality matrix upgrade — 2026-08-09

## Direction

按用戶指示，今次冇做 Top-2 lock、slot 3/4 rerank 或 shortlist micro-adjustment。
改動直接落喺 scoring matrix：提升模型辨識馬匹「喺幾強賽事、輸幾多」嘅能力。
Gold／Good 優先；Pass 維持「模型 Top 3 任兩匹上名」。任何賠率都冇入分。

## Data alignment finding

研究用 `scratch/au_prize_cache_build.py` 原本只掃 AU data root 即時子目錄，completed
meeting 移入 `Archive/` 後就全部漏讀。舊 cache 因此表面正常、實際停止喺 7 月 12 日。
修正為 recursive Formguide discovery 後：

- meetings：87 → 121；
- races：762 → 1,042；
- horse blocks：8,431 → 11,537；
- margin coverage：11,073 → 27,380 formal runs；
- starters coverage：1,549 → 15,963 formal runs。

另外做咗 point-in-time leakage audit：archived scratch field-test 曾見同日結果，但 805 場
matching evaluation records 加上 `run_date < meeting_date` 截斷後，分數與排名完全一致，
證明今次 production evidence 冇食目標場結果。同日／未來截斷已永久寫入 parser，並有
regression test。

## Simple structural feature

`stability` 保持兩個成分，冇增加第三層模型：

```text
stability = 0.60 × form_score + 0.40 × performance_quality_score
```

每場歷史 run：

```text
quality = -min(20, abs(beaten_margin)) + 4 × log10(prize / 50000)
```

再取最近最多四場，recency weights `1.0 / 0.8 / 0.6 / 0.4`，最後轉成同場
`60 + 20 × z-score`（clip 1–99）。`4` 係 3–5 穩定 plateau 中點，唔係單點 argmax。

證據閘：

- 每匹最少兩場正式賽；
- 每場必須同時有 margin、prize、starters；
- 同場最少三匹有完整 raw quality；
- 不完整／legacy schema 逐匹完全沿用舊 `consistency_score`；
- 無日期 hard-code，gate 只睇資料完整性同 point-in-time 合法性。

舊 consistency 仍保留做 report-only fallback，唔再同新 quality 一齊疊加投票。
`WC_DISABLE_AU_PERFORMANCE_QUALITY=1` 可令新 leaf 逐匹 rank-exact fallback，供未來
meeting 做 forward A/B 或即時 rollback。

## True-engine result

完整 1,042 Logic discovery／805 aligned races／8,249 runners；對照係 identity-corrected
舊 production，候選係真正 `RacingEngine` 重跑。

| Metric | Old | New | Delta |
|---|---:|---:|---:|
| Gold（實際前三全入模型 Top 4） | 16.15% | **17.02%** | **+0.87pp** |
| Good（模型 Top 1+2 都上名） | 24.84% | **25.71%** | **+0.87pp** |
| Pass（模型 Top 3 任兩匹上名） | 45.84% | **47.20%** | **+1.37pp** |
| Champion | 25.47% | 25.22% | -0.25pp |
| Winner@3 | 55.28% | **56.27%** | +0.99pp |
| Winner@5 | 74.53% | **75.53%** | +0.99pp |
| Top-3 precision | 46.92% | **47.70%** | +0.79pp |
| Top-5 AUC | 0.6864 | **0.6928** | **+0.00636** |

全樣本 paired-race bootstrap CI：**[+0.00296, +0.00982]**。

完整日期 dev／terminal holdout：

- dev 594 races：rank-identical，AUC delta 0；
- terminal holdout 211 races：AUC **0.6769 → 0.7012**，delta +0.02432，
  CI **[+0.01234, +0.03674]**。

## Current-schema audit

完整證據 gate 自然啟動喺 2026-08-01／05／06／07，共 119 races；唔係日期 hard-code。

| Metric | Old | New | Delta |
|---|---:|---:|---:|
| Gold | 18.49% | **24.37%** | **+5.88pp** |
| Good | 24.37% | **30.25%** | **+5.88pp** |
| Pass | 45.38% | **54.62%** | **+9.24pp** |
| Champion | 22.69% | 21.01% | -1.68pp |
| Winner@3 | 52.10% | **58.82%** | +6.72pp |
| Winner@5 | 70.59% | **77.31%** | +6.72pp |
| Top-3 precision | 47.62% | **52.94%** | +5.32pp |
| Top-5 AUC | 0.6842 | **0.7274** | **+0.04326** |

Current-schema bootstrap CI：**[+0.02231, +0.06395]**。

逐日：8/1 完全不變；8/5、8/6、8/7 AUC delta 分別 +0.0487／+0.0403／+0.0610，
三日 CI 下界都大過 0。888 匹分數改變、96 場排名改變；冇 observed quality evidence
嘅 races 排名改變數係 **0**。

## Simplification and risk

呢次唔係加 reranker，而係用一個更直接、連續、class-aware 能力訊號取代 stability 入面
較離散嘅 consistency vote。Fallback 保留舊行為，因此 rollout 對 legacy／薄料場次係
零風險。限制係完整現役 schema 只有四個日期；雖然三個獨立日期全勝、第四個中性，
仍要用未來 meetings 做 forward monitoring。Champion 喺 current-schema cohort -1.68pp，
但用戶指定 Gold／Good 為最高優先，而且 Winner@3／Winner@5 同時明顯上升，所以接受。

## Verification

- production true-engine materialization：805 races／8,249 runners；
- performance-quality + signal-map focused tests：21 passed；
- AU auto + AU daily + shared + scripts tests：438 passed；
- fallback-only rank changes：0；
- no odds input；same-day/future run censor locked by tests。
