# EXP-20261015-12 — 補可靠逐駒時間、乾淨語料重測與條件發布

用戶授權：採用上一仗全程方向，先補可靠資料／覆蓋，結果好先正式版。
基準`9f0360c7`，包括AU PIT修正及7個post-race extraction排除；不得重加排除場次救候選。
原EXP-08至11為舊基準探索結果，不作本次正式發布證據。

## 新資料：Tasracing 官方 Daily Sectionals 2026

官方2025-12-24公告：2026起以race vision提供每匹完賽馬全程、200m分段及途中位置。
目錄由官方FORMPLUS公開前端的calendar/races/WordPress report API解析，不猜meeting ID。
原始Excel由report的`thoroughbred_sectionals_csv`附件連結取得；只讀、不修改來源。
來源報告、API metadata、raw hash、下載capture及附件published/modified時間一併保留。
時間只用逐駒`IVRTIME`，不用只存在於勝方行的`OFFTIME`補其他馬。
校驗日期／race／距離／馬名、total−L800=TO800、末四段合計=L800及最少3有效馬。
trial/DNS/缺時間不填；表內going與API有衝突時採官方raceTiming（記衝突）。
Devonport只在API venue=Devonport、附件venue=Devonport Tapeta Synthetic、官方going=Synthetic
同meeting ID明確連結時，source-local binding到現有form key `devonportsynthetic`；
不是全域模糊alias，不跨layout。其他未知venue binding直接保留unmatched。
未知格式或source時鐘不符不猜；沒有個別時間的winner／margin推算一律不用。

## 固定評估

語料：新main fresh dump，2026-08-05至10-14，遵守新排除名單。驗證日期仍固定
2026-09-04至10-14，保持原窗口邊界，不因08-12被排除而把驗證開始日向後推。
每7個原驗證賽日一窗，fit只收之前日期；舊窗已看過，本輪仍不是fresh forward holdout。
TAS source用report附件date/modified皆早於target悉尼00:00者；capture與publication分開，
metadata不冒充當年的raw capture。原RQ歷史availability FLAG亦不偷偷清除。

只試data A及latest B兩項，四臂：

- Q：原RQ source＋現役近六仗A×1.5，重播原算法。
- QL：Q＋最近一場全程修正；固定EXP-10 pairwise logistic ridge10、scale10。
- QT：RQ+TAS source＋相同近六仗A×1.5；無新排名feature。
- QTL：QT＋相同latest全程修正。latest必須真最近正式賽，不跳缺值。

QL−Q隔離latest；QT−Q隔離data；QTL−QT量新資料下latest邊際；QTL−QL量data邊際。
不採用本次近2／3仗多參數候選，不再重配六維／gain／lambda。
Context standard保持原公式，加入新course來源不改原par算法；metadata不夠者中性／拒絕。
比較使用同一批當前race，不以有時間subset篩選headline；純AUC才用相同observed pairs。
canonical Gold/Good/Pass及五ranking metrics、date bootstrap2000 seed7、六時間塊、
Holm三候選×七metrics；field/distance/venue/going/result-SP分層（SP只作評估）。
先做原A移除budget背景，不把它當latest/data完整§6預算；無完整功效證據不報RANKING_WIN。
baseline before change、來源品質、評分不變控制、時間／future append測試均需通過。

## 發布條件

只在正確性、source availability、canonical primary/ranking／cohort與Central gate都支持時，
才做獨立exact-scope正式release，更新golden/calibration/generated docs及dashboard。
未通過則保存新來源adapter、研究與結果到non-main分支，說明差距，不能只憑點估計部署。
若新來源只能讀到舊樣本、無法持續刷新或跨來源時間偏差未釐清，不能宣稱覆蓋已修好。
