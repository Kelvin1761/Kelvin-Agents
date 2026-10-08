# EXP-20261008-01 — HKJC ranking tail stability

- **日期**：2026-10-08
- **平台**：HKJC
- **狀態**：REJECT — 方向正面但 ranking evidence 太弱，零 production 改動
- **假設**：逐日大幅波動主要由少數「情境分與馬匹實力分極端分歧」的馬造成；只對極端分歧作小幅、封頂修正，可以減少 Top-5 嚴重高估／低估，而不需要重配整套 7D。
- **搜索過嘅舊記錄**：EXP-20260928-01/03/06/07-HK/08/09/10、EXP-20261007-02/04/05。
- **改到嘅組件**：research-only harness；未改 production scoring。

## Baseline

- commit：`c89a2f09e79c559de512845a22608073ac06c705`
- 語料：`build_hkjc_ranking_dataset.py` 由同一 production engine 重評的 point-in-time HKJC archive；baseline 使用 `current_live_recomputed_ability`，不使用各歷史日期留下的舊版 `rank_score` snapshot。
- 外層維度保持 production weights；初出馬保持原分。

## Locked candidate family

馬匹實力 core：`sectional + stability + class_advantage + form_line`，按 production
相對權重正規化。情境 context：`trainer_signal + race_shape + horse_health`，同樣按
production 相對權重正規化。

只在 `|core - context| > 12` 時修正：

```text
raw_delta = 0.04 × (core - context - sign(core-context) × 12)
delta = clip(raw_delta, -0.8, +0.8)
```

三個 ablation arms：

1. `over_only`：只保留負 delta，修正 context-driven 高估。
2. `under_only`：只保留正 delta，修正 core-driven 低估。
3. `symmetric`：兩邊都保留。

參數已鎖，唔做 grid search。0.8 raw point 約為現役 raw-score SD 的 0.18 倍，只應
影響接近 Top-5 邊界的馬，不應造成 wholesale rerank。

## Locked evaluation

- 日期排序；最後 15% 日期為 terminal，只開一次。
- development 同時報五個 chronological blocks；至少 3/5 Gold、Good 同時非負。
- Stage 4 primary：Gold、Good 在 development／terminal 點估計均不得回歸。
- ranking：Capture@5、Competitive Recall@5、NDCG@5。
- cohort：沙田、跑馬地分開；任何 primary 實質回歸即 REJECT。
- tail guardrails（越低越好）：
  - 實際前三跌出 model Top-5 數量；
  - 實際前三最差 model rank；
  - model Top-3 跑第 8 或更後數量；
  - model Top-5 跑第 8 或更後數量。
- meeting volatility：逐 meeting `Top-5 hits` 平均值與完整 capture rate 的 SD。
  候選即使平均 NDCG 改善，如嚴重高估／低估尾部或 meeting volatility 明顯惡化，
  仍然 REJECT。

## Leakage contract

core/context 全部來自賽前 Logic 的 production matrix。`finish_pos` 只在完成候選分數
與排名後做 evaluation join；不使用賠率、當日賽果、賽後 incident 或未來資料。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/experiments/patches/hkjc_ranking_tail_stability.py \
  --dataset /private/tmp/hkjc_ranking_dataset_20261008.csv \
  --output /private/tmp/hkjc_ranking_tail_stability_20261008.json
```

## 結果

共 340 場／4,239 匹；development 280 場，terminal 60 場。487 匹觸發，惟平均
絕對 raw 修正只有 0.0135，最大 0.5175。三個 arm 全部守住 Gold／Good，五個
development blocks 亦全部 primary 非負，但 Stage 4 一律判
`ranking_evidence_too_weak`。

最有用的 `over_only`：

| 指標 | Development | Terminal | 全樣本 |
|---|---:|---:|---:|
| Gold | 0.00pp | 0.00pp | 0.00pp |
| Good | 0.00pp | 0.00pp | 0.00pp |
| Top-3 Capture@5 | +0.24pp | 0.00pp | +0.20pp |
| Competitive Recall@5 | +0.18pp | 0.00pp | +0.15pp |
| NDCG@5 | +0.00084 | 0.00000 | +0.00069 |

全樣本每場漏出 Top-5 的實際前三少 0.0059 匹，Top-5 跑第八或更後亦少
0.0059 匹；逐 meeting Top-5 hits SD 由 0.3006 降至 0.2922，完整捕捉 SD 由
0.1665 降至 0.1630。方向符合假設，但 terminal 完全零影響，而且冇 ranking metric
達到 Stage 4 正證據門檻。

## 決定

**REJECT，不接 live。** 問題唔係修正方向錯，而係只看極端 core/context 分歧會漏掉
大部分 Top-5 邊界錯排。下一個實驗改測「鎖住現役 Top-2、只重排第 3–8 位」的
point-in-time reranker；咁可以針對一兩匹高估／低估，同時直接保護 Good／Champion。
