# EXP-20261107-01 預先登記：上仗競賽主任「受阻」評語 → 今仗有冇跑贏預期

- **日期**：2026-11-07（寫喺抽數同量度之前）；**平台**：AU；**類型**：診斷（唔改模型）。
- **起因**：外部分析指 2026-11-07 Ascot R10 #8 Snitzalatte、#9 September Born 上仗受阻但 Facts
  「備註／寬恕」欄空白。核實：Formguide `Stewards:` 由 2026-08（轉 Sportsbet）起 0% 有內容；
  Racenet 年代（2024-06 至 2026-07）去重後約 2.5 萬仗有評語。
- **搜索過嘅舊記錄**：EXP-20260907-02（健康分冇來源；量嘅係 Sportsbet 年代，所以 0%）、
  EXP-20260908-01（由走位軌跡推導寬恕，三個標籤方向全部同寬恕相反）、EXP-20261010-03（HKJC trouble forgiveness）、
  memory `au-stewards-reports-source-found`、`au-late-fade-is-redundant-with-form`。
  **未測過嘅係：用真嘅競賽主任文字。**

## 問題

上仗被競賽主任記錄受阻嘅馬，今仗入位率有冇高過「佢上仗表現所暗示嘅水平」？
有 → 值得搵 live 來源（WA RWWA、NSW PDF…）再過 model-regression-gate；冇 → 停，唔寫 scraper。

## 數據（固定）

- **曝露（上仗 P 嘅評語）**：資料根所有 `*Formguide.md` 入面嘅 Racenet 格式往績（有 `Stewards:` 行，
  值係 `None` 或文字）。以（正規化馬名，日期）去重；同一仗多份副本，有文字嗰份優先。
- **表現（P 同今仗 C 嘅名次、輸距、馬匹數、SP）**：Sportsbet 格式往績行（`finish:a/b`、`margin:`、`starters:`、`Flucs:` 最後一個價）。
  以（正規化馬名，日期）去重。試閘（`(TRIAL)`）一律剔除。
- **配對**：同一匹馬喺 Sportsbet 數據入面連續兩仗正式賽 P→C，間隔 ≤180 日；P 要喺 Racenet 數據有 `Stewards:` 值。

## 標籤（逐句分類；一仗可以多過一個）

句子含 `jump|start|began|begin|away|stride` → 只計 **START**，唔計 INTERF。

| 標籤 | 規則（大小寫不拘） |
|---|---|
| **INTERF** 途中受阻 | `checked|crowded|inconvenienced|held up|blocked|steadied|tightened|clipped|hampered|carried (out|in|wide)|squeezed|denied|unable to obtain|awkwardly placed|bumped|made contact|struck|lost ground|lost its footing|severely` |
| **START** 出閘 | `slow to begin|began (awkwardly|only fairly|poorly)|slowly away|slow into stride|blundered|commenced awkwardly|dwelt|missed the start|bumped (on jumping|at the start|at start)|on jumping|crowded on jumping|hampered on jumping` |
| **WIDE** 大外冇遮擋 | `wide (and )?without cover|(three|four|3|4)[- ]wide|raced wide|very wide` |
| VET 獸醫（只報告） | `lame|bled|blood in|cardiac|arrhythmia|roar|respiratory|sore|abnormal`（排除 `no abnormalit`、`no abs`、`passed fit`） |
| **NONE** 對照 | `Stewards: None` |

有評語但三個主要標籤都唔中嘅（例如 keen、laid in、COT）唔入對照，另列。

## 主要群體同結果

- **主要群體**：P 名次 ≥4（上仗跑輸）。次要：全部 P。
- **結果**：C 入位（名次 ≤3）。
- **E1 主要（按上仗表現校正）**：分層 = P 名次百分位（4 桶）× P 輸距（≤1、1–3、3–6、>6 L）× C 馬匹數（≤8、9–12、≥13）。
  超額 = 觀測入位率 − Σ（同層 NONE 入位率 × 該標籤喺嗰層嘅數目）／總數。
- **E2 次要（按 C 嘅 SP 校正）**：分層 = C SP 桶（<3、3–5、5–8、8–13、13–21、≥21）× C 馬匹數桶。
  量市場有冇已經計入，唔係判決依據。
- **CI**：以馬為單位 cluster bootstrap 2,000 次，95% percentile；層喺每次重抽重新計。

## 判決（預先固定）

- 主要假設三個：INTERF、START、WIDE 嘅 E1 超額 > 0。Holm（三個）調整 bootstrap 單邊 p。
- **值得跟進**：INTERF 或 WIDE 或 START 任何一個 Holm 後 p < 0.05 **而且** E1 超額 ≥ +2.0pp。
  跟進 = 搵 live 來源 + 正式 feature 測試（leakage-audit、model-regression-gate），**唔係直接上模型**。
- 其他情況：停，記錄。超額為負就照記（同 EXP-20260908-01 一樣，代表標籤量緊能力）。
- 唔會因為結果再改標籤 regex、分桶或群體。如果發現 parser 錯，修 parser 後全部重跑並喺結果寫明。

## 洩漏檢查

- P 嘅評語喺 P 賽後公佈，C 之前一定拎得到 ✅。
- C 嘅 SP 只用喺 E2 校正，唔做特徵。
- 唔用任何 Racenet 年代嘅評分輸出（舊語料係賽後重評分，`au-archive-rescored-post-race`）。
