# EXP-20261101-38 上線：剷走證據厚度安全欄 + overlay 上 dashboard

- **判決記錄**：[results](EXP-20261101-38-au-overlay-audit-results.md)。
- **用戶決定（2026-11-01）**：「Agree with your 下一步計劃. We should either have a section that listed all these overlay or we should
  display them in the dimension that affects the scoring」。

## 改咗咩

1. **證據厚度安全欄停用**：`renderer.THIN_EVIDENCE_RAIL = False`，`ensure_verdict` 唔再對調頭 1／2。
   `_default_leaf_count`、觸發清單保留（`miss_autopsy` 用嚟標記證據薄嘅馬）。安全欄測試改為喺 `THIN_EVIDENCE_RAIL = True`
   之下行（保住重開時嘅行為），另加「預設設定唔會對調」測試。
2. **overlay 顯示**（排名唔變）：
   - 報告加 `<!-- wc-au-overlays:v1:… -->`（`renderer.overlay_metadata`）：逐匹七維分、三個 overlay 數值同相關維度、
     距離轉變罰分有冇觸發。單元測試釘住「七維 + overlay = 綜合分」。
   - Dashboard 後端 `au_overlay_metadata.read_overlay_metadata` → `horse.score_overlays`（名對唔上就唔掛）。
   - 前端：七維矩陣下面加「額外調整」：濕地往績調整（場地與地況適性）、班次證明（官方評分對位）、逐駒全程速度（速度考驗背景），
     加一行「原始總分 ＝ 七維 ＋ 調整」；距離轉變罰分顯示為「已喺狀態與穩定性扣 5 分（唔再另加）」。
   - 真數據預覽（2026-10-31 Alice Springs 6 場重新渲染）：Voronya「原始總分 83.66 ＝ 七維 82.73 +0.92 調整」對得上；
     手機闊度 375px 冇橫向捲動。
3. **模型說明**：`explain_model.py` overlay 表以前錯縮排喺 `if adjustments:` 入面，AU 只印標題冇表 —— 修好；
   `scoring.RANKING_OVERLAYS` 補返濕地 overlay（以前得兩個）。

## 預期影響

- 排名：只係首選／次選次序喺觸發安全欄嘅場次（約 14%）還原為能力分次序。歷史 3,246 場：首選上名率 +1.17pp [+0.03, +2.34]，
  首選頭馬 +0.43pp（CI 跨零）；Gold／Good 結構上不變（頭 2／頭 4 成員唔變）。
- 顯示：每匹馬多咗 overlay 細項，總分可以由畫面加返出嚟。

## 舊報告

已發佈嘅舊報告冇 overlay block，dashboard 唔顯示呢個區塊（唔會估）；新分析或者重新渲染之後先出現。
