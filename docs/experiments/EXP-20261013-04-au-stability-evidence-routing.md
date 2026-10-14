# EXP-20261013-04 — Stability 按實際證據分配 FORM/PQ

## 預先登記（未讀本輪 routing 候選結果）

日期2026-10-13，AU。用戶要求合理配比而唔鎖60/40。EXP-03 固定全局六格及
來源／情境候選已完成，唔再調救佢哋；本輪係獨立「缺少其中一類證據」假設。

資料診斷發現：完整PQ但FORM無任何可用名次 rows 1,726匹，舊表存 `- (-輸距L)`
而缺終點名次；仍有 dated margin／prize／starters 提供完整PQ。呢個唔係同一
FORM/PQ證據配置，全局配比可能混合了不同來源regime。現行FORM可能仍有獎金
調整，所以 routing 有丟訊號風險，必須量成功場被破壞。

Baseline 同 EXP-03 frozen current snapshot、1,762 dev、08-05至09-21。原terminal
保持關閉，不另切新holdout。只測以下三項，係數／其他維度／overlay不動：

- **D1**：只有 FORM 明細 rows 為空且 source 明確完整PQ時，FORM:PQ=0:100；
  否則沿用60:40。檢查有效PQ是否被空FORM稀釋。
- **D2**：只有 FORM有可用rows且PQ source=consistency_fallback時，FORM:PQ=100:0；
  否則沿用60:40。檢查是否不應把代理consistency當作另一份獨立PQ。
- **D12**：上述兩條合併，來源互斥；分別對D1／D2報邊際，不能因組合贏救獨立失敗。

不重建缺失名次、唔用輸距假裝名次、唔加賠率、唔把所有unknown自動扣分。
來源及rows是在賽前評分完成前已知，actual_pos只作評估。

Canonical primary/ranking metrics、paired race bootstrap2000 seed7、同一五個
日期folds、field-size／source cohorts照EXP-03。任何dev primary回歸＝DEV_REJECT。
即使過dev都不能部署，已曝光dev不冒認獨立驗證。

## 結果

| 候選 | dev Gold Δ | dev Good Δ | 改分馬匹 | 救失手／壞成功 | 無primary回歸folds |
|---|---:|---:|---:|---:|---:|
| D1 | −0.3973pp | −0.1703pp | 1,725 | 7／11 | 3/5 |
| D2 | +0.0568pp | −0.0568pp | 658 | 4／1 | 3/5 |
| D12 | −0.3405pp | −0.2270pp | 2,383 | 11／12 | 2/5 |

**全部DEV_REJECT。** D1丟掉FORM尚有嘅獎金／context調整；D2丟掉consistency
可能包含嘅額外歷史訊號，並非只是去掉重複資料。以上為機制推斷，退步本身係
實測。組合沒有救回獨立候選，不把理論上乾淨當成保留理由。

來源分層的重要發現：FORM缺可用名次而有完整PQ，頭兩段26%左右、其餘三段
接近0。D1最後三段近乎不觸發，唔可以把佢嘅零差當成泛化成功。

Terminal未開；無live模型、配比、golden、基準改動。只讀同一135MB frozen
dev snapshot，source PIT限制同EXP-03；候選沒有賠率或target outcome入分。

**決定**：REJECT RANKING ROUTES／保留診斷紀錄；未commit、冇push／deploy。
所有失敗候選只有research scorer，production engine唔含新routing邏輯。

## 重跑及產物

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python \
  docs/experiments/patches/au_stability_redesign.py --routing \
  --snapshot scratch/au_stability_redesign_20261013/snapshot.json \
  --out scratch/au_stability_redesign_20261013
```

原始JSON：`scratch/au_stability_redesign_20261013/routing_results.json`，包含paired
CI、五個日期fold、D12相對D1／D2邊際；same snapshot SHA256
`3782d6f6e3cb60c2ed870f07959818c0e660d697ef0d08678e3630081a19cf37`。
[完整審視](../audits/au-race-weight-oracle-20261013/STABILITY_DESIGN_REVIEW.md)。
十項研究tests、quick及完整repo gate全過。
