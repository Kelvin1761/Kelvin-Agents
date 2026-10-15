# EXP-20261015-10 — 以最近正式賽速度剖面預測下一次出賽（預登記）

基準origin/main `81597057`（AU引擎與`ca2c4bd6`相同）；先fresh dump再嚴格配對
EXP-08的2496場。原時間窗2026-08-05至10-14，首30賽日warmup、其後每7日一窗。
舊窗已觀察，本輪只屬探索性walk-forward，不是新forward holdout；source FLAG保留。
先搜尋EXP-04/05/06/08/09及INDEX，未有同一next-start supervised比較。

## 與失敗的同仗修正有何不同

EXP-06用同一仗full time對同仗早段做回歸，部分／總和相關不等於用力因果。
今輪X只含**目標賽之前最近一場正式賽**，y是之後目標賽同場上名／落第比較。
不再以同一仗總時間當response。只用formguide最新正式賽；缺該場時間不跳去更早賽。
最新日期有多個不同run key則記ambiguous，不擅選；排除trial／target日及未來日。

## 固定輸入

以原已驗證ContextStandard（不採用EXP-09新精確標準）按每個target日前資料fit：

- T：上一仗逐駒全程相對common-class par。
- P：上一仗field median early相對其class-aware early par及歷史trackday variant，
  `-log-ratio/.03`截在±3；只是觀察到的過去步速，不是目標賽步速預測。
- Q：上一仗個體early相對該場median early，`-log-ratio/.03`截在±3。
- profile=[T,P,Q,P²,Q²,PQ]，沒有再放late time（與total/early代數重疊）。
- 各項在當前完整field只用有證據馬做z、clip±3，再乘
  `w/(w+3)`；w沿用90日half-life、途程exp(-abs(log ratio)/.25)、不同going×.5。
  缺值全零、明確observed flag；不以缺值當最慢，無任何市場特徵。

## 已鎖四臂，沒有超參數搜索

N_total / N_profile：其他能力分中性、overlay零，分別用T / 六項profile。
D_total / D_profile：現行已部署A1.5分數作固定offset，分別加T / profile學得的修正。
兩種問題分開fit：N offset=0；D offset=(deployed score差)/10。
學習同場placed vs unplaced pairwise logistic，正例是上名馬−落第馬的X差。
不加intercept，ridge penalty固定10（sum logistic loss +10/2*||beta||²），零初值，
Newton最多50步、backtracking、tol1e-8；不足20訓練pairs退回beta=0。
只用2026-08-05之後、target驗證窗之前的訓練賽；同日不跨窗。
兩類模型訓練及比較都只用最近正式賽有完整資料的同一批馬／同一批pairs。
預測score N=60+10*Xbeta，D=round(deployed+10*Xbeta,4)。
缺資料D保持原分，N保持60；不把中性馬號排序算進純訊號辨識力。
不搜尋lambda／scale／gain／時窗／profile子集；不因結果加入新arm。

## 評估

- 固定同1493場驗證集（fresh配對若改變就停），N只在observed cohort量AUC。
  N_profile−N_total是剖面自身額外訊號；D_profile−D_total是原模型以外剖面邊際。
- canonical counts及_stage4_metric_rows：Gold/Good/Pass、五ranking metrics，
  按賽日2000bootstrap seed7、六時間塊；D兩臂與七metric為同family Holm。
- 距離≤1200/1201–1700/>1700、going、venue、field size、首選result-SP分層；SP僅評估。
- 在fit之前記原A部件移除budget/MDE作背景；這不是新profile完整§6預算，
  本輪不宣稱正式RANKING_WIN。source publication FLAG亦直接阻止正式WIN。
- 先驗證零feature=原分、零offset/logistic合成方向、未來append不改過去feature及fit、
  最新正式賽缺值不得跳過、target/未來run剔除、outcome不進feature。
- 保存train-through、beta、pair數、缺值原因、每筆previous日期；所有previous<target、
  所有fit target日<test日。原baseline與deployed固定回看不混作fresh holdout。

## 交付

研究腳本、測試、結果、完整來源與命令；不改現役模型／dashboard／前瞻R1凍結版本。
若沒有穩健收益照記失敗，不改尺度去救候選。新速度來源擴張不在本輪範圍。
