# EXP-20261007-03 — HKJC 完整歷史同程統計

Status: **PROMOTE AS CORRECTNESS FIX**（唔係已證實表現改善）。

## 問題

2026-10-01 沙田尾場亞軍勇者為皇，本身 Facts／Auto report 已正確顯示
`1200m 6場（2冠）`、路程分 72，亦冇 `distance_unproven`。不過用戶指出嘅
「畫面話路程證明不足，但歷史其實有同程成績」係一個真實而廣泛嘅資料問題：

- Facts 會顯示「完整賽績檔案」同「較舊歷史賽績」兩張表；
- `compute_stats()` 同 `compute_distance_aptitude()` 卻只食 formguide 近期表；
- 所以較舊官方 horse-profile rows 肉眼睇到，但 `同程`、`同場同程`、
  `最佳距離`、`distance_score` 同 `risk_score` 完全冇計。

靜態掃描 360 份 Facts／4,517 匹馬，2,378 匹嘅顯示同程總數與完整表不一致；
當中 335 匹同時出現 `路程證明不足`／`同程往績未足以建立信心`。呢個係可獨立
證明嘅資料正確性問題，而唔係靠賽果揀出嚟嘅候選。

## 修正

- 將 formguide recent rows 同官方 horse-profile full history 按賽事日期去重合併；
- recent formguide row 優先，保留段速／評語等較完整資料；
- horse-profile 只補較舊本地歷史；
- archive replay 仍先用 meeting date 過濾 profile，當日及未來 row 不可進入；
- 同一份完整 PIT history 同時供 `season_stats`、`same_dist`、
  `same_venue_dist`、個別場地 shadow 同 `best_distance` 使用；
- 日期 parser 同時接受 HKJC profile 嘅 `DD/MM/YY` 同 formguide 嘅 `DD/MM/YYYY`。

## Locked A/B

Harness：`docs/experiments/patches/hkjc_full_history_distance_ab.py`

語料：331 場、33 日（2026-04-12 至 2026-10-04）；最後 15% 日期為 terminal，
共 50 場。Baseline 同 candidate 用同一份現役 engine 重算；candidate 只替換完整
PIT 賽績可以決定嘅 season／distance aggregate 同 `best_distance`，冇使用賠率、
當日賽果或未來 row。

### Coverage / leakage

| 項目 | 數量 |
|---|---:|
| 有完整歷史 runner | 3,982 |
| season_stats 改變 | 2,652 |
| best_distance 改變 | 2,425 |
| ability score 改變 | 828 |
| 錯誤 distance risk 消除 | 335 |
| 當日／未來 row | **0** |

平均絕對 ability 變動 0.261 分，最大 3.41 分。

### Metrics

| Window | Gold | Good | Champion | Capture@5 | Competitive recall@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| Development | +0.36pp | -0.36pp | 0.00pp | +0.24pp | -0.10pp | +0.0005 |
| Terminal | **0.00pp** | **0.00pp** | -2.00pp | 0.00pp | +0.40pp | -0.0048 |
| All | +0.30pp | -0.30pp | -0.30pp | +0.20pp | -0.03pp | -0.0003 |

Development Good 同 terminal Champion/NDCG 嘅 paired 95% CI 均跨零；terminal
Gold／Good 完全相同。Venue primary cohorts 冇顯著倒退。呢個結果**冇通過表現改善
閘門，唔可以叫已證實提升**。

## 判決

按 evaluation contract §7 以 correctness fix 上線：舊 code 顯示完整官方歷史、
計分卻靜靜漏走同一批 row，即使績效點估計相反都應修；PIT leakage audit PASS，
terminal primary 零倒退，亦冇顯著 primary cohort regression。

預期好處係消除錯誤路程風險與補回可靠同程證據；唔聲稱單靠呢個改動已令整體
排名表現顯著提升。
