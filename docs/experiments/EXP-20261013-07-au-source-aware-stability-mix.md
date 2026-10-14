# EXP-20261013-07 — 真PQ同fallback分開嘅最小配比設計

## 候選結果未開前登記

用戶追問PQ可否係強signal但需要更好設計。EXP06來源診斷已曝光，完整PQ同fallback
同場AUC分別約.645／.540；因此提出單一最小候選：
只對source=class_adjusted_margin_field_relative或sportsbet_complete_form_archive_recovery
用FORM40／PQ60，其餘保留原FORM60／PQ40。來源係引擎實際provenance，不靠分數
等於60、賠率、賽果或phase決定。不是之前EXP04 fallback→100%FORM、缺FORM→100%PQ。

Baseline與uniform40皆沿用EXP06 main a0bf0f38完整production projections；
同2533固定eligible，原始overlays、rounding、grade、安全欄全部不變。
只一個新arm，不掃ratio、run-count或age門檻。報全期、原dev、後段、六日期塊、
field/SP cohort及相對uniform40嘅邊際。若失敗照記。

**證據層級：data-selected exploratory counterfactual**。候選係由同一語料診斷提出，
不能用本輪數字宣稱獨立out-of-sample改善、不能用fixed_rule自動promotion。
若有正面結果，先凍結候選設計，再交真正walk-forward train-only calibration及
新日期前瞻確認；不得重開舊後段揀參數。本轮不改live、無push或新增排程。

## 結果與判決

| 固定2533場、相對main 60／40 | Gold淨增 | Good淨增 |
|---|---:|---:|
| 一律40／60 | +5 | −2 |
| 完整PQ用40／60，其餘60／40 | +4 | +5 |

來源分流相對baseline：Gold day-bootstrap95% CI [−0.699,+0.971]pp；
Good [−0.525,+0.917]pp。原dev1762場Gold+1／Good+6；後段771場Gold+3／Good−1。
六日期塊Gold／Good淨數依次+8/+2、−8/−1、0/+4、+1/+2、+5/+1、−2/−3；
兩個primary各4/6非負，但全期NDCG下降0.0775pp、平均top3模型排名差0.00447。
相對uniform40 Good+7，CI [+0.075,+0.510]pp；此為同資料選出設計後嘅邊際診斷，
不能因CI轉正就聲稱獨立驗證。後段Good由−7收窄到−1，但仍未轉正。

**判決：有來源分流方向證據，未證實勝過live baseline；不promotion、不改live。**
可重現command：`PYTHONDONTWRITEBYTECODE=1 .venv-au-ml/bin/python docs/experiments/patches/au_source_aware_mix.py`。
input為EXP06 production projections及逐馬來源metadata，JSON結果存
`scratch/au_fixed_40_60_20261013/source_aware_mix.json`；baseline main SHA
`a0bf0f388bd6053641cc08d41b2915ee73bb7c5f`。來源條件凍結於本記錄，
新日期測試前須保存原始賽前來源快照；今輪重播不是完整歷史PIT證明。
