# EXP-20261015-12／13 — 可靠時間覆蓋與RQ冠名配對

基準 `9f0360c7`；本輪研究分支，**沒有正式啟用／沒有改dashboard或四線runtime**。
用戶授權補可靠資料，結果好先發布；本輪未達正式發布證據要求。
[來源協議](EXP-20261015-12-au-time-coverage-protocol.md)、[獨立配對修正協議](EXP-20261015-13-au-rq-venue-binding-protocol.md)。
EXP-13在讀過12結果後另開；不能將13說成12的預先登記結果。

## 可靠資料與覆蓋

官方[公告](https://tasracing.com.au/news/new-sectional-provider-for-tasmanian-thoroughbred-racing?hs_amp=true)
說明2026起逐駒video timing。官方FORMPLUS public calendar/race/report目錄供48場meeting Excel。
讀每匹馬的IVRTIME；不拿OFFTIME頭馬鐘或margin推算補值。
接受385場／3445匹逐駒時間（Launceston141、Hobart135、Devonport102、Longford7場）。
排除四場source/API距離不同、一場無足夠有效馬、七筆分段身份不合。
檢查total=early+L800、L800=末四段，但這是表內算術完整性，不是獨立儀器準確度驗證。
來源GPS／video計時方法不同，不能聲稱已完全校準儀器偏差。

每個URL都有raw、SHA256、capture timestamp；附件date/modified以UTC解讀作保守as-of，
publication不冒充當時已capture，沒有清除原RQ歷史availability FLAG。
Tasracing不合日期／未知venue／header／重名／距離者fail closed；無付費或估算時間。
Devonport僅由同meeting API+明確Synthetic+報告layout核實後連到devonportsynthetic。

RQ官方club頁證實冠名與club：
[Gold Coast](https://www.racingqueensland.com.au/racing/club-details/thoroughbred/gold-coast-turf-club)、
[Cairns](https://www.racingqueensland.com.au/racing/club-details/thoroughbred/cairns-jockey-club)、
[Warwick](https://www.racingqueensland.com.au/racing/club-details/thoroughbred/warwick-turf-club)。
只加這三個source-local lookup binding，日期／場號／距離／馬名仍exact match，
不改global normalizer或source track par，Poly與Warwick Farm不合併。

同一乾淨驗證語料14,361匹次（1483場、41日），原嚴格latest覆蓋1816（12.65%），
只補TAS1852（12.90%），再加核實冠名配對2319（16.15%）。
新增503：Gold Coast297、Cairns103、Warwick67、TAS36。
這仍有11263筆latest未覆蓋、779筆form無更早正式賽紀錄；後者不直接等於已證實初出。
因此**覆蓋改善，但覆蓋問題未解決**。未配對量最大的venue包括Belmont331、Randwick274、
Caulfield260、Kalgoorlie240、Grafton215、Sandown Hillside208，後續需另外核實州別來源。

## 固定方法與結果

fresh dump遵守7個post-race extracted meeting exclusions，clean2455場；驗證仍固定9/4–10/14，
沒有因warmup排除而改窗口。六個時間窗，只用之前日期labels fit，ridge10／scale10不變。
基準在1483場／14361匹逐筆重播舊EXP10同race的deployed，最大score差0.0。
舊headline1493場不拿來與本輪比較。score code／六維權重／gain1.5全無生產修改。

| 配置 | Gold | Good位置 | Pass |
|---|---:|---:|---:|
| 現役資料＋原A1.5 | 289 | 392 | 747 |
| 原資料＋上一仗修正 | 291 | 394 | 751 |
| 補資料及配對＋原A1.5 | 289 | 394 | 749 |
| 補資料及配對＋上一仗修正 | 293 | 399 | 750 |

EXP12只補TAS：資料本身0/0/0，連上一仗修正+3/+2/+4。
EXP13補TAS及核實配對：資料本身0/+2/+2，連上一仗修正+4/+7/+3。
最後一臂相對補資料基準的上一仗邊際為+4/+5/+1，不把全部功勞歸給新feature。

QTL−Q：Gold +0.270pp CI[-0.133,+0.713]pp；Good +0.472pp CI[-0.070,+1.024]pp；
top5 pairwise AUC +0.001297 CI[-0.000359,+0.003075]。
date bootstrap2000 seed7、六時間塊；三候選×七指標Holm最小p=.735，沒有顯著WIN。
距離分層QTL−Q：短途645場0/+5/0、中距離665場+4/+1/+3、長途173場0/+1/0。
9–10匹一桶Gold−1／Pass−1，首選result-SP≥21桶Gold−1；並非所有cohort都升，沒有據此改參數。
完整cohort與beta、prior日期、來源hash在results及predictions；SP僅評估分層，不入模型。
原A剷除budget背景、單獨binding消融在paired-audit；沒有冒充完整§6功效研究。

純T、其餘neutral（未fit，不帶其他leaf）：舊新同297場／2193pairs的AUC .60306→.60214，
paired delta−.000912 CI[-.003963,+.001883]。新增覆蓋後不同cohort共3361pairs AUC.60711，
CI[.57862,.63629]；這支持存在速度訊號，**不能用不同cohort AUC宣稱signal變強**。
同pairs現役綜合baseline AUC .68719。舊EXP10的N_total .60762經可靠度／場內標準化與fit，
不能和本輪未fit raw-T的.60306混為同一估計量。

## 判決

官方判決器仍REJECT/leakage_audit_failed：歷史source availability未certify，窗口早已看過。
即使忽略此FLAG，主要及排序區間仍未證實改善，不能將+4/+7當作formal WIN。
**不經Central啟用候選，不部署dashboard、不改已知良好現役模型。**
這輪交付的是source reader、核實配對的研究版本、來源cache和可重跑證據，保存到non-main分支。
研究版不會自動刷新生產bundle；未稱工程／營運覆蓋已正式啟用。

## 重現

固定artifacts根：
`/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/AU-time-coverage-research`

使用`PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`。
1. `scratch/au_tas_time_source_20261015.py --cache <根>/tas-source --out <根>/tas-events.json`
2. `scratch/au_time_coverage_eval_20261015.py --fresh <根>/current-leaves.json --events <BASE>/AU-fulltime-implementation/seed-events.json --forms <BASE>/AU-fulltime-implementation/form-blocks.json --tas <根>/tas-events.json --out <根>/results.json`
3. 同上加`--rq-bindings`，out用`binding-results.json`（勿覆蓋12結果）。
4. `scratch/au_time_coverage_audit_20261015.py --predictions <根>/binding-results.predictions.json --prior <BASE>/AU-next-start-speed-research/results.predictions.json --tas-only <根>/results.predictions.json --out <根>/paired-audit.json`

BASE為上述根的parent；input SHA全記於結果。TAS重parse（加入finish/domain檢查後）events逐筆不變。
corpus-audit status ok（HOT/WARM已知artifact齊全）；六項source safety tests通過。
檢查命令及完整結果見`quick.log`、`unit-tests.log`、`full-check.log`及delivery manifest。
