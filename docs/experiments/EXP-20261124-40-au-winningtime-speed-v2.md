# EXP-20261124-40 AU WinningTime 速度分（EXP-20260927-02）喺現行 live 用新尺重做 —— S1 PASS（機率），頭幾選冇改善

- 日期：2026-11-24　平台：AU　類型：候選（預先登記 `patches/au_speed_v2_20261124/PROTOCOL.md`，commit `9834e369` 先過結果）
- 背景：EXP-20260927-02 開發期 Gold +0.43 [+0.05, +0.86]；盲測 forward 2,044 場舊尺（Stage 4 v2）判 REJECT
  （insufficient_ranking_metrics）。**嗰個 forward 判決唔追溯改**；呢度係現行 live 上嘅新候選。
- 語料：`au-rejudge-20261124/BASE.json`（現行 live，含 F1），2026-08-05 起，4,000+ 場。速度值用同 forward 一樣嘅 code
  （`au_speed_venue_audit`）：30,068 場參考頭馬時間（1,080 場時間衝突剔走），速度覆蓋 **73.8%**（30,227／40,938 匹）。
- 洩漏：每仗往績 `date < 今仗`；場地×路程標準同地況修正只用嚴格早過今日嘅賽事；冇用賠率。

| arm | Δlog-loss [95%] | Gold Δpp（下界） | Good Δpp（下界） | capture@5 | 頭二選有中 | Holm | v2 |
|---|---|---|---|---|---|---|---|
| **S1** ability + 0.5 × 場內 z(speed)（原定固定） | **−0.00028 [−0.00048, −0.00009]** | −0.23 (−0.61) | −0.08 (−0.54) | +0.08 | +0.03 | **0.005** | **PASS** |
| S2 walk-forward β（中位 0.72） | −0.00027 [−0.00056, +0.00001] | −0.11 (−0.57) | −0.14 (−0.65) | +0.11 | +0.06 | 0.03 | REJECT（CI 上界 +0.00001） |

## 讀法

- 速度分喺現行 live 上**有獨立資訊**：機率準咗，同 S1／S2 方向一致、Holm 過。呢個係新尺第一次判佢，舊尺嘅「排名證據唔夠」
  係舊尺冇靈敏度（EXP-20261121-35：真改善 v3 只捉到 2–14/30）。
- 但**頭幾選冇改善**：Gold／Good 點估計輕微負（CI 跨零），capture@5／頭二選輕微正。即係改善喺中後段排名同機率，唔係首選。
  同 EXP-20261124-22 嘅 PR2 一樣嘅形狀。
## 決定：實驗性上線（Kelvin 2026-11-24「if it makes our model better happy to go ahead」）

照合約，主指標（log-loss，Holm 0.005）判定為改善，所以上 S1（原定固定 0.5，唔用 walk-forward β）。首選冇改善呢點寫入退回條件。

- 引擎：`au_racing_engine/winning_time_speed.py`（公式唯一位置；`au_speed_venue_audit` 改 import 佢），
  orchestrator／dump 工具同一個 `prepare_field`（全場速度 → `race_context["field_speeds"]`），`ability_score += 0.5 × 場內 z`。
  `WC_AU_SPEED_LIVE=0` 回退。參考頭馬時間表 `AU_Speed_Reference.json` 每晚建（`au_speed_reference_table.py`，~12 秒，30,068 場）。
- 顯示：分析頁拆解「頭馬時間速度分」，dashboard 分數拆解（`OVERLAYS`）同「逐駒全程速度」一齊歸速度維度。
- `exact_score`、validation 同 7 個 forward 腳本都加咗 `speed`，咁其他 forward 嘅「live」唔會靜靜少咗呢截。

## live 實作核對

- Ballina 11-23 單場重評分：62 匹速度值同研究計法逐匹一樣（0 mismatch），64 匹有 43 匹有速度分。
- 全語料用 live code 重建 dump（4,260 場，30,094 匹郁咗）對 BASE：

| | Δlog-loss [95%] | Gold Δpp（下界） | Good Δpp（下界） | 頭二選有中 | v2 | v2.1 |
|---|---|---|---|---|---|---|
| 研究 harness S1 | −0.00028 [−0.00048, −0.00009] | −0.23 (−0.61) | −0.08 (−0.54) | +0.03 | PASS | — |
| live code（第一版） | −0.00027 [−0.00043, −0.00011] | −0.11 (−0.42) | −0.14 (−0.58) | −0.08 | PASS | PASS |
| **live code（Sol 修正後）** | **−0.00028 [−0.00048, −0.00010]** | −0.23 (−0.61) | −0.11 (−0.56) | +0.06 | **PASS** | — |

  第一版嘅差異係 bug：全場名單存原始值、每匹存捨入值，引擎搵唔到自己就再加一次，令自己計兩次（Sol 發佈前覆核搵到）。
  修正後同研究 harness 基本一樣。同時修：場號字串、開關關咗時唔入 forward（`live` 標記）、`au_eval`／`au_matrix_refit`
  研究 scorer 補齊所有 live overlay（老馬、練馬師剩餘表現、騎練總獎金、速度分 —— 前三個係舊缺口）、速度表唔再跟練馬師表失敗一齊跳過。
- 已知差異：live 參考表只有建表時已抓嘅 Formguide；研究用全語料（包之後先抓嘅 Formguide 入面嘅舊賽事）。11-24 兩者一樣（30,068 場）。

## 退回監察 forward（EXP-20261124-42，預先登記）

`au_speed_forward.py`、scheduler `step_speed_forward`、tracker `speed_live`：baseline = live − 儲存嘅 `winning_time_speed_feature`；
11-25 起、新 code 評分場次先計分，1,000 場用 v2 判一次並凍結。`rollback_recommended` 條件：Δlog-loss CI 下界 > 0、AUC 護欄唔過、
**或者 Gold 同 Good 點估計都 < 0**（因為上線前首選冇改善）。上唔上線／回退由 Kelvin 決定。
