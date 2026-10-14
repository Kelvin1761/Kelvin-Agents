# AU 賠率變動訊號：獨立 ML 試驗設計

狀態：**LEARNING_ONLY；設計保留，暫不實作**。2026-10-14 最新用戶指示：先學習讀
Betfair 賠率與走勢的訊號，no need to implement yet。未fit或啟動收集；存量資料仍為
DATA_GATE_HOLD。來源：EXP-20261014-09。
學習筆記見 [Betfair signal learning brief](../audits/2026-10-14-betfair-signal-learning-brief.md)。
Kelvin的目標是模型學習變動所透露的訊號；RacingBoard只作資料記錄方法參考。
使用已安裝的Python資料層／統計套件，沒有LLM需要。

## 先鎖研究問題

主要問題：在同樣當時價格及AU能力分數下，過去已發生的賠率變動是否增加勝出／前三資訊？
主要決策時點T-60；T-30／T-10先保留資料與診斷，不看結果後轉換primary時點救候選。
「預測H之後會不會縮價」屬另一個label任務，不能混成win probability或用作本實驗成功指標。

市場價是**明文研究輸入**。原AU評分照保留作對照；不把價格隱藏在speed/form等欄位。
任何日後production整合是獨立候選，沿用既有Gold／Good／Stage4 gates；本設計不改把尺。

## Phase 0：先補時點證據

存量時點閘尚未過：歷史race jump time、逐race取得時間、freshness及部分補錄來源未驗證。
可先尋找原保存的native event metadata；若只取得今日補抓的歷史時間，標示retrospective，
不可自動說它是當時可知的原schedule。

向前資料若要收集，使用獨立headless Python入口，不需要RacingBoard介面。
以下是所需規格，**不是已啟動的新collector／launchd**：

- 每個source／race取得scheduled_start_utc、provider event ID、runner ID/number/name、country/code。
- 記request_started_at、response_received_at、source_updated_at（若真的提供）、cache-hit及來源版本。
- 固定保存T-120/T-90/T-60/T-30/T-10；immutable observation，價格和model snapshot分開保存。
- features只准用response_received_at <= decision cutoff的資料；不選cutoff之後的「最近」價格。
- provisional freshness上限10分鐘；來源更新時間未知保留FLAG，不能以新檔mtime假冒fresh。
  最終營運budget在未看結果的coverage pilot鎖定，之後不為救候選改門檻。
- price cache要明確控TTL／記原取得時間；重複cache回應不能每次改stamp變成新市場活動。
- 排除已inplay／resulted／closed；保存當時SCR與runner變動，不能用未來的最終名單清理早期場。
- 各book價格保持各自source；不同book價差不能被拼成同一book的時間變動。
- 保存back/lay價格及size、matched volume（有值才算），先核對欄位含義／queue與成交量差別。
- outcome／BSP／SP另表且只作labels／評估；逐列future-append invariance必須通過。

收集的首次工作是量coverage／delay／mapping，不是訓練。2,246個舊多capture race不能
代替已驗證的T-60樣本數；effective N是合格race/date，不是觀察列數。

## Phase 1：最簡單的增量試驗

同一批完整賽事、同一時間cutoff、同一identity集合，建立四個對照：

| Arm | 明文输入 | 用途 |
|---|---|---|
| A | 凍結的原AU排名／score | 現役基線 |
| B | 當時市場價格／場內去水概率 | 市場基線 |
| C | 當時AU score＋市場價格 | 排除「只是加入市場就變準」 |
| D | C＋一個已觀察價格變動特徵 | 量movement對C的邊際貢獻 |

第一次D只加**同source、同runner的log odds change**：T-90→T-60（均需合格快照）。
沒有真book opening price就稱first observed quote，不冒稱open。
field/SCR變動保留為guardrail；重編號、沒有可確認pair、補錄、過期或cutoff後觀察排除並報原因。
momentum、multi-book confirmation、volume／spread作後续獨立假設，一次加一個並做ablation。

先用已裝的logistic regression；用同一ML/calibration family量C和D，其他參數保持一致。
勝出及實際前三labels分開；勝率／前三概率與ranking score的轉換在dev鎖定，
不能改轉換去救terminal Gold/Good。baseline ranking仍用原模型，市場arm保持獨立。
若简单D有穩定OOS增量，再安裝及試LightGBM；模型複雜度不先於資料證據。

## Phase 2：證據紀律

- 開正式fit前，先做coverage和dev-only功效pilot，量可辨識幅度與component budget；
  ranking判決遵守合約§6，不在REJECT後改UNRESOLVABLE。
- 凍結dataset/hash、feature公式、baseline、cutoff、population、primary KPI及sample budget。
- chronological whole-date split；同race/meeting不跨邊界，使用canonical固定holdout規則。
- 舊terminal反覆曝光，只能retrospective；新的前瞻terminal在登記後才累積，且只最後確認一次。
- scaler／imputer／calibrator只fit訓練窗；輸出win/Top3 Brier、log loss、calibration、Gold／Good及
  固定ranking metrics、paired CI、venue／field／going／價位cohorts。
- 最關鍵是D相對C是否有增量，同時不能忽略B市場基線；不以「D比A好」單獨宣稱market edge。
- 正式排名採用仍須既有primary/ranking/cohort gate；概率更準不代表已通過排名閘。
- ROI／CLV後續另量：可成交價、size、spread、commission、scratch/reduction、dead heat和未成交；
  BSP不能當更早下注的input或成交價。沒有這些證據只報概率／排名研究，不能報可盈利。

## 目前完成／未完成

完成：存量audit、來源與時間FLAG、可重現diagnostic輸出、6項不變性tests、獨立試驗設計。
未完成：歷史／前瞻fixed-horizon認證資料、collector、正式sample budget、ML fit、terminal驗證。
因此沒有模型效果數字，沒有改AU score、排程或部署。
