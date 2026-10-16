# HKJC 公式審查：預先登記

- 用戶要求：逐維度審查全部公式，測試狀態與穩定性四個討論點，必要時做 ML。
- Baseline：`dd22b05d`，現役完整 production replay + 每賽日前 PIT 騎練統計。
- 資料：hkjc_eval_harness 可發現、截至 2026-10-10 嘅 meeting；speed_score 死日剔除。
- 2026-10-11 起資料不讀，保留既有 forward 實驗一次性確認用途。
- 只讀 archive，禁止重寫 Logic、prediction snapshot、CSV 或部署。

## 固定測試，唔因結果加 arm／調數值

1. 重疊：近績 F 設 60、穩定性 C 設 60，分別消融，唔重新分配權重。
2. 名次粗化：量第六或以後但輸距 ≤2.5 馬位嘅往績、第四五 vs 第六七同輸距嘅分數斷層；
   固定候選只將近績第六七名由 40 提到 60（同第四五相同），其他不變。
3. 前三不看輸距：固定候選對亞季且輸距 >3 嘅逐仗 close credit 乘 `3 / margin`；
   只改 C，沿用既有 3 馬位門檻，唔 fit。
4. 缺詳情轉尺：量實際 fallback 覆蓋。候選只對非初出且無可解析逐仗資料者，
   將 last_6_finishes 轉成 margin=None 嘅往績，走現役 C 詳情公式；不憑空補輸距。

以上五個 arm 同屬 stability 家族，用 Holm 多重比較；power 先量 F／C 中性化嘅部件預算。
所有離線重算要重新執行 production SIP／全場 shape cap，A/A 必須逐分逐排名一致；
至少對候選逐場用真 engine replay 確認，否則只屬診斷。

## 全模型

- 九維逐一設 60，保留原權重，衡量有限語料下邊際貢獻；只屬消融診斷，唔自動剷維度。
- 場內 AUC、場內中心化相關、neutral 值與來源覆蓋、輸入日期及排序診斷。
- ML 沿用 hkjc_weight_study 既定 wf_refit（warmup=10、tau=3、L2=2），不搜參；
  每賽日只用之前賽日 fit。原工具保留 SIP residual，所以只可診斷權重，不能當成已驗證 production 候選。
- A/A 應無變；v3 要 REJECT。評估用賽日 bootstrap 2000 次、六時間塊、primary 與 ranking 指標。
- 全模型／ML 沿用舊實驗方向屬最新版本重驗，不宣稱係新發現。
- 需報場地、馬群、首選 SP（若無可靠欄則明確記缺口）；FLAG 未清不准 promotion。

## 交付

保留現役模型，交付可重跑 scripts、濃縮結果、公式來源索引及診斷限制。
本輪新候選未有未見過 forward 賽日確認，一律不自動啟用。

## 輸距語義更正（2026-10-16，原測試已撤回）

原定義將 rank=1 都當成可以有正數落後輸距，係語義錯誤。冠軍嘅正數距離不能解讀成輸距。
原296筆包含52筆冠軍、63筆亞軍、181筆季軍；原測試及其「Good少1」解讀撤回。
更正候選只對rank=2/3套同一3位門檻及同一折減公式，不改參數、不按結果揀規則；
重跑前先記此更正，同一stability家族計Holm。舊版輸出保留/private/tmp/hkjc-review-20261016-withdrawn-top3-results.json。
