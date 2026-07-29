# HKJC 競爭力排序 Archive Review

## 結論

- Gold / Good / Pass 保留作輔助標籤；主評估改用 Top3@4/5、winner rank、NDCG@5、competitive-tier recall。
- 全樣本 245 場；0/1-hit 75.1%。
- 模型前四平均捕捉實際前三 55.4%；前五 63.4%。
- 實際前三全在模型前五：22.9%；winner@5：69.0%。
- NDCG@5：0.532；competitive-tier recall@5：58.4%。

## 異常結果處理

- 有可審核異常標註並從 adjusted 層排除：79 場。
- unfiltered baseline 永遠保留；無 incident／極冷門標註嘅賽事唔會自動排除。
- Adjusted 166 場：Top3@5 69.5%，NDCG@5 0.586。

## 0/1-hit 主因

| 主因 | 場數 | 比例 |
|---|---:|---:|
| 已標註異常賽果 | 74 | 40.2% |
| 整體競爭群辨識不足 | 42 | 22.8% |
| 競爭層已捕捉但頭二排序不足 | 22 | 12.0% |
| 騎練訊號辨識不足 | 9 | 4.9% |
| 班次／負磅context辨識不足 | 7 | 3.8% |
| 資料稀薄／不確定性處理不足 | 7 | 3.8% |
| form line辨識不足 | 7 | 3.8% |
| 直路賽專屬轉化不足 | 5 | 2.7% |
| 狀態穩定性辨識不足 | 5 | 2.7% |
| 初出馬備戰／不確定性轉化不足 | 3 | 1.6% |
| 段速辨識不足 | 2 | 1.1% |
| 備戰／風險辨識不足 | 1 | 0.5% |

## 專項

| Cohort | 場數 | 樣本 | Top3@5 | 全部前三@5 | NDCG@5 | 0/1-hit |
|---|---:|---|---:|---:|---:|---:|
| 沙田直路1000米 | 8 | small | 70.8% | 37.5% | 0.546 | 100.0% |
| 有初出馬 | 61 | stable | 71.0% | 36.1% | 0.576 | 75.4% |
| 新馬賽 | 1 | small | 66.7% | 0.0% | 0.791 | 100.0% |
| 有外隊馬 | 0 | unavailable | — | — | — | — |

## Data limitations

- 外隊馬標籤可用場次：0；未有可驗證 archive sample，現階段只可做 pipeline／synthetic contract test，唔可宣稱實證已優化。
- 真正新馬賽（race-class 標籤）只有 1 場；「有初出馬」另有 61 場，兩者不可混為一談。
- 245 場 replay 分為 archived snapshot 與 current reconstructed primitives；cohort 報告保留 source split。

## Files

- Structured weak-race CSV: `/Users/imac/Antigravity-repo/scratch/hkjc_competitiveness_weak_races.csv`
- Full JSON: `/Users/imac/Antigravity-repo/scratch/hkjc_competitiveness_review.json`
