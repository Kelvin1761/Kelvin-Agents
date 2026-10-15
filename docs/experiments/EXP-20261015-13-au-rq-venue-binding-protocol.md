# EXP-20261015-13 — RQ 冠名場地配對正確性

在EXP-12結果已讀後，獨立登記資料修正，不能冒充12預先登記的來源。
不改權重、par、ridge、窗口、指標、正式判決規則。

缺值審計發現 Gold Coast 300、Cairns103、Warwick90筆最近正式賽未配對。
RQ source用冠名，form用簡稱。官方club頁明確連結：

- https://www.racingqueensland.com.au/racing/club-details/thoroughbred/gold-coast-turf-club
- https://www.racingqueensland.com.au/racing/club-details/thoroughbred/cairns-jockey-club
- https://www.racingqueensland.com.au/racing/club-details/thoroughbred/warwick-turf-club

只增加source-local lookup identity（不修改global normalize、不改source track par）：
`aquisparkgoldcoast -> goldcoast`、`ladbrokescannonpark -> cairns`、
`picklebetparkwarwick -> warwick`。同日期、race、距離、horse名仍必須完全一致。
Poly、synthetic、firststart前綴、Warwick Farm一律不得歸入這三個binding。
存在新舊key衝突直接raise；不挑選對模型有利的別名。

先讀三個binding可增加的identity數，無讀修正後KPI。
同EXP12四臂、同2455/1483場、同來源as-of；另外比較12的QT/QTL，隔離venue修正。
不得將已看過的窗口說成新holdout；原historical availability FLAG不因名稱修正清除。
若結果或source/gate不支持正式版，保存研究分支，不進main。
