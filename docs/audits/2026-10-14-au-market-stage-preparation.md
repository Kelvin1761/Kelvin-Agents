# AU 下一階段：市場資料工具準備與研究

日期：2026-10-14。Kelvin 授權先學習／安裝四個 repo，優先使用外置碟。
本次完成安裝與小規模連線／介面驗證；沒有 AU 候選模型回測或表現改善聲稱。

## 安裝位置與範圍

外置碟 `/Volumes/Kelvin Hardisk 1` 已確認是真實掛載：開始時可用約824GiB；內置碟約22GiB。
研究根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/tools/au-next-stage-20261014/`。
新下載、Python 虛擬環境、uv cache、temp、SQLite、運行紀錄均在該根目錄。
Python 使用本機已存在的 CPython3.12.13，不另外安裝到內置碟；venv 的 base interpreter
仍在 `/Users/imac/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/`。
整個研究目錄完成驗證後約848MiB，venv 約382MiB，cache 約429MiB。

| Repo | 固定 commit | 本次處理 |
|---|---|---|
| BillyBingham/Odds-Fluctuations-in-Horse-Racing | `6d235671f707016ea6f86297893db3f3094ef592` | shallow clone；CSV、notebook、Word報告、PDF、Tableau原檔保留；只讀 source／CSV／報告文字，沒有執行原 notebook |
| betfair-datascientists/betfair-datascientists.github.io | `893b6d2def4327c6fca8d73576975ec38b2bdb42` | partial clone + sparse checkout；78個md/py/ipynb及頂層檔，约5.8MB文字內容；不下載大量圖片／歷史資料，不建立本地網站 |
| DanielTomaro13/RacingBoard | `e62e825ca13644c3279396ae4b5b92d19c7ac12a` | clone + core runtime；本地介面已短暫啟動並停止；optional ML trainer 沒有啟用 |
| DanielTomaro13/sportsdata-mcp | `713f5a7a4746c34f270e3ead544dbf2a2ee7bba7` | editable install v0.33.0 + dev tests；可作 Python library 或 standalone MCP server |

`manifest.json` 記錄 paths/origins/commits；`requirements-resolved.txt` 記錄114個已解析套件版本。
包括 FastMCP3.4.8、httpx0.28.1、betfairlightweight2.24.0、betfair-data0.3.4、pandas、
scikit-learn、matplotlib、nbformat、BeautifulSoup及測試工具。
RacingBoard 的 `requirements-ml.txt` 是另選訓練層；本次不安裝 lightgbm/pyarrow，亦未
改本機原生 OpenMP 環境。現有 web/data runtime 不需要它們。

没有更改全域 Codex MCP config；standalone MCP 已驗證，亦可由 Python 直接調用。
沒有建立 launchd／定時任務、tunnel、公開部署、長期poller；沒有輸入帳戶資料或投注。
AU 現役模型、Gold/Good判決規則及pipeline未改。

## 驗證證據

外置根目錄下保存：

- `logs/version.log`、`logs/lint.log`：CLI version與spec lint成功，0 warning。
- `logs/offline-sportsdata.log`：1511 passed、373 deselected，1個未登記unit marker警告；
  命令 `pytest -m 'not live and not contract' -q -p no:cacheprovider`，約384秒。
- `logs/racingboard-retention.log`：upstream原生`python tests/test_retention.py`入口，6個case全過。
  初次以pytest執行沒有收集到tests（exit5），這是入口選擇問題；原紀錄保留，不冒稱pytest通過。
- `validation.json`：各命令exit code及結果；RacingBoard retention驗證另記在自己的log。
- `protocol.json`／`logs/mcp-server.log`：stdio initialize/list_tools成功，53個工具；
  六個明確read-data groups：betfair.exchange/navigation、tab.racing、sportsbet.racing、
  pointsbet.racing、betr.racing；沒有sportsbet.write/account或tab account/placement groups。
- `live-probes.json`、`state/probes/*.json`：五個provider本機read-only連線都有實際回應。
  TAB58個meeting、Sportsbet當日dates/sections/meetings、PointsBet3個日期組、BetR10個next-race items、
  Betfair148個navigation nodes；provider shapes不同，不能當成已統一schema。
- `price-probes.json`：Eagle Farm R2共14個runner entries，12個fixed-win價；
  dfsFormRating有14個欄位值，其中只有10個>0，另4個為0；early speed band有14個。
  這只證明可取欄位，不證明rating獨立於市場、不證明缺資料BACKMARKER標籤可信。
  Betfair AU WIN市場`1.263730302`，10個runner entries、8個exchange blocks，
  OPEN且inplay=false；有actual availableToBack/availableToLay價格及size。
- `board-smoke.json`、`logs/racingboard-smoke.log`：首頁HTTP200、health OK、19場AU賽事，
  child server已終止。smoke關掉corporate poller、active cap2，只驗證本地介面與live discovery，
  不代表所有多源配對或完整race lifecycle都驗證過。

所有回應只是一刻的可用性證據，不是持續feed SLA，也未量quote freshness或成交可行性。
repo `./檢查.sh --quick`及完整`./檢查.sh`均通過；完整測試以現有
`WC_HKJC_SCHED_LOG_DIR=/private/tmp/horse-analyst-hkjc-test-logs`覆寫HKJC測試日誌位置。
保留現有AU/HKJC data-contract stale-baseline警告，沒有把其他session的模型基準重新校準。
Betfair sparse checkout的78個檔另按Git blob SHA逐個核對，全數一致；RacingBoard與sportsdata
upstream worktrees均clean。本次沒有改upstream source。
運行器強制external state/cache/temp、loopback127.0.0.1、AU thoroughbred；telemetry關閉。
RacingBoard wrapper先覆寫Discord設定，避免upstream自動讀另一個project的webhook後發通知。
Kelly fraction=0、auto-follow confirmations=999；沒有啟動或測試第三方placement/account APIs。

## 四份研究的可借鑑內容

### 1. Odds-Fluctuations

[README](https://github.com/BillyBingham/Odds-Fluctuations-in-Horse-Racing/blob/6d235671f707016ea6f86297893db3f3094ef592/README.md)
及notebook／CSV確認：806筆、806個RaceID，**每場只記錄贏馬**。
目標Top2Flucs是「已知贏馬是否屬該場最大兩個縮價之一」，不是「這匹馬會不會贏」。
294/806為Top2Flucs=1，512/806為0；README80%accuracy不是冠軍預測命中率。
notebook輸入Opening、Starting、PercentDiff、Ground、Favourite；Starting及完整開盤→開賽變動
不可用於更早落注時刻的預測。random train_test_split／10-fold非chronological驗證。
最後一段混淆矩陣亦曾在新split後用舊predictions，不能直接引用為固定holdout證據。

可保留的問題：固定決策時刻已觀察到的價格變動，是否包含原模型未捕捉的資訊？
需要每場所有runner、同時刻市場baseline；winner-only資料無法量假陽性／選注ROI。
此repo沒有可見LICENSE；本次作本機研究副本，不把其code或資料vendor進AU主線。

### 2. Betfair教材

已讀市場走勢、BSP、historical stream、backtesting ratings、commission等相關source。
值得學：publish_time／inplay cutoff、back/lay ladder、可用size、matched volume增量、
spread、tick movement、固定時間窗、多粒度採樣、commission和未成交情況。
歷史stream的size/volume更新是該價位當下總量，不能把每次更新都累加成成交量。

[市場走勢notebook](https://github.com/betfair-datascientists/betfair-datascientists.github.io/blob/893b6d2def4327c6fca8d73576975ec38b2bdb42/src/tutorials/analysingAndPredictingMarketMovements.ipynb)
中有可直接讀出的例子問題：`wap_movement_10s`除以`wap.shift(-10)`，在candidate feature中用了未來值；
`best_lay_30s_in_future`實際shift的是back_best；shift30筆不能在缺更新時保證等於30秒。
這是教材source的audit flag，不是說整個Betfair資料源或所有教材都有問題。
教材應用作方法參考，先修timestamp joins與future-invariance，再做可重現實驗。
歷史stream資料不是這份文字checkout的一部分；沒有下載付費資料或進行帳戶登入。

### 3. RacingBoard

較有價值的是forward logger、固定T-120/90/60/.../2 buckets、多源確認、價格比較、
immutable paper-follow與favourite baseline。
firm/features.py將H時刻特徵與jump_price label分開；evaluate.py明確改為H→jump標籤，
避免用已發生的open→jump方向獎勵T-2預測；train.py按race jump_time分割及calibration。

heuristic是縮價預測：market35%、form25%、flow25%、consensus15%，再做momentum調整。
這些不是馬匹能力權重。`P(firm)`不等於`P(win)`；repo的metrics_h60.json記model AUC.651
vs baseline.608、5235rows，但沒有這份安裝可重播的原始語料／CI，不作可採用證據。

另外：queued weight-of-money不等於已成交資金；tote share來自歸一化inverse odds，
不一定是精確逐馬實際pool金額；跨book確認有共同資訊，不是獨立證據相乘。
scorer.py對dead heat註釋允許全額派彩，不能直接用它判真實投注ROI；必須獨立處理
dead heat、scratch/reduction、commission、market價格可成交性及place slots。
README說明GitHub Actions已暫停，公開demo是recording；本次測的是本機live backend。

### 4. sportsdata-mcp

可作通用HTTP資料層：provider specs、rate limit、timeout/retry、cache、error_signals、
capability discovery、doctor／contract checks。RacingBoard直接Python import調用，無需LLM。
其response_hint只是說明，不是跨provider統一schema；本次Sportsbet回應dates結構即可印證。
markets/events/runners還是要由我哋做deterministic matching、時間戳及coverage gate。
GraphQL／需要key的provider未測；不能由53工具catalog或offline tests推斷全部provider正常。
上游支援account/placement，但本次配置沒有暴露那些groups。

## 對下一階段的安排建議（本次沒有開始運行）

1. 先寫一份獨立市場研究methodology：固定decision horizons、每場所有runner、
   provider observed_at／source_time、scratch、market status/inplay、back/lay/size/volume。
   AU原能力排名保留；任何市場入分另有明文方法及既有promotion gate。
2. 先量join／資料完整度／時效，再做持續forward資料收集；把label結算與feature snapshots分開。
   這需要營運設計、storage/retention、monitoring，安裝本身不等於授權新排程。
3. 分開驗證：(a) H→jump縮價預測；(b)對獨立AU模型的增量；(c)可成交價扣成本後回報。
   一律先量樣本需求／部件預算，dev與時間fold選擇，新terminal最後確認；不能用BSP救早期信號。

同 `docs/plans/2026-10-14-open-source-borrowing.md` 的市場增量／去水／位置一致性研究整合，
避免重複測已失敗權重。操作入口見 `docs/operations/au-market-lab-20261014.md`。
