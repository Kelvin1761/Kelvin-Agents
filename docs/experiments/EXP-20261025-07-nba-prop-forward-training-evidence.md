# EXP-20261025-07：逐 prop 賽前輸入 → C baseline → Final target

## 決定及範圍

**工程資料鏈；沒有fit／採用新公式。NBA engineering complete / forward model evidence pending。** 用戶目標是新模型超越現役C後作主模型；本輪把阻礙公平訓練／比較的資料鏈接通，不把既有32場開發單腿成績當升級證據。沒有改C、EV、選腿或`MODEL_VARIANTS`，沒有新投注／外部ledger apply／Dashboard部署。

Base `2429d0fa2c6a9a05f0bdda7e9fb9360b1074ce05`。先查EXP-04、05及06研究分支（`codex-nba-l10-calibration-20261025`、`0fef884f`）：80/80的full研究模型未證明勝C；只用過去selected腿的offset反而令後續15腿Brier稍差，不保留。沒有趁這輪再換參數／窗口救候選。

## 固定協議

外置根`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-prop-training-evidence-20261025`；Protocol.json在實作及結果之前寫入。只觀察新的native snapshot，不retrofit舊model_obs。既有賽前快照已包含EXP-05的原始機會量資料，但原ledger沒有按腿可join的輸入；現在讓每次既有`record_snapshot`自動留下`prop_training`，既有evaluate自動列`prop_training_evidence`準備程度。不另裝排程。

新增`nba_prop_training.py`只做資料觀察／匯出，沒有概率、fit、排行或bet builder。每條腿保留：

- 相同時刻的C模型ID／概率／原生單腿價在`baseline`，不放入`inputs`。
- L10數組／日期／分鐘、歷史隊伍與賽季參考、由真數組重算的L10/L5及80/80資格。
- PTS／REB／AST／FG3M各自的機會量欄位、缺項、GP、來源query季／cutoff／capture／row及source hash；球員角色及source fallback警示另列。
- 未來Final y／首次結算時間／結果hash只放`target`，不是預測輸入。無法核實／void／未有賽果留null，不當miss。

數據capture不等於validated forecast：`training_ready=false`及`promotion_allowed=false`是明確的階段標記，不是新統計採用閘。選中腿是selector membership，並非實際投注。

## 時間、身份及完整性

只從manifest列出的game_tags與遊戲檔hash讀取，對照官方game tag及tip；capture及export都要求`tip_source=official_schedule`，不接受Sportsbet fallback冒充官方時間。Full-name正規化＋同隊唯一配對，要求NBA player ID；每條腿須是整數Over milestone。L10須10個不同、順序正確且早於事件US日期的日期；支援真實Extractor的`OCT 21, 2026`及ISO格式，沒有拿缺失當0。80/80重算，不信任外來hit-rate欄位。

新來源available時檢查GP、季、capture≤snapshot cutoff、query cutoff早於事件US日及hash格式。負數／非有限數擋住，0 attempt conversion null保留。繼承的USG／AST%可能fallback，需要連同原game context來源審核；沒有聲稱裸欄位全部PIT安全。原始來源仍在immutable snapshot，輕量ledger保留references及該prop values，不為每條梯級複製整個tracking表。

匯出沿用ledger最新已發布pretip snapshot規則，排除warmup、no_prediction、preseason、late／post-tip；最新缺新feature不回復舊snapshot湊資料。額外核對odds capture≤snapshot created≤recorded<tip，feature cutoff綁snapshot。Final target要求既有settle的hit/miss verification狀態、結果hash及tip後結算時間；`dataset(as_of=...)`亦不暴露當時未可用的標籤。

來源parse失敗明列`observation_error`／`snapshot_source_error`，不破壞正式投注；準備報告保留status counts。匯出CLI遇壞ledger JSON會停止，不默默吞行。使用新輸出目錄，將每個來源JSONL一次讀取的相同bytes另存`source_ledger`及hash，避免append期間用不同版本。單次window>100MB要求縮窄日期，不產生大型內置暫存。

## 實測及驗證

首次只讀現役ledger匯出：6465個最新published腿尚沒有此新feature觀察，另296腿沒有published pretip snapshot，**符合新合約feature_rows=0**。這不是模型無法出bet，也不是現有C observations／舊OOF資料消失；它表示尚無完成這條新來源合約的前瞻資料，不准用今天tracking回填舊腿。

既有正常下一次賽前snapshot才開始留下新欄位；日常evaluate會分prop列rows／settled_rows／80/80／settled_events。當下不宣稱已收足訓練資料或完成挑戰模型對C的forward試驗。

全NBA **571 passed**，quick綠。新針對測試包含manifest tamper／官方身份及缺官方來源、整數milestone、真日期格式／當場日期／重複日期、80/80重算、GP0／錯季／晚capture／hash、最新缺feature、warmup／late／no_prediction、void／未核標籤／未到available_at，以及正常`record_snapshot`接線、原C metrics parity。

6日71,296行凍結ledger重播，除新增evidence欄位與generated_at外，改前／改後整份C評估exact parity。17場原生歷史snapshot純只讀兼容重播：3985腿有有效base，39腿不是10個有效prior日期、290腿snapshot已非pretip；原包沒有新tracking所以仍是base_only，**沒有回填ledger**。首輪兼容檢查誤用Sportsbet時間，出現3447個10分鐘錯配；保留原結果，改用ledger既存官方時間後重播。正常scheduler原已用官方時間，這亦促使把獨立CLI fallback路徑封實；首個尚未提交的gate取消後，對修訂SHA重跑。完整release gate及activation證據見外置根Final_Verification.json。

## 後續挑戰模型

保留80/80研究基準，逐prop獨立輸入／參數。先累積這條新資料鏈及Final labels，凍結train／calibration／之後未見comparison，再逐block測機會量、效率、分鐘／角色、對手；不要用同一組結果擇參再稱blind。全candidate與selected cohort同時看，分prop及價帶報概率誤差、coverage、配對不確定性。C歷史fit overlap不是獨立比較；真正主模型升級要用之後凍結的同批腿及同個報價時刻。

目標包含盈利SGM，因此單腿確認後仍須另驗原生SGM價、聯合命中及相關性；不能由單腿乘積或開發ROI直接晉升。NBA正式promotion把尺及功效須在候選fit／確認之前另行凍結，這輪沒有改判決規則。

CLI（只讀local ledger；`--output`需全新目錄）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/nba/nba_daily_auto/nba_prop_training.py \
  --root ~/WongChoiData/NBA_Market_Eval --since YYYY-MM-DD --until YYYY-MM-DD \
  --output <外置全新研究目錄>
```
