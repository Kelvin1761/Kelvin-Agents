# EXP-20261116-20 預先登記：AU 末段扣位置（Lpos）forward 測試（只追蹤，唔郁發佈排名）

- **日期**：2026-11-16（Kelvin 經主 session 批准：「happy to have a 登記嘅前向測試」）。
- **來源**：[EXP-20261116-22](EXP-20261116-22-au-sectionals-deep-dive-results.md)：`Lpos` 喺現行模型之上有殘差資訊（Holm p 0.020），
  但 318 場量唔到排名改善（Gold MDE ~4pp）。呢個測試用**全新、之後先發生**嘅賽事判。
- **寫喺任何 forward 數據之前**，規格凍結；之後見到數據唔准改（Kelvin 嘅要求）。要改 = 開新 EXP、新 arm。

## 數據

- 抓取：每日 04:30（悉尼）新 launchd job `com.antigravity.au-wong-choi.mobile-sectionals`，
  抓**前一日至前 8 日**、賽日 ≥ 2026-11-17 嘅 AU 純種馬賽事 `sportsbetform.com.au/mobile/{eventId}/1/`（每場一版）。
  event ID 由主站 `AllRacing/{day}` 攞。每版隔 25 秒、非 200／逾時／內容過細即停、唔重試、每次最多 180 版、
  03:00 前或者 09:00 後唔開工（避開 22:00 evening job、10:00–16:00 refresh 同其他抓 sportsbetform 嘅工作）。
- 儲存：`<AU 資料根>/AU_Mobile_Sectionals/<賽日>/<eventId>.json.gz`（parse 結果）同 `.html.gz`（原檔）。
- 賽後先抓係安全嘅：EXP-20261116-19 證實舊賽事頁固定喺賽事日期（370 版 0 行 ≥ 賽日）；特徵仍然只用日期 < 今仗嘅行。

## 特徵（凍結）

每匹馬每仗（手機往績行 join 今仗 `Race N Formguide.md` 同馬同日嘅往績行）：

    本駒 L600 = Σ 200 × 3.6 / km/h（400m、200m、Fnsh 三格齊先有）
    Lr        = −(本駒 L600 − RaceL600)
    p800      = (800m 位置 − 1) / (馬數 − 1)
    Lpos      = Lr − (−1.1008497873571432 + −0.10976351609298357 × p800)   # 常數 = EXP-22 用 11-06 前 22,071 行 fit，凍結

`Lpos.avg4` = 最近 ≤4 仗有值嘅平均（日期 < 今仗）。冇值 = 場內 z 0。

## 兩個分數

- **baseline** = live 排名分（`Race_N_Logic.json` 儲存特徵，`au_walkforward_refit.exact_score`，同其他 AU forward 一樣）。
- **candidate** = baseline + **0.10** × 場內 pstdev(baseline) × 場內 z(`Lpos.avg4`)。
  0.10 = EXP-22 估計比率 0.102 向下取整，冇再調。

## 母體

賽日 ≥ 2026-11-17；有手機版、有 Logic、賽果齊（頭三同頭馬）；馬只計對到賽果嘅。場次按（日期、場次資料夾、場號）排序。

## 判決（凍結）

- **夠 2,500 場判一次並凍結**（`au-lpos-forward-status.json`）；夠數由 `au_forward_tracker` 推 primary Telegram。
- `model_evaluation_decision.evaluate_full_record(domain="au", mode="fixed_rule")`，ranking metrics
  `top3_capture_at5`、`ndcg_at5`、`top5_pairwise_auc`（同其他 AU forward 一樣）。
- 另報（描述，唔判）：短途 ≤1200m 同 >1200m 分開嘅 Gold／Good；有 `Lpos` 嘅馬比例。
- **未夠數唔睇賽果指標**：status 檔每晚只寫場數、覆蓋率、有幾多場排名會郁。
- 判 PRIMARY_WIN／RANKING_WIN → 交 Kelvin 決定係咪上線（要另一個改動，連 golden／data_contract）。其他 → 唔上線。
- 永遠唔會自動改模型。

## 洩漏

只用日期 < 今仗嘅手機行同 Formguide 行；常數係 EXP-22 嗰陣定（11-06 前資料）；冇今仗賠率；
baseline 用賽前儲存特徵重算。
