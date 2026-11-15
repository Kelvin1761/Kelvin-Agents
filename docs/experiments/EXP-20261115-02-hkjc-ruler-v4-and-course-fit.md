# EXP-20261115-02 HKJC 歷史回放尺 v4（Kelvin 決定）＋場地類型適性用新尺判

- **日期**：2026-11-15 ｜ **平台**：HKJC ｜ **決定**：把尺改動（獨立發佈）；場地類型適性 **REJECT（v4）**
- **把尺**：`docs/model-evaluation-contract.md`「HKJC 歷史回放尺 v4」；判決器 `hkjc_reflector/scripts/hkjc_replay_compare_v4.py`
- **Kelvin 2026-11-15**：揀「主指標改機率 log-loss；Gold／Good 改做 CI 下界唔可以明顯負（> −1pp）」

## 驗證把尺
A/A（S 版 vs S 版，dev）：Δlog-loss 0、CI 跨零 → **REJECT** ✅

## 場地類型適性（EXP-20261115-01 第 2 部分）用 v4 判（dev walk-forward；候選校準用全季版本，只影響 a、α）
| 指標 | 結果 |
|---|---|
| Δlog-loss（每匹） | −0.00020 [−0.00063,+0.00021]（好過 null 100%） |
| Δ場內 AUC | +0.0003 [−0.0012,+0.0019] |
| Gold | +0.16 [−0.45,+0.77] |
| Good | −0.36 [**−1.09**,+0.40] |
| capture@5 | +0.05 |
| 頭二選有中 | +0.64 [−0.08,+1.38] |
→ **REJECT**：log-loss CI 跨零、Good 下界啱啱過 −1pp。

## 要老實講
篩選嘅「模型之上 +0.08／SD」係對**場內排名百分位**（粗）；對完整 raw 分數，剩餘訊號真係好細 —— 唔單止係把尺問題，效果本身細。
新尺唔係放水；之後（19 組 leaf 重建）用 v4 判。
