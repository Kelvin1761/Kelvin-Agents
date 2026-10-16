# 驗證紀錄

- 基準：2d7ec14c09a3d6fa0bc5733406a730f7dff344ff。
- ./檢查.sh --quick：PASS（開工及最終版本）。
- ./檢查.sh：PASS，All suites passed；沒有改 production code、golden 或 contract baseline。
- A/A：325 場 raw ability 及排名完全一致；既有 v3 判決器拒絕 A/A。
- validate.py：五個預先按條件抽取場次 × 四個候選，共 20 組，direct production raw ability 及排名完全一致。
- 初次 parity wrapper patch 到 package draw 類別，但現役 engine 用 top-level draw 類別，所以 patch 未接通；修正為 engine_core 實際持有的 DrawScorer 後，20 組全數一致。初次 wrapper 失敗不作任何候選績效證據。
- 逐日訓練 latest_training_date < target_date；2026-10-11 起 forward 未開。
- 四個候選全部 REJECT / primary_regression。來源可用時間及完成馬數分母仍為 FLAG，沒有 promotion。

日誌保留於 /private/tmp/hkjc-draw-20261016-{capture,study,parity,report,full,final-quick}.log。
本分支只保存研究方法與失敗實驗記錄；沒有部署或啟用候選。
