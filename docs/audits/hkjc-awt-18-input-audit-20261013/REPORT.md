# HKJC 18場泥地輸入覆蓋審計

18場全部納入，213個賽果對齊runner records。只讀日期、場地、馬號同原Logic賽前輸入，冇讀當場賽果或搜尋權重。保留原隔離日期。

| 項目 | runner records |
|---|---:|
| matched_runners | 213/213 |
| surface_text_available | 32/213 |
| surface_positive_sample | 26/213 |
| foreign_surface_fallback | 0/213 |
| speed_neutral | 5/213 |
| foreign_rows_present | 182/213 |
| hk_starts_metadata | 213/213 |

以上係stored Logic覆蓋，唔代表原排位／profile冇資料。speed_score缺key亦計中性，需分開缺key同真60；surface文字存在亦唔等於PIT已證明。

18場可以用嚟先搵資料鏈問題、預先定義泥地假設。唔用隔離賽果調參；現時亦未過EXP-20260928-05嘅30場promotion樣本要求。

逐場來源hash、馬號、原surface evidence見coverage.json。

## 2026-10-14更正

原surface_positive_sample=26使用錯誤regex，讀到第一個草地樣本，唔係target泥地；呢個指標作廢。正確stored泥地有效樣本>0係18/213。Foreign rows present=182只係list非空，唔代表真正海外泥地往績。詳見[來源追蹤](../hkjc-awt-source-trace-20261014/REPORT.md)。
