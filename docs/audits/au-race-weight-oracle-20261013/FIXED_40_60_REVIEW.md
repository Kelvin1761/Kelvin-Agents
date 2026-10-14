# 固定40／60：重播及差異覆核

**結論：舊Good+14可以重現，值得研究；現行main未重現同等增益。**
40:60 = FORM40%、PQ60%，只係stability內部配比，唔係全模型權重。

| 比較 | 場數 | Gold淨增 | Good淨增 |
|---|---:|---:|---:|
| 原snapshot、原矩陣、原dev |1762|+1|+14|
| 原snapshot分數、現行矩陣、原dev |1762|0|+9|
| 現行main產線、原dev |1762|−1|+5|
| 現行main產線、後段 |771|+6|−7|
| 現行main產線、全紀錄 |2533|+5|−2|

## 原數字實際包含咩

Good452→466，修好47／失去33，淨+14（+0.795pp；相對452約+3.10%）。
Gold380→381，修好33／失去32，淨+1，唔係額外捕捉一場且完全保住其餘。
Good改善散佈19個淨正日、12個淨負日，最大單日+3；不是集中一日。
FORM缺名次場Good+6，其他場+8；08-25後Good+9。
所以不能將改善全部歸因於早期缺資料，亦不能用CI跨零證明無效。

原報告逐場bootstrap；此次補回現行規格賽日bootstrap（2000、seed7），
Good95%CI[0,+1.637]pp，Gold[−0.870,+1.120]pp；Good下界等於零，仍未證實
獨立可泛化提升。未作多重搜索校正嘅exact McNemar Good p=.1456。
新CI不是換尺救候選；舊CI保留，沒有按新CI作promotion。

## 點解唔可以用自動選配比失敗判死固定40:60

之前forward模型用FORM .2/.4/.6/.6，佢係選擇策略，唔係固定.4。
兩者必須分開。此輪只覆核固定.4，沒有新增參數搜索。

## 舊矩陣同現行main唔一致

原實驗位於primary舊checkout0116c740及其未提交改動；現行main為a0bf0f38。
六個ranking係數相同，矩陣配方唯一差異係class_weight：
舊只用rating_score .70；現行另有class_score .15。
保持原馬匹features與overlay，改用現行配方，Good+14→+9；
使用現行engine重評相同原dev，Good進一步+9→+5。
現行baseline Good458已高於原baseline452；原候選466不能直接同458跨harness比。
同一份新語料新baseline458→新candidate463，先係合法比較。

原dev可比runner非中性feature變動：form104、rating749、class2768；
confidence/weight亦有變，但本身唔進ranking。沒有證據將全部差異歸咎某一修正。
新舊配方對原凍結分數嘅控制比較證明配方影響；具體features差異只係描述性歸因。
production thin-evidence只對調頭兩位，結構上不改Good/Gold集合。
已逐場驗證原dev有／無對調嘅Good/Gold相同，不能用佢解釋增益收窄。

## 新模型下嘅穩定性

全期Good修好49／失去51；Gold修好50／失去45。
GoodΔ−0.0790pp，賽日CI[−0.779,+0.632]pp。
GoldΔ+0.1974pp，CI[−0.632,+1.025]pp。
六個時間塊Good非負3/6，Gold5/6；新v3主要KPI閘不通過。
首選SP≤3：Good−4；其他SP只作cohort觀察，不能用嚟新調參。
Top5前三捕捉率−0.0658pp、平均前三模型名次+0.00855（稍差）、NDCG−0.1582pp；
不是一個各方面同步改善的候選。以上不表示已證實退步，區間仍有不確定性。

## 「漏場」目標有值得保留嘅訊號

補充診斷Gold或Good（原oracle本身亦以兩者皆未達標定miss），唔換成promotion尺：
舊587→617，淨多30，修好65／失去35；賽日CI[+0.660,+2.950]pp。
但Gold且Good245→230，少15，CI[−1.670,−0.057]pp。
現行全期Gold或Good849→864，淨多15，修好72／失去57，CI[−0.252,+1.517]pp；
Gold且Good344→332，少12。佢傾向擴闊「至少有一項成功」覆蓋，但減少雙重成功。
這項診斷是在查看transition後加入，明確屬post-hoc，不可拿來救未過primary嘅候選。

## 可重現性／限制

所有現行2533場先捕捉main完整production projection，逐匹baseline分數及renderer
完整排名完全一致；candidate只改stability，保留grade、原始overlay、rounding、安全欄。
完整field用嚟計分及標準化；賽果評估沿用固定eligibility/aligned roster。
完整roster比joined roster多687個runner，排名過濾方式兩個arm一致；不稱為歷史
published榜單排名，亦未對缺結果或withdrawal做新結果補全。
40:60已由六格dev搜索挑出，不能事後叫fixed_rule獨立驗證；已曝光後段亦不是
未開封forward holdout。mutable archive統計嘅完整PIT來源仍未單獨認證。

今輪只保存研究，live維持60:40。若追蹤固定40:60，應鎖版本跟全新賽日平行觀察，
不混入重新挑配比或改成功定義。本輪没有建立排程或自動promotion。

原始紀錄：scratch/au_fixed_40_60_20261013/。
覆核腳本：docs/experiments/patches/au_fixed_stability_{mix_review,old_diagnostic,attribution}.py。
使用/usr/bin/python3（production3.9）；old diagnostic用.venv-au-ml/bin/python。
模型版本a0bf0f388bd6053641cc08d41b2915ee73bb7c5f；dataset SHA
 db0ffe220069c1c8e3b40275a5e497355c95ed977b3505d2e578a541c12f9519。

## 來源分流設計後續

用戶追問更準確測試及更好設計後，完成真正PQ／fallback來源診斷，同一語料探索單一來源分流候選。全2533場Gold+4／Good+5，後段Good−1；仍未獨立驗證。詳細見[stability設計與測試覆核](STABILITY_DESIGN_REVIEW.md)及EXP-20261013-07。診斷與結果SHA保存於scratch/au_fixed_40_60_20261013/review_manifest.json。
