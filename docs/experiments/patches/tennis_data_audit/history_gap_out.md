# 網球往績缺口及 composite 排名審計

生產資料庫唯讀；以 match_id 連上 Sportsbet 價格之 Sportsbet 場次為母體。賽日前 ACTIVE 往績，事後回溯；同一球員可出現於多級別。每級按排序後 ID、seed 20261127 抽最多 80 人。

A 為機械相似候選，並非身份確認；B = 原文無姓但 DB 有相似名（無符合 A 往績），C = 原文及 DB 均無相似名；D = 原文有姓、姓名不能解析或證據不足。B/C 互斥，空白原文無法搜尋，B/C 僅代表可讀原文；原文無姓不證明賽事沒抓取；姓氏以最後一個 token 近似，倒轉／多字姓可能誤判。原文命中只代表同姓，並非同一人。

原文範圍：2026-09-28 至 2026-11-26 成功抓取 composite／tennisexplorer match_history；226 筆，無效 JSON 188 筆。

## 分類比例

| 級別 | 母體不同球員 | 樣本 | A | B | C | D |
| --- | --- | --- | --- | --- | --- | --- |
| ITF | 676 | 80 | 60 (75.0%) | 2 (2.5%) | 1 (1.2%) | 17 (21.2%) |
| UTR | 204 | 80 | 73 (91.2%) | 0 (0.0%) | 3 (3.8%) | 4 (5.0%) |
| Challenger | 150 | 80 | 36 (45.0%) | 0 (0.0%) | 0 (0.0%) | 44 (55.0%) |

### ITF A（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 22473 | Salma Djoubri | 23551 | 2026-11-13 | 相似 ID 8147 Djoubri S.；賽日前往績 2026-01-19 |
| 25149 | Jayson Blando | 23164 | 2026-11-09 | 相似 ID 7898 Blando J. / Blando M.；賽日前往績 2026-01-14 |
| 19485 | Valentino Grippo | 24243 | 2026-11-20 | 相似 ID 7741 Centurion / Grippo V.；賽日前往績 2026-01-13 |
| 20131 | Ramiro Amarilla | 23940 | 2026-11-17 | 相似 ID 9765 Amarilla R.；賽日前往績 2026-02-16 |
| 24311 | Zichen Shao | 23277 | 2026-11-10 | 相似 ID 10851 Shao Z.；賽日前往績 2026-03-08 |

### ITF B（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 1474 | Xinle Geng | 23407 | 2026-11-11 | 原文無姓 geng；相似 ID 25229 Xinle Geng（無符合 A 往績） |
| 21879 | Khomtat Kitthachok | 23776 | 2026-11-15 | 原文無姓 kitthachok；相似 ID 1729 C Chaiyarin / K Kitthachok（無符合 A 往績） |

### ITF C（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 27193 | Haqim Kamal | 24115 | 2026-11-18 | 原文無姓 kamal；DB 無機械相似名 |

### ITF D（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 27431 | Reva/Reva | 24760 | 2026-11-25 | 雙打組合，姓名無法按單打球員可靠比對 |
| 27255 | Malirz/Martinez | 24266 | 2026-11-20 | 雙打組合，姓名無法按單打球員可靠比對 |
| 26762 | Arce Fernandez/Belda | 23316 | 2026-11-11 | 雙打組合，姓名無法按單打球員可靠比對 |
| 27523 | Medvedeva/Shkutova | 24881 | 2026-11-26 | 雙打組合，姓名無法按單打球員可靠比對 |
| 26933 | Gadecki/Wan | 23675 | 2026-11-14 | 雙打組合，姓名無法按單打球員可靠比對 |

### UTR A（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 27244 | Tomas Pinho | 24247 | 2026-11-20 | 相似 ID 9482 Pinho T.；賽日前往績 2026-02-10 |
| 24939 | Imran Daniel Abdul Hazli | 23239 | 2026-11-10 | 相似 ID 14604 Abdul Hazli I.；賽日前往績 2026-05-24 |
| 20941 | Sofiia Nagornaia | 24369 | 2026-11-21 | 相似 ID 10580 Nagornaia S.；賽日前往績 2026-03-02 |
| 26721 | Andrew Li | 23348 | 2026-11-11 | 相似 ID 6767 Li A.；賽日前往績 2026-01-05 |
| 22858 | Nathaniel Suh | 24497 | 2026-11-22 | 相似 ID 16048 Suh N.；賽日前往績 2026-06-15 |

### UTR B（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |

### UTR C（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 27410 | Mineth Nawarathna | 24704 | 2026-11-24 | 原文無姓 nawarathna；DB 無機械相似名 |
| 26791 | Emma Maria Ansorge | 23354 | 2026-11-11 | 原文無姓 ansorge；DB 無機械相似名 |
| 26499 | Cylova Zuleyka Hukmasabiyya | 23102 | 2026-11-09 | 原文無姓 hukmasabiyya；DB 無機械相似名 |

### UTR D（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 27111 | Jules Caby | 23994 | 2026-11-17 | 原文同姓 caby：raw 29597/tennisexplorer/2026-11-20；身份未確認 |
| 27100 | Chiharu Abe | 23963 | 2026-11-17 | 原文同姓 abe：raw 29424/composite/2026-11-19；身份未確認 |
| 26924 | Leon Nickel | 23653 | 2026-11-14 | 原文同姓 nickel：raw 29597/tennisexplorer/2026-11-20；身份未確認 |
| 26913 | Cade Fernando | 23635 | 2026-11-14 | 原文同姓 fernando：raw 30479/tennisexplorer/2026-11-24；身份未確認 |

### Challenger A（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 18531 | Odysseas Geladaris | 23167 | 2026-11-09 | 相似 ID 10762 Geladaris O.；賽日前往績 2026-03-04 |
| 25794 | Nicolas Hollender | 23846 | 2026-11-16 | 相似 ID 8469 Hollender N.；賽日前往績 2026-01-25 |
| 27241 | Joao Couto Loureiro | 24571 | 2026-11-24 | 相似 ID 4590 Joao Victor Couto Loureiro；賽日前往績 2026-02-11 |
| 272 | Darwin Blanch | 24195 | 2026-11-19 | 相似 ID 8111 Blanch D.；賽日前往績 2026-01-19 |
| 18381 | Gavin Young | 24261 | 2026-11-20 | 相似 ID 6946 Young G.；賽日前往績 2026-01-06 |

### Challenger B（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |

### Challenger C（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |

### Challenger D（最多五例）

| 球員 ID | 姓名 | 場次 ID | 比賽日 | 證據 |
| --- | --- | --- | --- | --- |
| 26797 | Dev/Sinha | 23362 | 2026-11-11 | 雙打組合，姓名無法按單打球員可靠比對 |
| 26799 | Hsu/Zhu | 23364 | 2026-11-11 | 雙打組合，姓名無法按單打球員可靠比對 |
| 27107 | Melnic/Sinclair | 23988 | 2026-11-17 | 雙打組合，姓名無法按單打球員可靠比對 |
| 27476 | G Cadenasso / J Vasami | 24844 | 2026-11-26 | 雙打組合，姓名無法按單打球員可靠比對 |
| 27496 | D Kuzmanov / M Geerts | 24863 | 2026-11-26 | 雙打組合，姓名無法按單打球員可靠比對 |

## 抓取範圍及排名程式

- `tennis-wong-choi/src/tennis_wc/sources/providers/tennisexplorer_provider.py:29` 使用 results `type=all`，第 431–439 行逐日下載；程式無 ITF／UTR 篩選，參數不能證實網站實際包括全部 ITF 或 UTR。composite 歷史由 ESPN 提供（`providers/__init__.py:35-36`），不等同 TennisExplorer 頁面。
- `sources/ingest_rankings.py:65-68,174-210,230-237` 用當前 provider 抓取，按 row.raw.source 將官方及 Sackmann 排名寫成實際來源，只有其他來源才標 composite；因此 composite 標籤停止不等於抓取停止。`sources/providers/__init__.py:19,47-72` composite 優先官方、後備 Sackmann；`run.py:80-92` 每日仍呼叫。排名來源標籤由寫入路徑決定，須核對 raw receipt。

## 排名影響

composite 球員最後日期與各其他來源最後日期逐人比較；同日其他來源不算較新。只計 DB 有紀錄，不保證現時排名讀取符合時效或 receipt。
符合「沒有其他較新來源」：975 人；其中完全只有 composite：672 人。

| 11月定價場次級別 | 受影響不同球員 | 至少一人受影響場次 | 受影響球員場次 | 只有 composite 球員 | 只有 composite 場次 |
| --- | --- | --- | --- | --- | --- |
| Challenger | 6 | 8 | 8 | 4 | 6 |
| ITF | 26 | 32 | 34 | 21 | 26 |
| UTR | 19 | 52 | 53 | 17 | 49 |

各級別球員可重複；場次按 match_id 去重，球員場次每場最多兩人。

## 10-28 至 11-02 排名相關日誌

符合條件 22 行；以下每天首個 WARNING，原文截取排名部分。

- [2026-10-28T09:23:04+11:00] WARNING: 3 data source(s) failed: rankings_atp, history_lowtier, slate_integrity. Details: [{"error":"provider player identity changed: composite/uts:52300: 'Aleksandr Shevchenko' -> 'Alexander Shevchenko'","source":"rankings_atp"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"},{"error":"held fixtures: [{'match_id': 22057, 'issues': ['fixture_already_disputed']}]","source":"slate_integrity"}]
- [2026-10-29T09:24:41+11:00] WARNING: 2 data source(s) failed: rankings_atp, history_lowtier. Details: [{"error":"provider player identity changed: composite/uts:52300: 'Aleksandr Shevchenko' -> 'Alexander Shevchenko'","source":"rankings_atp"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"}]
- [2026-10-30T09:26:33+11:00] WARNING: 4 data source(s) failed: rankings_atp, rankings_wta, history_lowtier, slate_integrity. Details: [{"error":"ranking identity holds: imported=2153 held=7 raw_response_id=25462 hold_response_id=25463; first: provider player identity changed: composite/uts:52300: 'Aleksandr Shevchenko' -> 'Alexander Shevchenko'","source":"rankings_atp"},{"error":"ranking identity holds: imported=1523 held=19 raw_response_id=25464 hold_response_id=25465; first: canonical player identity changed: 3441 -> 858: 'Yexin Ma' -> 'Ye Xin Ma'","source":"rankings_wta"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"},{"error":"held fixtures: [{'match_id': 22294, 'issues': ['fixture_already_disputed']}]","source":"slate_integrity"}]
- [2026-10-31T09:31:28+11:00] WARNING: 3 data source(s) failed: rankings_atp, rankings_wta, history_lowtier. Details: [{"error":"ranking identity holds: imported=2289 held=6 raw_response_id=25822 hold_response_id=25823; first: canonical player identity changed: 25294 -> 1829: 'Diego Dedura' -> 'Diego Dedura'","source":"rankings_atp"},{"error":"ranking identity holds: imported=1523 held=19 raw_response_id=25825 hold_response_id=25826; first: canonical player identity changed: 3441 -> 858: 'Yexin Ma' -> 'Ye Xin Ma'","source":"rankings_wta"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"}]
- [2026-11-01T09:26:33+11:00] WARNING: 3 data source(s) failed: rankings_atp, rankings_wta, history_lowtier. Details: [{"error":"ranking identity holds: imported=2289 held=6 raw_response_id=26011 hold_response_id=26012; first: canonical player identity changed: 25294 -> 1829: 'Diego Dedura' -> 'Diego Dedura'","source":"rankings_atp"},{"error":"ranking identity holds: imported=1523 held=19 raw_response_id=26014 hold_response_id=26015; first: canonical player identity changed: 3441 -> 858: 'Yexin Ma' -> 'Ye Xin Ma'","source":"rankings_wta"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"}]
- [2026-11-02T09:34:10+11:00] WARNING: 3 data source(s) failed: rankings_atp, rankings_wta, history_lowtier. Details: [{"error":"ranking identity holds: imported=2289 held=6 raw_response_id=26183 hold_response_id=26184; first: canonical player identity changed: 25294 -> 1829: 'Diego Dedura' -> 'Diego Dedura'","source":"rankings_atp"},{"error":"ranking identity holds: imported=1523 held=19 raw_response_id=26186 hold_response_id=26187; first: canonical player identity changed: 3441 -> 858: 'Yexin Ma' -> 'Ye Xin Ma'","source":"rankings_wta"},{"error":"provider player identity changed: tennismylife_history/KE64: 'Toby Samuel' -> 'Stefan Kozlov'","source":"history_lowtier"}]

排名資料日期與寫入日期不同；身份 hold 可部分寫入，單靠日誌不能推斷 composite 停止更新的根因。
