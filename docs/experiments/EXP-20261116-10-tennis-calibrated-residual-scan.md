# EXP-20261116-10 — Tennis：以校準後機率做底，搵市場系統性偏差

- 日期：2026-11-16；平台：Tennis；類型：**唯讀研究**（冇改 live code）。
- Kelvin：「C 校準準咗……at least we should get as close as possible first and see how we can win」。
- 底：EXP-20261116-08 arm C（逐 family 市場錨定校準，dev ≤ 2026-10-15 fit；dev <50 行嘅 family 用去水市場）。
- 預先登記（`patches/tennis_calibrated_residual_20261116/scan.py` docstring）：殘差 r = 結果 − p；固定 7 類分層
  （family、賠率段、熱門／冷門、tier、tour、場地、開賽前幾耐定價）共 28 格；dev 篩選用 Bonferroni（0.05/28），
  而且格內 `p × odds > 1` 嘅注 dev ROI > 0 先入 holdout。

## 結果

- **dev 冇一格過 Bonferroni** → holdout 冇候選可以驗。名義上最接近嘅係 CHALLENGER：殘差 −0.041 [−0.072, −0.013]，
  即係校準後仍然高估，屬於「唔好買」，唔係機會。
- dev 入面 `p × odds > 1` 嘅 ROI 好睇（+20% 至 +80%），但嗰個係 in-sample（p 喺同一段 fit），**唔作數**。
- **holdout 整體**：3,760 行／1,505 場，殘差 +0.005 [−0.015, +0.024]；`p × odds > 1` 落 168 注 ROI **−7.2%**，
  盲買全部 −7.8% —— 等於盲買減少少，冇 edge。

## 判斷

校準後嘅模型已經「盡量貼近市場」，同市場之間冇量得到嘅系統性缺口。用而家有嘅欄位（family、價、tier、tour、
場地、時間）切，Sportsbet tennis props 冇軟位。要贏，只剩三條要新數據嘅路（同 EXP-20261110-03 一致）：

1. **外部參考價**（Betfair exchange／Pinnacle）：Sportsbet 價高過參考價先落。
2. **多莊比價**：同一個 p，揀最高價。
3. **價格移動／時間**：11-06 起精選場次每 30 分鐘抓價，累積夠先量得到「早落定遲落」。

## 限制

單一莊家、最後賽前價；dev 跨兩個 code 年代；ITF／UNKNOWN tour 混埋；28 格多重比較已用 Bonferroni。

## 重現

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 docs/experiments/patches/tennis_calibrated_residual_20261116/scan.py tennis-wong-choi/tennis_wc.db
```
