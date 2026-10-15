# EXP-20261015-08 — 純速度、相同樣本比較及聯合重配（預先登記）

用戶要求：先將其餘訊號中性化，驗證速度本身，再研究權重。研究基準 SHA
`ca2c4bd6b8435373158dc438765006f24a8df73b`；不改現役引擎、dashboard 或評估合約。
本文件在本輪結果計算之前寫入。研究不是 production promotion。

## 資料與限制

- 重新執行現行 `au_dump_engine_leaves.py`，與 EXP-04 frozen contextual features 按
  meeting/date/race/horse number/name/result 嚴格配對；只保留相同完整場次。
- 正式賽歷史逐駒時間：A 全程 contextual speed，B total−L800 contextual early speed。
  原 EXP-04 prior-date-only transform、最近六仗/可靠度收縮固定，不再調整。
- 日期固定 2026-08-05 至 2026-10-14；首30個賽日 warmup，之後每7賽日一窗。
  每窗所有 fit 只收之前賽日。舊窗已被觀察，本次是 retrospective exploratory OOS，
  不是新的 forward holdout。原歷史 source publication/capture FLAG 保留。
- 缺速度 A/B=null，不當成慢。排名補充分析用 contribution=0；純訊號比較只用有證據馬。
  現有 leaf=60 預設剔除；這只是中性代理，不等於完整 source-state 證明。
- 香港參考：保留逐段距離/時間與分段標準。HKJC 現行 winner-derived pace correction
  大致化簡為 margin×0.17，且 L600 有半段近似，均不移植 AU。

## 已鎖測試家族

1. 純 A、純 B：其他全部60，wet/proven_class/full_time 等 overlay 歸零。
   場內 placed/unplaced AUC、按日 bootstrap2000/seed7、六時間塊；以 60+signal 排序。
   驗證正 gain 只改尺度、不改順位；中性模型 AUC 必須0.5，不能把馬號 tie-break 當能力。
2. A 對六個既有 leaf：pace_figure、performance_quality、form、rating、jockey、trainer。
   每一對均使用同場同一批 A有值且leaf非60的馬；比較AUC差、paired date CI及Holm。
   不跨不同覆蓋率直接比較。另列短途≤1200、中途1201–1700、長途>1700。
3. 聯合權重三臂：R0重配原六維；R1六維+A；R2六維+A+B。
   三者原有overlay維持不變，速度只在新增維度出現一次；不再另加部署gain1.5。
   新速度維度固定60+10×已收縮場內z；缺值60。正權重總和固定為原總和。
   每臂512個Dirichlet(1) proposal，seed7；不以原權重作初始化偏好。
   所有proposal相對原無A baseline：訓練Gold/Good均不下降、place objective嚴格上升、
   五個連續日期fold至少4個不下降。合格者逐維中位數再歸一化，重驗同一閘；
   無合格共識則退回原無A baseline。不取argmax，不增添proposal/arm/門檻。
   R1−R0量A邊際；R2−R1量B邊際；另比較每臂對原baseline及固定部署1.5回看。
4. 在候選結果前先量 baseline+A1.5 vs baseline 的 component budget/CI半寬(MDE)。
   共用 canonical _counts、_stage4_metric_rows、v3 evaluator；日期bootstrap2000/seed7、
   六時間塊、Holm family校正；field size/going/distance/venue/result-SP僅作評估分層。
   賠率不進特徵或fit。source FLAG 未清，即使統計通過也不宣稱上線WIN。

## 決策

只交研究結果與可重現腳本。任何優勝候選需要之後未開過的賽日及source-safe證據確認。
失敗亦照記；不部署研究參數，不改既有模型說明/golden/data-contract基準。
