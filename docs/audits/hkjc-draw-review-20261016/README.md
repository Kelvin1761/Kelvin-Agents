# HKJC 檔位公式比較（2026-10-16）

結論：今輪四個預先登記候選全部未通過統計篩查，沒有候選可以取代現行公式。 這不代表 75／65／50 是全域最佳。

基準 commit `2d7ec14c09a3d6fa0bc5733406a730f7dff344ff`；325 場、33 個賽日、4101 匹次。
時間：2026-04-19 至 2026-10-07。Gold 基準 44/325；Good 81/325。

Gold＝實際前三全部在模型頭四；Good＝模型第一、第二揀都上名。

| 候選 | Gold 場數差 | Good 場數差 | NDCG@5 差 | v3 統計篩查 |
|---|---:|---:|---:|---|
| 相對檔位連續分 | -2 | -11 | +0.003302 | REJECT / primary_regression |
| 分場地／途程歷史差 | -4 | -6 | -0.003499 | REJECT / primary_regression |
| 檔位／出馬數／欄位分層 | -4 | -14 | -0.014128 | REJECT / primary_regression |
| 正則化回歸曲線 | -3 | -10 | -0.001558 | REJECT / primary_regression |

## 公式及可解讀範圍

完整預先登記公式見 [PROTOCOL.md](PROTOCOL.md)。只測普通馬檔位分；初出馬保留原分。沙田及跑馬地不混池，泥地獨立，途程用 exact distance。
歷史訓練池 22154 匹次／1797 場，2024-09-08 至 2026-10-07；逐個賽日只用 date < target_date。不是拿完整語料 fit 完再評自己。
相對檔位 x=(draw−1)/(賽前最大宣告檔位−1)。用最大宣告檔位而非賽後完成馬數。三個 learned 方案的最少 100 匹次／20 場門檻作用於同場地、表面、途程的歷史池。
固定差值／回歸曲線的分數尺度和收縮常數事前鎖定，沒有因結果再搜索 gain、門檻或權重。

## 場地分層

| 候選 | 沙田草地 Gold／Good 場差 | 跑馬地 Gold／Good 場差 | 泥地 Gold／Good 場差 |
|---|---:|---:|---:|
| 相對檔位連續分 | +2／-6（145場） | -4／-5（95場） | +0／+0（15場） |
| 分場地／途程歷史差 | -3／-7（145場） | -2／+0（95場） | +1／+1（15場） |
| 檔位／出馬數／欄位分層 | -3／-8（145場） | -2／-7（95場） | +1／+1（15場） |
| 正則化回歸曲線 | -1／-8（145場） | -3／-3（95場） | +1／+1（15場） |

## 資料及限制

- 70 場缺少／未能辨認 production 場地，全部候選在這些場次 no-op；沒有偷偷用賽果補場地再當公式收益。
- rail_draw_results 的 FieldSize 是有有效名次及檔位的完成馬數，未能當作完整賽前出馬數認證。訓練端上名機會分母有這個限制，不能宣稱已通過洩漏審計。
- 各賽日之前的結果日期已嚴格截斷；但舊 archive 是後來重建，確切的賽前 artifact 可用時間仍未全面認證。統計篩查是條件性診斷，並非 promotion。
- 官網檔位表按跑道／欄杆位置及途程統計。現有八份獨立存檔中七份標示 23 點後抓取；剩下一份亦缺時間區及首次開跑時間的不可變認證。因此官方表直接入分留待前瞻存檔；沒有將今天官網表套回歷史。
- 官方頁說明：https://racing.hkjc.com/zh-hk/local/information/draw 。官網目前表格及例子只用來核對欄位語意，不參與歷史候選選擇。
- SP 只在評分後加入 cohort，覆蓋 {'available': 325}，不入任何公式。場地、出馬數、途程、地況及初出馬 cohort 詳見 results.json；unknown going 不冒充已驗證。
- 候選家族 Holm 修正見 results.json；時間塊及按賽日 2000 次 bootstrap 使用既有 v3 判決器，沒有改判決規則。2026-10-11 起 forward 結果未開。

## 驗證及保存

- A/A：325 場 raw ability、排名完全一致；候選=baseline 判 REJECT。直接 production 路徑 20 組抽查 raw 分數及排名完全一致。
- 本次沒有修改 production 評分、權重、golden、數據合約或模型說明。
- 完整公式、CI、六時間塊、cohort、來源 hash 及 sample-floor 覆蓋見 results.json；原始較大 runner dump 留在 /private/tmp。

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 docs/audits/hkjc-draw-review-20261016/capture.py /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-baseline.jsonl
python3 docs/audits/hkjc-draw-review-20261016/study.py /private/tmp/hkjc-draw-20261016-baseline.jsonl /private/tmp/hkjc-draw-20261016-evidence.jsonl /private/tmp/hkjc-draw-20261016-study
python3 docs/audits/hkjc-draw-review-20261016/validate.py
python3 docs/audits/hkjc-draw-review-20261016/report.py
```

canonical_keys.json 保存上一輪同 session 已鎖定的 325 場 keys；原來源 /private/tmp/hkjc-review-20261016-canonical.jsonl。該批 351 場先排除 6 場 runner alignment mismatch，再排除 20 場 dead-speed。沒有按本輪績效再篩選。
