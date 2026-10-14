# EXP-20260928-07 — AU Matrix Top-4 constrained ML reranker

- **日期**：2026-09-28
- **平台**：AU
- **狀態**：REJECT_RETROSPECTIVE／NOT SHIPPED
- **假設**：鎖死現役 Matrix Top 4 成員集合，只用 XGBoost place probability 重排集合內次序，可以保持 canonical Gold 完全不變，同時改善 Good／Pass。
- **搜索過嘅舊記錄**：`EXP-20260821 Rating Matrix ML Re-Optimisation`、`EXP-20260831-12`、`EXP-20260928-02`；未見 constrained Top-4 reranker。
- **改到嘅組件**：research-only `au_ml_top4_rerank.py`；唔改 production scorer。

## 預先鎖定配置

- **baseline**：現役 Matrix 次序。
- **A — `top4_place`**：Matrix Top 4 成員不變；1–4 按 XGBoost `pred_place` 重排；第 5 名後保持 Matrix 次序。
- **B — `rank1_locked_place`**：Matrix 第一名不變；Matrix 第 2–4 名按 XGBoost `pred_place` 重排；第 5 名後保持 Matrix 次序。
- tie-break：原 Matrix rank，再 horse number。
- 候選 probability 保持 Matrix probability；ML 只改 `analysis_score` 排序，所以 Brier/calibration 預期完全不變。

唔試 alpha、唔試 venue rule、唔加入 WinningTime speed，避免一次改多樣。A/B 係「容唔容許
ML 郁 Matrix 第一名」嘅 nested ablation。

## 數據與選擇規則

- dataset：`/private/tmp/au_ml_20260928/au_ml_dataset.json`，2,853 場／28,216 runners。
- 固定 whole-date split：development 2,075 場（至 2026-09-08）；terminal 778 場（2026-09-09 至 09-27）。
- development：5 段 walk-forward；每段只用之前日期訓練 XGBoost。
- dev eligibility：Gold 必須數值完全不變、Good 點估計 > 0、至少 3/5 fold Good 非負。
- 多個 eligible：先揀 dev Good Δ 最大；再以 Pass Δ；仍同分揀較簡單／較安全嘅 B。
- terminal 只為 selected candidate 開一次。

## 證據限制

呢個架構係睇過 `EXP-20260928-02` terminal 嘅「Hybrid Good/Pass 升、Gold 微跌」之後先
提出，所以同一個 09-09→09-27 terminal **唔係 globally untouched**。今次即使通過只可
判 `PROMISING／PROSPECTIVE SHADOW`，唔可直接 promotion。正式上線仍需 2026-09-28
之後新完成賽事。

## 結果

樣本同 `EXP-20260928-02` 一致：2,853 場／28,216 runners；development 2,075 場，
當中 1,558 場進入五段 expanding-window 驗證；diagnostic terminal 778 場。

### Development walk-forward

| 候選 | Gold Δpp | Good Δpp | Pass Δpp | Champion Δpp | Good 非負 folds |
|---|---:|---:|---:|---:|---:|
| `top4_place` | +0.00 | +0.83 | +0.06 | +0.51 | 3/5 |
| `rank1_locked_place` | +0.00 | **+1.28** | **+0.58** | +0.00 | **4/5** |

按預註冊規則揀 `rank1_locked_place`。逐 fold Good Δ 為 +1.75、+0.48、−1.15、
+2.56、+3.13pp；唯一明顯負 fold 係 2026-08-08 至 08-18。由於第一名同 Top 4
集合都鎖死，Gold／Champion 如設計所料完全不變。

### Diagnostic terminal（2026-09-09 至 09-27）

| Gold Δpp | Good Δpp | Pass Δpp | Champion Δpp | Winner@3 Δpp |
|---:|---:|---:|---:|---:|
| **+0.00** | **+0.77** | **+1.41** | **+0.00** | −0.13 |

- Gold paired 95% CI：`[+0.00, +0.00]pp`。
- Good paired 95% CI：`[-1.41, +2.96]pp`，跨 0，未達預註冊門檻。
- 機率完全沿用 Matrix，所以 Brier／log loss／calibration 全部 bit-identical；今次只量排序。
- 場大小：細場 Good +3.79pp（132 場）、大場 +1.09pp（184 場）、中場
  −0.22pp（462 場），未見可安全概括嘅單調規則。
- going：Good/Firm +0.41pp（493 場）、Soft +1.09pp（276 場）、Synthetic
  +11.11pp（9 場）；Synthetic 樣本不可作判決。
- watch venues：Kalgoorlie +14.29pp（7 場）、Randwick −10.00pp（10 場）、
  Caulfield 0.00pp（19 場）、Ballarat Synthetic 0 場。樣本太少而且方向不一致，
  **唔建立 course override**。

## 判決

**REJECT_RETROSPECTIVE／保持現役 Matrix 次序。** 呢個 constrained 設計解決咗上一輪
Hybrid 傷 Gold 嘅問題，而且 dev／terminal Good 點估計都正，唔可以講成「ML 完全冇
訊號」；但 terminal Good CI 跨 0，而該 terminal 亦已被上一個實驗睇過，唔足以登記
production 或 prospective shadow。以目前 +0.77pp 點估計粗略外推，要約數千場獨立新
樣本先有合理機會令 CI 下界過 0，回報唔值得再開一條長期 ML shadow。

實驗零 production scoring 改動；research harness 同 regression tests 保留，方便將來有
新特徵或真正獨立大樣本時用同一把尺重跑。

## 重跑

```bash
PYTHONPATH=/private/tmp/au_ml_runtime_20260928 \
MPLCONFIGDIR=/private/tmp/matplotlib-cache PYTHONDONTWRITEBYTECODE=1 \
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_ml_top4_rerank.py \
  --dataset /private/tmp/au_ml_20260928/au_ml_dataset.json \
  --output-json /private/tmp/au_ml_top4_rerank_20260928.json \
  --output-md /private/tmp/au_ml_top4_rerank_20260928.md
```
