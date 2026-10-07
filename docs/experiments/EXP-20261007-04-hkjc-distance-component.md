# EXP-20261007-04 — 路程性能由 class 拆出

Status: **STRUCTURAL MIGRATION KEEP／AGGRESSIVE REFIT REJECT**。

## 問題

`distance_score` 一直只係參考分；同程上名／未上名卻經 `class_score` 入 7D
`class_advantage`。呢條路徑概念錯：路程性能唔等於級數優勢。今次用已修好嘅完整
point-in-time 歷史，比較三個版本：

1. 現役完整歷史公式；
2. 從 `class_score` 完全移除同程加減分；
3. 版本 2 加獨立 capped distance component，沙田／跑馬地分開 fit。

語料 catalog 回報 `hot_only_unregistered`：本機 archive 足以做同窗 A/B，但未登記入
長期 catalog，結果唔應過度外推。

## 設計

Harness：`docs/experiments/patches/hkjc_distance_component_ab.py`

- 331 場／33 日，2026-04-12 至 2026-10-04；
- development 281 場；最後 15% 日期 terminal 50 場；
- 3,982 匹有完整歷史；當日／未來 row = **0**；
- 獨立 component grid：權重 2/4/6/8%，cap 4/6/8/10；
- ST 與 HV 分開 fit，選參數只用 expanding development folds；
- terminal 只開一次。

## 結果

### A. 只由 class 拆走同程分

| Window | Gold | Good | Champion | Capture@5 | Recall@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| Development | +0.36pp | +0.36pp | +0.71pp | +0.59pp | +0.48pp | +0.0025 |
| Terminal | 0.00pp | **-2.00pp** | 0.00pp | 0.00pp | 0.00pp | -0.0004 |

Stage 4：`REJECT / primary_regression (good_positional)`。Terminal 少一場 Good，集中
沙田草地；跑馬地 Gold／Good／Champion 全部零差。

### B. 獨立低權重 capped component

五個 walk-forward folds 最終四個守住 primary；aggregate 六項全部向上：Gold／Good
各 +1.24pp、Champion +2.48pp、Capture@5 +1.24pp、Recall@5 +1.11pp、NDCG
+0.0176。Development 最終 fit 兩個場地都選 8%／cap 10。

Terminal 出現明確取捨：Gold -2.00pp、Good 0.00pp、Champion -2.00pp，但
Capture@5 +2.00pp、Recall@5 +2.53pp、NDCG +0.0218。跑馬地 ranking 指標全升，
但少一場 Gold；沙田草地 Good／Champion回退。Stage 4：
`REJECT / primary_regression (gold)`。唔准按已開 terminal 再揀 2/4/6% 救結果。

## 採用嘅結構修正

進取 weighting 唔上線，但概念污染仍然要修：

- `class_score` 不再讀同程紀錄；
- 同程上名／未上名改成獨立、報告可見嘅 `distance_suitability_adjustment`；
- 先精確搬移舊貢獻（約 +0.43／-0.17 raw），唔改總分與排名；
- 7D 表列出 matrix subtotal，再獨立列路程調整，唔再將路程證據寫成級數優勢；
- 較進取 ST/HV distance weight 留待新賽事 prospective confirmation。

舊引擎與新結構在完整 331 場的逐匹 raw-score SHA256 均為
`f67b8da40bd431f90d22d1f434f14f57ee6e7484c751a2183367a6f52d7cfa4a`，逐場排名
SHA256 均為 `1f01fd6c55dc174574d33a96455a02671c9edd1653453f152c6738d85b463b59`。
因此呢次係語義／透明度修正，**唔聲稱績效提升**。

## 附帶營運修正

直接由 HKJC full orchestrator 完成評分時，post-success hook 過往只重發 live snapshot，
`target_dir` 只作 log 顯示，造成「Cloudflare deploy 成功、Dashboard 內容冇更新」。hook
而家會先將新 meeting merge 入 live snapshot，再把該 snapshot 傳畀 `deploy.sh`；新增
回歸測試鎖定 `WC_DASHBOARD_BASE_SNAPSHOT`。如果 fresh snapshot 建立失敗，hook 會拒絕
報告成功，避免再出現「deploy 綠燈但 Dashboard 仍舊」。
