# EXP-20261113-30 HKJC：近六仗以外嘅狀態／穩定性與同場同程

- 日期：2026-11-13；Kelvin 授權研究；production 不改。
- Baseline：`e6e45aa1d`，同一 worktree 現行 production orchestrator + PIT priors。
- 舊記錄：EXP-20261007-03 完整同程歷史修正；EXP-20261105-03 名次／輸距分拆；
  EXP-20261109-02 rolling class（失敗；今次唔改 class）；EXP-20260928-01 場地歷史。
- 假設：第 7–12 仗提供額外狀態／穩定性資訊；同場同程可以分辨相同路程但唔同跑道嘅實績。

## 預先凍結（任何候選結果之前）

全部 arm 只讀 matching meeting/race Facts 馬匹區塊內本地正式歷史表；馬號與馬名均須匹配。
歷史按日期去重、日期必須嚴格早於賽日；海外表、當日／未來行、非正式名次不入。
第 1–6 仗保留 production 原文；延長窗要求 Facts 前六名次及日期與 production recent_6_detail 完全一致，
否則 fallback production，不將缺值當差績。只用賽前已發生嘅日期、名次、輸距、場地、途程。

| Arm | 唯一改動 |
|---|---|
| F12 | 名次分保留現行分檔及 1/(i+1) 權重，加入第 7–12 仗；冇完整六仗或額外歷史則不變 |
| S12 | 保留現行 close/poor/severe 輸距規則、近三仗對 4–6 仗趨勢；加入第 7–12 仗，權重由第六仗 0.35 每仗乘 0.85 |
| FS12 | F12+S12；唯一預先登記互動，拆開 arm 作消融 |
| CD | 只將獨立同程加分所讀嘅紀錄換為同馬場＋同表面＋同途程；現行有上名／未上名加減幅完全保留；冇匹配歷史為中性；不改 risk/class |

唔試其他窗、門檻、權重或組合去救候選。以上四個係同一 family。

## 語料與判決

- 開發全紀錄：hkjc_eval_harness `--until 2026-10-10`；死 speed_score 場次按現行 harness 排除。
- Forward：2026-10-11 起，只有 family 經 Holm 後 WIN 先開一次；否則不讀其結果作候選判決。
- 現行 baseline 先 replay；A/A 必須 REJECT，matrix rerank current 必須與 production 排名完全一致。
- §6 功效：在候選結果之前量 stability／distance_fit 中性化部件預算與賽日 bootstrap CI 半寬。
- §8：每個候選都做 A1/A0 與 B1/B0；live guard B1/A0、stale B0/A0。
  B0/B1 同用原有 hkjc_weight_study.wf_refit：10 meeting warmup、之前所有賽日、tau=3、L2=2、
  production prior、L-BFGS-B 300 iterations；程序以檔案 SHA256 鎖定。
  擬合排除死欄位日，雙方同樣本；同日資料不得跨入訓練。
- Stage4 v3 原有 primary、五個 ranking metrics、6 時間塊、賽日 bootstrap 2000、seed7。
  family 全部 fixed/refit 共八個機會做 Holm；§8 判決器另做 arm 內 Holm。
- 必報 Gold、Good、capture@5、NDCG@5、top2_any_hit；場地、馬群、班次、首選 SP、久休及初出分層。
  SP 只作評估分層，永不入候選。功效不足記不確定，不稱無效。
- 不擇參、不改評估合約；未過閘不改 live、不開自動 forward 測試。

## 交付

濃縮結果、可重跑研究程式與命令、輸入／程序 hash；原始 dump 留 `/private/tmp/hkjc-long-form-study-20261113/`。
只對證據支持嘅候選考慮 production，未通過嘅研究不改 production scoring。
