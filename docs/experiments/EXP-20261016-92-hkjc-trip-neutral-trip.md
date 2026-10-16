# EXP-20261016-92 — HKJC 沙田消耗分一律60消耗扣分豁免

- 日期：2026-10-16；平台：HKJC；baseline：`3083316d55fd35d798772514248ae2723e6b469b`。
- 假設：測沙田普通馬消耗分的邊際排名貢獻；winner／close_top3只取消符合條件往績的52／46→60扣分，neutral_trip則T一律60。
- 舊記錄：EXP-20260902-08、EXP-20260904-07、EXP-20260928-01；不是重試全T中性或反轉trip符號。
- 固定條件：沙田消耗分一律60。winner／close_top3要求日期嚴格早於今場、XW≥3、原標籤高／極高；其他資料缺失不猜。neutral_trip無須往績資格，所有沙田普通馬T=60。
- mode=fixed_rule；325場／33賽日，2026-04-19至2026-10-07；沒有fit或holdout調參，2026-10-11起forward未開。
- 家族修正後：**REJECT / primary_regression**；原始v3：REJECT／primary_regression。

| 指標 | baseline | candidate | 差 | 95%CI（pp） |
|---|---:|---:|---:|---:|
| gold | 44 | 48 | +4場 | [+0.000, +2.744] |
| good_positional | 81 | 79 | -2場 | [-1.524, +0.000] |

觸發1853匹次；完整排名改變129場，頭兩選成員變動15場。只取消扣分不足以保證有額外上名捕捉收益，不能將零變化說成規則無用。
- leakage-audit：FLAG（舊文字artifact賽前可用時間未全面認證）；日期／parser檢查及direct production parity通過。
- golden／data_contract：production未改；由檢查.sh核對，未record／calibrate新snapshot。
- 決定：今輪不作production promotion。只按完整家族修正後證據解讀，未merge／deploy任何候選model code。
- 公式、Holm、六時間塊、ranking power、cohorts、來源hash及重跑：見 [審計](../audits/hkjc-trip-forgiveness-20261016/README.md) 及 results.json。
