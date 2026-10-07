# EXP-20261007-05 — HKJC Distance Suitability V2

Status: **KEEP AS PROSPECTIVE SHADOW／LIVE PROMOTION REJECT**。

## 假設

V1 只問「同程有冇上名」，仍會將一匹任何路程都跑得好嘅強馬當成路程專家。
V2 改成同一匹馬內部比較：

`目標路程表現後驗 − 同場地所有路程表現後驗`

因此整體能力先被扣走，路程適性唔再混入 class 或重複計算一般入位能力。

## 預先設計

Harness：`docs/experiments/patches/hkjc_distance_suitability_v2.py`

- 同 EXP-20261007-04 語料：331 場／33 日，2026-04-12 至 2026-10-04；
- development 281 場；最後 15% 日期 50 場已曾經開過，因此今次只列為
  **non-decision diagnostic**，唔准用嚟揀參數；
- 逐仗資料只取今場之前；leakage audit：未來／同日 rows = **0**；
- 365 日半衰、最多 1095 日、4 場中性收縮；
- 冇目標路程證據嚴格回 60，唔可以因為「只跑過其他路程」而扣分；
- ablation：exact / ±100m / ±200m、名次 utility、頭馬距離 utility、blend；
- 權重 2/4/6/8%、cap 4/6/8/10；
- 跑馬地草地、沙田草地、沙田 AWT 分開 fit。

## Development walk-forward（161 場驗證）

最終 development fit：

| Surface | Candidate profile |
|---|---|
| 跑馬地草地 | exact blend，8%，cap 6 |
| 沙田草地 | exact blend，2%，cap 4 |
| 沙田 AWT | exact blend，8%，cap 4；但 dev 只有 8 場且 archived Facts 無可靠 AWT target coverage |

Aggregate：

| 指標 | Baseline | V2 | Delta |
|---|---:|---:|---:|
| Gold | 8.70% | 9.32% | +0.62pp |
| Good | 13.66% | 14.29% | +0.62pp |
| Champion | 24.22% | 24.22% | 0.00pp |
| Top-3 Capture@5 | 60.25% | 60.87% | +0.62pp |
| Competitive Recall@5 | 55.79% | 56.50% | **+0.71pp**，95% CI [+0.16,+1.40]pp |
| NDCG@5 | 0.49909 | 0.50030 | +0.00121 |

五 fold 有 3 fold Gold／Good 同時非負；三個 ranking 指標全部正向。按場地：

- HV 53 場：Gold／Good／Champion 0；Capture +1.26pp、Recall +0.94pp、
  NDCG +0.00573；
- ST turf 100 場：Gold +1.00pp、Good +1.00pp、Champion 0、Capture +0.33pp、
  Recall +0.65pp、NDCG -0.00109；
- ST AWT 8 場：全部 0，因 archived table 無可識別 target surface evidence。

## 已開 terminal：只作非決策診斷

| 指標 | Delta |
|---|---:|
| Gold | 0.00pp |
| Good | **-2.00pp（少 1 場）** |
| Champion | 0.00pp |
| Top-3 Capture@5 | +0.67pp |
| Competitive Recall@5 | +0.90pp |
| NDCG@5 | +0.00699 |

Good 回退集中沙田草地；HV primary 全部持平。雖然排序指標正面，Stage 4 規定任何
Gold／Good dev 或 terminal 點估計回退即 `REJECT`。用戶明確偏好排序改善亦唔改變
評估合約；唔可以按已見 terminal 再改 ST 權重去救候選。

## 決定

1. **正式 V1 分數／排名不變**，保留可回退 known-good baseline。
2. V2 完整接入 Facts → Logic → engine；每匹馬輸出 score、target/surface effective N、
   source 同固定 surface profile。
3. `distance_suitability_v2` 加入 default shadow profiles，自動產生全場 shadow rank、
   rank delta、entered-top4，供未見賽事賽後結算。
4. AWT 修正 formguide 將 `rail=AWT` 誤當沙田草地嘅 surface identification；外地
   dirt/synthetic 只喺本地冇 target evidence 時作 fallback。由於 archived AWT coverage
   無法可靠回放，AWT weight 固定 0，先收 prospective evidence。
5. 血統資料目前只得 sire/dam 名，冇經驗性 distance/surface lookup；缺資料保持中性，
   禁止靠文字印象估分。

## 重現

```bash
PYTHONPYCACHEPREFIX=/tmp/hkjc-distance-v2-pycache \
python3 docs/experiments/patches/hkjc_distance_suitability_v2.py \
  --meeting-root '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing' \
  --output /tmp/hkjc_distance_suitability_v2_neutral.json
```

Production activation gate：只用今次之後未見賽事，Gold／Good 都非負，至少兩個預先
登記 ranking metric 改善且其中一個 terminal paired CI 下界 > 0；AWT 另要求足夠
surface-labelled races，唔同 HV/ST turf 合併判決。
