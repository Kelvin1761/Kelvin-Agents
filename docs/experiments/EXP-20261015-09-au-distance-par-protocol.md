# EXP-20261015-09 — 精確賽程標準與下一階段驗證（預登記）

基準`ca2c4bd6`；研究沿用EXP-08同2496場／41日1493場驗證，仍是已觀察的探索窗。
不修改現行模型、dashboard、評估合約、gain或歷史試閘規則。

## 假設與固定改動

香港值得參考的是精確「馬場×途程」標準。AU現標準以全球距離曲線及
track×400m band部分pooling；同band包含不同起步點，可能留下賽程偏差。
本輪只試一個新標準：把track_band分類鍵由distance//400換成精確distance。
其餘Huber/ridge懲罰、全球距離曲線、going/rating/class/rail、歷史trackday variant、
原聚合六仗／90日／途程權重／可靠度收縮全不變。沒有搜索band大小或懲罰。
沒有新增global distance類別、硬性長途cutoff、能量修正或GPS多跑距離bonus。

1. 先審計：每個target的可配對正式往績，尤其長途馬的往績途程、matched weight占比、
   原400m band和精確賽程訓練樣本支持。使用same corpus與prior-only seed events。
2. Candidate T_exact全程：只改上述standard category。先量改動相對deployed A1.5的
   component budget/MDE；純AUC用完全相同覆蓋，按日2000bootstrap/seed7，六時間塊。
   排名固定加1.5×新z，無gain refit。報canonical Gold/Good/Pass、五ranking metrics、
   cohort及v3 source FLAG。對原全程A和新全程A做paired AUC差。
3. 分段剖面只作診斷：精確賽程標準下分開total、early=total−L800、late=L800。
   原始時間與距離保留，不插值、不把半段當真L600，不假設early+late指數可相加。
   三者能力AUC屬同一diagnostic family，Holm校正；不將頭／末段新增入排名。
4. 重播A/A要與EXP-08 current leaves/context raw A一致；長途／其他cohort不改切法。
   過往EXP-05/06的E600/Fraction/Cruise/effort correction失敗方向不原樣重試。

## 前瞻方案凍結

R1 profile取EXP-08最後一個時間窗已學得的權重（按日期選，不按測試績效選），
訓練截止2026-10-08；這個單一profile**不等於**六窗合計Gold+3/Good+5。
與已部署A1.5並列shadow。固定profile、模型formula和input hash，目標日從2026-10-16起。
獨立研究CLI只讀新賽前已評分Logic，檢查target/capture/prediction日期及來源，
輸出獨立shadow JSON，絕不覆寫推介／Logic／dashboard，不自動新增排程。
現存Logic沒有可驗證jump timestamp，因此CLI只准前一個或更早賽日capture；同日資料
拒絕，避免「日期相同但其實賽後」混入前瞻。工具尚未自動接入每日pipeline。
前瞻結果至少30個新賽日及1000場、200場速度可比較場次才開一次確認；之前不調參。
新標準T_exact不因舊窗好看自動加入這個已凍結family，另需新版本登記。

## 決策限制

舊source capture/publication FLAG仍在；本輪即使統計有改善也不能宣稱fresh WIN。
準備前瞻工具不等於已收集到未來資料。只交研究及可執行工具，候選參數不部署。
