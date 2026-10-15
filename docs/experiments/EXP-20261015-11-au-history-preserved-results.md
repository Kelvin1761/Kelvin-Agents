# EXP-20261015-11 — 近兩、三場延伸（舊基準，未採用）

本輪在補來源前已跑完，結果沿用舊2496／1493場與availability FLAG，不能作最新正式證據。
H1（最近一仗）相對現役Gold+2／Good+2／Pass+4；H2為+2/+3/+4；H3為+2/+2/+4。
第二仗只有額外Good+1，第三仗回吐，沒有採用多仗係數或作為EXP12/13模型。
H1 feature／score重播EXP10最大差都是0。只在latest有資料cohort內嘗試兩、三仗，
不跳缺值，固定ridge10與原時間窗；沒有以最好一仗或peak搜索。

原暫存worktree被外部清理，未commit的專用driver與預登記檔遺失。
因此這份記錄只保存實際存活的結果與限制，**不聲稱這輪可完整逐命令重現**。
留存results/predictions含beta、每筆特徵／previous日期；不以無法完整重跑的結果部署。
目前持久worktree已放repo .scratch，後續只用已commit研究scripts。

留存artifact：`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-speed-history-research`。
results SHA256 `e80da8401886881b150cc7a6be58889a7ab2af59e0f2091c4df9405df3edaf9b`。
同目錄extra-fields-audit只做來源診斷：距離／步頻／步幅有異常和重複speed資訊，
未加wide／stride bonus，未用失手體檢擇參。
