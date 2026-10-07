# EXP-20260928-08 — HKJC race-shape 單軸權重 profile

- **日期**：2026-09-28
- **平台**：HKJC
- **狀態**：REJECT_DEV / PARETO TRADE-OFF / TERMINAL UNOPENED
- **上游**：EXP-20260928-06/07；兩次 terminal 均未開。
- **假設**：joint refit 嘅 primary 回歸可能來自其他六維一齊郁，而非 race-shape 減權
  本身；只減 shape、其餘六維保持 production 相對比例，可以識別安全重量區間。
- **Harness**：`docs/experiments/patches/hkjc_race_shape_weight_profile.py`

## 固定設計

- 同一 320 場／3,972 runner 語料，同一最後15%日期 terminal。
- 初出馬完整鎖定；標準馬只改 outer `race_shape`。
- grid 固定 `10%, 14%, 18%, 20%, 22%, 24%, 26%`，另有現役27.37% baseline。
- 其餘六維按 production 相對比例分配 `1−race_shape`；inner shape 完全不變。
- dev 274 場按日期切5個連續 reporting blocks；無 optimizer、無 feature 搜索、無 odds。
- 候選須 aggregate dev Gold／Good不退、至少3/5 block兩者均不退、三個 ranking metric
  至少兩項正。合格時揀最接近 production（最高 race-shape weight）嗰個，唔取最高分。
- 只開一個 locked terminal；Stage-4 v2照舊。全部不合格就 `REJECT_DEV`。

## 結果

固定候選喺完整 dev 274 場結果：

| Shape | Gold Δ | Good Δ | capture@5 Δ | recall@5 Δ | NDCG@5 Δ |
|---:|---:|---:|---:|---:|---:|
| 26% | −0.365pp | −1.095pp | +0.487pp | +0.438pp | +0.139pp |
| 24% | −0.365pp | −0.730pp | +0.608pp | +0.511pp | +0.370pp |
| 22% | −0.730pp | −0.730pp | +0.730pp | +0.876pp | +0.519pp |
| 20% | −1.095pp | −0.730pp | +1.460pp | +1.259pp | +0.814pp |
| 18% | −1.460pp | +0.365pp | +1.825pp | +1.442pp | +1.235pp |
| 14% | −1.825pp | +1.095pp | +2.068pp | +1.928pp | +1.208pp |
| 10% | −1.825pp | +1.095pp | +1.217pp | +1.113pp | +0.841pp |

14% 嘅三個 ranking metric CI 全正：capture `[+0.7299,+3.5280]pp`、recall
`[+0.9244,+2.9805]pp`、NDCG `[+0.2512,+2.1652]pp`；但少 5 場 Gold，只有
1/5 reporting block 同時守住 primary。連最接近 production 嘅 26% 都少 1 Gold、3 Good。
7/7 候選 fail，terminal 未開。原始輸出：`/tmp/hkjc_race_shape_weight_profile_20260928.json`。

**判決：REJECT_DEV。** 呢條 curve 證明 shape 減權有真實 continuous-ranking 收益，但同
canonical「完整捉中頭三／頭二」形成 Pareto trade-off；唔可以將 ranking-first 結論冒充
現有 primary 改善。
