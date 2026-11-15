# EXP-20261115-15 — 老馬贏後、騎師升降級、評分跌返贏馬分 —— holdout 全 REJECT；兩個 pattern 改做顯示標籤＋forward shadow

- 日期：2026-11-15｜Kelvin「正式測老馬贏後扣分；dig 降班＋換騎；dig 評分（三至五班）」
- 特徵：`docs/experiments/patches/hkjc_patterns/feat2.py`（HKJC 馬匹頁＋賽果，as-of）；老馬 = 在港 ≥4 年或 ≥35 仗；高班 = 評分 ≥95 或一二班。
## 診斷（dev 殘差）
老馬贏後 −11.85（非高班 −11.2、高班 −16.7 n 32 → 高班例外唔成立）；騎師升級（入位率 +5pp）冇降班 +2.45、降班＋騎師升級 +4.20、騎師降級 −2.74、
單純降班 −1.70（唔顯著）→ 降班＋換騎嘅訊號係騎師質素；評分跌返贏馬分 +1.41、降班＋跌返 +5.16、降班換騎＋跌返 +6.0。
## 正式（walk-forward；家族 6 個，Holm）
| 候選 | β（raw） | dev Δlog-loss | holdout Δlog-loss | 判決 |
|---|---|---|---|---|
| C1 老馬贏後 | −5.19 | −0.00032 ✅ | −0.00009 [−0.00037,+0.00021] | REJECT |
| C2 老馬贏後（非高班） | −4.62 | −0.00024 ✅ | −0.00012 [−0.00036,+0.00013] | REJECT |
| C3 騎師升降級 | +1.2／+2.5／−1.2 | −0.00015（Gold −0.88） | 冇開 | REJECT |
| C4 評分跌返贏馬分 | +1.02 | −0.00021 ✅ | +0.00010（頭二 −0.58） | REJECT |
| C5 降班＋跌返 | +2.56 | −0.00014 | 冇開 | REJECT |
| C6 合併 | — | −0.00060 [−0.00125,+0.00005] | 冇開 | REJECT |
## 持續性（候選 REJECT 之後嘅診斷）
| pattern | dev 殘差 | holdout 殘差 |
|---|---|---|
| 老馬贏後（非高班） | −11.2 | −9.7 [−17.9,−0.8] |
| 降班＋評分跌返贏馬分 | +5.2 | +5.2 [+0.6,+10.2] |
| 評分跌返贏馬分 | +1.4 | +0.1（冇咗） |
→ 兩個 pattern 真但罕見（每季 ~100 匹），排名層冇功效。**Kelvin 2026-11-15：顯示標籤＋forward shadow 兩樣都做**
（`hkjc_racing_engine/form_patterns.py`、`tags._form_pattern_tags`、`hkjc_arm_form_patterns_shadow.py`、forward `form_patterns_shadow` 150 場）。
live 定義由 Logic 計（total_starts ≥35；贏馬分＝近 6 仗＋`HKJC_Sections/win_ratings.json`）；近 12 賽日觸發率 1.50%／1.57%（回放 0.7%／1.4%）。
