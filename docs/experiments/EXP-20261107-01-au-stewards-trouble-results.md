# EXP-20261107-01 結果：「受阻」唔預測反彈；「大外冇遮擋」勉強過預先登記門檻，但市場已經計咗

- **預先登記**：[protocol](EXP-20261107-01-au-stewards-trouble-protocol.md)（commit 71cbd54a，量度之前）。
- **harness**：`docs/experiments/patches/au_stewards_trouble_test.py`；輸出 `au_stewards_trouble_result.json`。
- **命令**：`PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/au_stewards_trouble_test.py --boot 2000 --out …`
- **數據**：8,440 份 Formguide；Racenet 往績有 `Stewards:` 欄 49,633 仗（33,038 有文字）；Sportsbet 往績 95,753 仗；
  配對 P→C 8,439 對（P 日期 2024-04-13 → 2026-07-25），其中 5,200 對 P 有評語。
- **對接核實**：（馬名，日期）兩邊場地一致 8,477／8,701；唔一致嘅 224 個全部係 "First Start <場地>" 前綴，同一場賽事。

## 結果（主要群體：上仗名次 ≥4；結果 = 今仗入位；cluster bootstrap 2,000，以馬為單位）

| 標籤 | n | E1 按上仗表現校正 | Holm p | E2 按今仗 SP 校正 |
|---|---:|---|---:|---|
| **INTERF** 途中受阻 | 661 | **−0.77pp** [−5.17, +3.63] | 0.61 | −3.85pp [−7.60, +0.46] |
| START 出閘 | 1,169 | +1.34pp [−2.00, +5.25] | 0.42 | −0.77pp [−4.12, +2.57] |
| **WIDE** 大外冇遮擋 | 461 | **+5.79pp** [+0.47, +10.97] | **0.045** | +0.27pp [−4.42, +4.94] |
| VET（只報告） | 112 | +14.00pp [+4.35, +24.91] | — | +4.34pp [−3.94, +14.61] |

全部 P（次要）：INTERF +0.05pp、START +0.67pp、WIDE +2.48pp [−1.55, +6.55]（唔顯著）；INTERF E2 **−3.06pp [−5.93, −0.21]**。

## 判讀

1. **途中受阻（外部分析嘅主要論點）：冇訊號。** 上仗被記錄受阻、跑輸嘅馬，今仗入位率同「上仗冇評語、表現相若」嘅馬一樣。
   市場反而**高估**佢哋（E2 −3.1 至 −3.9pp）—— 投注者寬恕過頭。即係「將受阻記錄接入 Facts 去扶高排名」會做錯方向或者冇效。
2. **大外冇遮擋：按預先登記門檻「值得跟進」**（Holm 0.045 < 0.05、+5.79 ≥ +2.0），但要打折扣：
   - 剛剛過線；全部 P 群體唔顯著。
   - E2 ≈ 0：市場已經完全計入。我哋模型輸市場（AUC 0.6530 vs 0.7393），所以對**我哋**仍可能有用，但唔係市場冇嘅資訊。
   - E1 只校正上仗；模型用嘅資訊多過上仗，真正邊際貢獻要喺模型入面量（未做）。
3. **VET +14pp 唔可信**：抽樣見到 "did not reveal any abnormalities" 被誤標（regex 漏咗呢個否定寫法），而且 90% 係大敗後，
   似係「大敗有原因 → 回歸」。預先登記寫明只報告，唔跟進。
4. 「Bumped shortly after the start」之類冇分類，兩邊都唔入（1,725 對「其他」）—— 預先登記規則，冇改。

## 決定

- 受阻／出閘：**停**，唔寫 scraper，唔改 Facts 計分。
- 大外冇遮擋：只係「值得跟進」，唔係上線。跟進前提係有 **live 來源**（Sportsbet 冇；WA = RWWA、NSW = RA PostStewardsReports PDF，
  逐州未齊），然後先做 leakage-audit + model-regression-gate（要喺模型排名之上量邊際貢獻）。成本高、預期效果細，交俾 Kelvin 決定。
- **冇改任何模型 code。**

## 洩漏檢查

P 評語喺 P 賽後公佈、C 之前拎得到 ✅；C 嘅 SP 只用於 E2 校正 ✅；冇用 Racenet 年代評分輸出 ✅。
