# EXP-20261025-08：逐 prop、80/80、單調概率挑戰模型工具

## 狀態

**研究工具完成；尚無原生新資料可fit；NEEDS MORE TESTING，不晉升。** 只保存獨立研究分支，不進main、不安裝日更、不改現役C／EV／SGM／Dashboard。不能將synthetic單元測試當真實準確率或盈利證據。

承接用戶要求超越C後升為主模型，及EXP-04、05、06、07。不是再試舊global offset：EXP-06只用過去selected腿學offset未見幫助，這次不採用；也不拿舊32場反覆調參。這一輪建立可重現、可在新資料成熟後執行的per-prop fit／walk-forward／forward-prediction工具。

## 先固定協議

Base `655296ee0a5b69ed5f6db01c4bd2332f5441ffa3`。外置根`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-prop-challenger-20261025`。Protocol.json先於實作及任何結果固定：四個prop、六個arms、ridge4、近期decay0.9、80/80、資料／時間隔離及不得promotion。沒有打開舊terminal，也沒有換AU/HKJC判決把尺。

內置Data volume不足10GiB，本輪沒有開大型模型實驗、沒有抄語料；只有小型工具測試及既有ledger只讀匯出，全部研究輸出在已掛載外置碟。

## 模型與各prop輸入

每個prop共用自己的classifier，不按姓名獨立fit。`logit(p)=a_s + b_s×count_logit + c_s×empirical_logit + d_s×recent_logit + context_s`。

- Core：L10均值／變異推moment Poisson/NB milestone survival logit；Jeffreys平滑L10命中logit。
- Recency：newest-first固定0.9遞減，weighted hits加0.5／總weight加1；沒有search衰減率。
- Minutes：L10均值、CV、L3/均值；**是歷史參考，不冒充已驗證未來分鐘預測**。
- Opportunity及opponent按prop消費不同欄位：

|Prop|Opportunity context|Opponent context|
|---|---|---|
|PTS|2PA、3PA、FTA每分鐘；2P、3P、FT各自轉化|容許PTS／100回合|
|REB|攻／防籃板機會每分鐘、各自轉化、爭搶比例|對手自己投失／進攻籃板、容許REB／100回合|
|AST|potential assists每分鐘、touches每分鐘、持球時間|容許AST／100回合|
|3PM|3PA每分鐘、3P轉化、catch-and-shoot／pull-up出手率|容許3PA／3PM／100回合|

裸USG／AST%參考可能來源fallback，第一版不當已核特徵；POTENTIAL_AST轉化亦不採用，因來源定義不支持保證AST是其嚴格subset。源GP／query cutoff／缺失狀態仍隨資料保存，之後實際fit前需核對feature evidence，不因一個裸數字存在就認為有預測力。

這是低容量的classifier假設，**不是已驗證的「分鐘×機會×效率」生成模型**。Context只平移logit，不能自由改變所有尾部分布；是否比更簡單core好，由之後相同時間外資料判斷。

## 單調限制與訓練

價格／C／姓名／結果都不在X allowlist；只有key的milestone line用來算count與empirical特徵。Count、empirical及recency logits隨line增加不升，對應係數限制非負；其他context不依line，故同球員同來源下25+不得比20+更高概率。沒有靠事後扣固定pp或挑中某條line補救。

每prop constrained ridge logistic（scipy L-BFGS-B，maxiter1000，ridge4），不做hyperparameter search。每player-event-prop ladder總likelihood權重1，避免梯級多的球員倍增權重。Median imputation、mean/scale只fit訓練列；整個訓練期全缺的欄位drop並記錄，不把之後出現的新欄位自動算成已學會。

只fit80/80原生腿。每prop最低8訓練日期／20事件／100個player-event-prop ladder、每類label至少10個有該label的ladder；保留opportunity block的arm另需20事件有非空opportunity。**全部是可計算性／過度稀疏的操作下限，不是統計功效、盈利或promotion閘。** 沒有達標就blocked，不以舊模型fallback補位。

固定六arms：core、full、minus_recency、minus_minutes、minus_opportunity、minus_opponent。同日期／候選池比較；沒有因某個arm點估計最好就自動選它。全四prop／全arm訓練未齊的日期列blocked，不改窗湊過關。

## 原生資料重建及時間驗證

只讀EXP-07匯出。每個複製ledger JSONL的hash須等於Readiness.json；由這份相同原始ledger重新跑native dataset join，saved dataset須完全相同。另驗unique milestone key、L10日期／line／80/80一致；不接受手造一份CSV補出歷史tracking。

按target日期expanding walk-forward。每個test日先取最早snapshot available_at作cutoff，訓練只用更早target日期、且Final label available_at嚴格早於cutoff的列。模型imputer／scale／係數皆只用這批；C baseline模型ID混合則停止，不混幾個C版本宣布勝出。

OOF輸出same-pool Brier／log-loss／gap、按prop與固定價帶，以及full−C/core/leave-block的日期cluster描述CI（2000，seed20261025）。另列每事件最高正預測EV單腿的命中、gap、coverage及flat ROI，價格1.15–3.5；不是正式banker或SGM重播，亦不是盈利判決。多個描述比較未作獨立promotion檢驗。

每個成功fold保留JSON coefficients與constructor hash／訓練label最後可用時間，無pickle。研究predict只接受hash及constructor相符的artifact、同一C baseline，而且實際wall-clock仍在tip之前；輸出OBSERVE。它不寫投注ledger或選擇main模型，也不會自動拿全部已見資料refit或挑贏家。

## 今輪實際結果

重新只讀現役ledger匯出後，合格新feature rows仍為0。真實CLI結果`awaiting_new_data`、OOF0、沒有任何trained coefficient artifact。這是資料未成熟，不是證明候選勝／負C；新來源照常由已部署EXP-07之後的賽前snapshot累積。

13項針對測試通過：四prop fit／JSON roundtrip／不同milestone單調性、price/C/labels/name不影響features、訓練期缺失處理不看future、稀疏／無新機會量拒絕fit、模型含未可用label拒絕predict、特徵順序、walk-forward label時間隔離、混C版本拒絕、空原生export不產生模型、export篡改及A/A配對差必須0。測試資料是synthetic，不是backtest。

quick通過；完整repo檢查、研究分支SHA及preservation證據見外置根Final_Verification.json。現役模型未切換。

## 執行

在此研究分支：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/nba_prop_challenger.py \
  --export <EXP07原生export目錄> --output <外置全新study目錄>

PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/nba_prop_challenger.py \
  --export <其後未開賽原生export> --model <已凍結fold_models.json> \
  --output <外置全新forward目錄>
```

下一階段仍需足夠原生Final資料、預先凍結NBA確認規則／功效與未見資料，先驗same-pool及selected校準，再驗實際SGM原生報價／聯合命中／相關性。工程工具／操作下限／synthetic測試均不構成主模型升級證據。
