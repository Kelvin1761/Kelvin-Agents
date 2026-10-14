# Betfair 賠率走勢：AU 下一階段學習筆記

日期：2026-10-14。範圍：學習與準備；用戶明確要求暫不實作。
這是市場資料研究筆記，不是現役 AU 模型說明，也沒有已驗證的訊號權重。

## 現時是否需要做更多

已安裝的外置碟 Python 資料工具與教材足夠支持下一階段研究。
目前毋須再裝 ML 套件；不啟動 collector、排程、訓練或 AU scoring 整合。
學習重點是先準確定義價格、流動性、成交量與時間，然後分辨可以測試的訊號。

工具與版本見 [operations](../operations/au-market-lab-20261014.md)；
存量時間資料缺口見 [EXP-20261014-09](../experiments/EXP-20261014-09-au-market-movement-readiness.md)。

## 先掌握讀盤語言

| 概念 | 正確讀法 | 常見誤讀 |
|---|---|---|
| Best back / best lay | 兩邊目前可成交價格；size 是可供成交的數量 | 把掛盤量直接當成已下注資金 |
| Last price traded（LTP） | 最近一次成交價，可能已過時 | 當成現在一定可以買到的價 |
| Spread / depth | 兩邊價差、各檔可成交量 | 只看一個報價就判定市場強弱 |
| Runner / market total matched | 個別馬匹與全場的累計成交量，分開量 | 全場成交上升就說某匹馬受支持 |
| Tick / percentage move | 按實際 price ladder 算格數；百分比另算 | 各價位減一元視作相同力度 |
| Queue change | 掛盤可能成交、撤單或改價 | 消失的掛盤全部算成成交 |
| BSP | 起跑時結算出的 starting price，與當時即時報價分開 | 用最終 BSP 解釋較早決策時的訊號 |

掛盤兩側的經濟含義亦要核對：available-to-back 是提供給 back 方成交的對手盤，
不能將其 size 簡單命名為「支持這匹馬的買入資金」。Weight of Money 的公式、
取幾檔、方向與可成交量限制都要寫明；不能由一個比例直接推論勝率。

官方來源：[讀 Exchange market](https://www.betfair.com.au/hub/education/betfair-basics/read-an-exchange-market/)、
[API type definitions](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687465)、
[BSP](https://www.betfair.com.au/hub/education/betfair-basics/betfair-starting-price-bsp/)、
[price increments](https://betfair-developer-docs.atlassian.net/wiki/pages/viewpage.action?pageId=2686993&pageVersion=3)。
市場規則、commission 與實際可成交量需另外處理；學懂價格不等於已證明可盈利。

## 值得日後驗證的訊號假設

以下只是研究假設，未證明能改善 AU 排名，未指定權重。

1. **持續縮價**：多個已觀察時點同方向移動，並有該馬成交量增長；與一次薄盤跳價比較。
2. **縮價後反彈**：幅度、持續時間及回吐程度，是否有額外資訊。
3. **持續漂價**：在相同當時價格下，先前方向是否仍有增量資訊。
4. **市場與 AU 分歧**：能力分數與市場概率不一致時，走勢能否幫助判斷；必須保留市場基線。
5. **流動性條件**：相同縮價幅度在不同 spread、depth、runner 成交量下是否可靠程度不同。

退賽／reduction factor 引起的機械重定價、臨近開跑的流動性增加、走地價格、
cached quote 和跨 book 價差，都要與同一市場的賽前走勢分開。
多家價格一致可能是共同資訊或跟價，不可當成多個獨立證據；也不能由縮價推論內幕消息。

## 現有工具實際提供甚麼

已保存的 Betfair 單次 probe（market `1.263730302`）有：

- 市場 `marketTime`、market ID、price ladder description。
- `status`、`inplay`、active runner 數量、`bspReconciled`。
- 市場 `totalMatched`、`totalAvailable`、`lastMatchTime`。
- runner 的 `lastPriceTraded`、`totalMatched`、status、adjustment factor。
- `availableToBack` / `availableToLay` 的價格與 size。

這證明工具可取得基本市場資料；只有單次快照，尚未證明持續讀取的 freshness、
更新延遲、完整 runner identity、穩定性或歷史訊號效果。此 web feed 與官方 API schema
不必然完全一致；不能因官方有欄位，就聲稱現有工具亦有。
`lastMatchTime` 是最近成交時間，不是每個報價的更新時間；market version 也不是通用報價時鐘。

日後若研究 Stream API，先學會維護增量 order book：atb/atl 更新是該價位的当前數量，
不是每次相加；traded-at-price 是累計量，不能直接當每次新成交。
撤單、void／reset、cross matching 與幣種都會影響解讀。

## 從外部項目吸收甚麼

- **Betfair 官方與 datascientists 教材**：市場機制、流動性、stream、歷史資料和交易成本。
  教材程式仍需逐段 leakage audit；已見 movement 示例用負向 shift 引入未來資料，不能照抄。
- **Odds-Fluctuations**：提出縮價幅度排序的假設；資料只有已知 winner，不能證明可預測 winner。
- **RacingBoard**：參考時間序列保存與展示概念。其既有權重、WOM 或 firming predictor
  不是 AU 已驗證權重；不需要部署介面。
- **sportsdata-mcp**：可用 Python 資料層；使用它不代表主模型需要 LLM。

## 將來開始實作前的資料門檻

首先認證 UTC／scheduled start、取得時間、來源更新時間或其未知狀態、cache、
runner identity、退賽及 inplay 狀態。存量 AU 多快照仍未通過固定賽前 horizon 的時間認證。
Betfair probe 的 native marketTime 是未來可用的候選來源，不能補證舊資料当時的 freshness。

之後先量 coverage，再測「當時 AU＋市場價＋走勢」相對「當時 AU＋市場價」的增量。
概率預測、縮價預測、排名與可盈利是不同任務；AU 採用仍按原 Gold／Good 評估閘。
保留 [ML 試驗設計](../plans/2026-10-14-au-odds-signal-ml-study.md) 作後續參考；目前不執行。

## 本次驗證

只新增研究筆記與更新計劃狀態，未修改模型、安裝依賴或啟動背景程序。
完整 `檢查.sh` 的 15 個 suites 通過；AU／HKJC 仍有既存 stale-baseline 警告，
因此不將數據合約比較當成有效的新模型證據。
