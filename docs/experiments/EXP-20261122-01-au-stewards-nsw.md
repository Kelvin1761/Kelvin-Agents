# EXP-20261122-01 AU 上仗競賽主任報告（NSW）入分：大外冇遮擋／獸醫事故／受阻 —— 預先登記（2026-11-22，parse 結果之前寫）

- 起因：Kelvin 2026-11-22「go ahead」（改善次序第 1 項：競賽主任報告）。HKJC EXP-20261116-06（走外疊 +、醫療 −）holdout PASS 上線。
- 之前 AU：EXP-20261107-01（Racenet 舊評語 8,439 對）—— 受阻冇反彈（−0.77pp、市場高估）；大外冇遮擋 +5.79pp 但市場已計入；
  獸醫未測。08-05 起乾淨語料（Sportsbet）冇評語，所以用 Racing NSW 競賽主任 PDF（racingaustralia.horse/PostStewardsReports/DDMMYYYYCODE.pdf）。
- 覆蓋：47,780 匹入面上仗喺 NSW 嘅 10,093 匹（21%），448 份 PDF。
- 特徵（只睇**上仗**報告，報告喺上仗賽後出、早過今仗 → 賽前拎得到）：
  - **WIDE**：該駒段落有 "wide without cover"
  - **VET**：有 bled／lame／cardiac／irregular heart／poor recovery／respiratory／tied up／heat stress
    （"did not reveal any abnormalities" 唔算）
  - **TROUBLE**：checked／held up／crowded／steadied／slow to begin／began awkwardly／bumped／hampered（複製 EXP-20261107-01）
  - 上仗唔喺 NSW、或者報告冇該駒 = 0
- 幅度：walk-forward β（同 EXP-20261121-37：每賽日用之前賽日 logistic，β 限 [−20, 20]，頭 20 日 0）。
- 判決：`au_logloss_ruler.evaluate`，語料 `au-noise-20261113/BASE.json`（3,736 場），3 個 arm Holm。
- 預期方向（唔係判決條件）：WIDE +、VET −、TROUBLE ≈0 或 −。
- 唔准：改關鍵字表、改語料、改尺。PASS 都要 Kelvin 決定 + forward；live 要另寫抓 PDF 嘅排程（只 NSW）。

---

# 結果：**冇數據，冇判決**（2026-11-22）

- 場地代碼砌齊（`patches/au_stewards_nsw/venue_codes.json`，NSW 只差 Coonamble、Armidale）；10,093 匹（21%）上仗喺 NSW，要 448 份 PDF。
- 抓咗兩三份之後，`racingaustralia.horse/PostStewardsReports/*.pdf` 回 HTTP 200 但內容係「Are you human?」驗證頁 —— 448 份得 1 份真 PDF。
  **唔繞過防機械人機制**，即刻停咗。
- PDF 格式可以 parse（每駒一段「馬名 - 描述」；"wide without cover"、"bled from both nostrils"、"lame (2/5)"），用 macOS PDFKit（`pdftext.swift`）。
- Kelvin 2026-11-22：「但係得 NSW 搞唔掂」—— 其他州各自網站，NSW 只覆蓋 21%，**呢條路擱置**，等有官方 feed 再做。
