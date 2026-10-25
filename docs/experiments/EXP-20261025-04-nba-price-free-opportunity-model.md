# EXP-20261025-04 市場獨立、逐 prop 機會模型

## 決定

**研究原型已建立及測試，NOT SHOWN BETTER／NEEDS MORE TESTING；不晉升。** 全情境候選 OOF Brier 比核心差、亦未贏市場；不能用開發單腿選擇的正收益宣布盈利。正式 C、EV 閘、Dashboard 及注碼沒有切換。失敗／未獲採用的模型 code 只保存研究分支，不進 main；資料擷取亦不因本研究自動安裝每日排程。

承接用戶要求：共用底層分布、每種 prop 不同參數及角色輸入；價格只做 benchmark／EV，不作預測輸入。已查 EXP-20261021-05（獨立 Poisson/NB 近均值研究）、20261022-03（C 的校準與市場限制）、20261023-06（舊 RF 本身已無價但未勝 C）、20261025-01 未晉升角色研究、20261025-02／03。不是聲稱首次有無價模型，亦不重試舊 RF。

## 在結果前鎖定的協議

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-independent-shadow-20261025`。

Protocol.json SHA256 `c9c7871eb1380c93856606c1524317226f356b637743059e52f76d944ff7a46d`。使用既有 verified_dataset_v2，SHA256 `16b378cd914d1d684609760eb0edbeb6d4648d52a7b5552faba10fd45c3a7e0d`。共8,286有標籤列／49事件／24US日期；來源、原生價格、Final標籤及特徵全部重新核 hash 重建驗證。

保留原最後5日期完全不參與本輪 fit／評估，不換窗：2026-05-17、06-03、06-05、06-08、06-10。前19日期作開發，5折 expanding TimeSeriesSplit；4日期起步、其後15日期為OOF，共 **5,305列／32事件／15日期**。這些歷史已看過，OOF只是擬合時間上未來，不是新確認 holdout。C 擬合／檢視過部分比較日期，**C比較不獨立**。不用這些結果調參再當新OOS。

先寫 Baseline.json／Baseline_OOF.csv 才建立及計候選。第一次 run 在特徵建構時因 GS/GSW alias停止，未擬合、未有候選指標；保存原錯誤及原code。Repair1只核對 canonical team identity，遇歧義拒絕，不改特徵／參數／窗口。Prerun_Repair1.json及Frozen_Model_Study_Repair1.py記錄確切code hash。

## 模型

共用公式：每個stat自己的 `logit(p)=intercept_s + weights_s × standardized_features`。

核心兩項為：(1) L10逐場count均值／變異推導 Poisson 或 moment NB 的 milestone survival logit；(2) Jeffreys平滑近期命中logit。每stat獨立 logistic，即對count／empirical底層作學習校準；不是手工附加概率點數。

| Block | 實際特徵與限制 |
|---|---|
| 分鐘 | 均值、CV、最近3／均值比、現隊歷史比例 |
| 角色 | PTS：USG、FGA／MIN、FTA／MIN；AST：AST%；3PM：FG3A／MIN；不將球員自己的DEF_RTG當籃板／助攻角色 |
| 對手 | pace；DEF_RATING只用PTS／3PM；相關OPP每100回合值只有真的保存且GP>0才可用 |
| 賽程 | 主客、從嚴格之前日期計的間隔／B2B，不從未知fatigue欄位猜測 |

Potential assists／rebound chances／對手容許數據在舊歷史快照缺失，留NaN，訓練覆蓋0的係數沒有學到訊號；**新抓資料不倒填過去**。保留欄位供將來接線，不聲稱本輪已驗證。H2H未入模型，因為跨隊／角色及小樣本問題需獨立資料合約。舊 defender_pm 不採用，避免剛修正的名單缺陷污染新候選。

每fold只fit自己的 median imputer／StandardScaler／LogisticRegression(C=1,max_iter=2000,lbfgs)，無 class_weight、無search。每個event-player-stat梯級總訓練權重1，再正規化平均權重1，避免多掛價梯級倍增該球員權重。價格／label／未來history不進特徵。

固定6arms：core、full、各去一個block（minutes／role／opponent／schedule）。每個arm按同一日期／列產生OOF。主要比較full−core，另報full−市場／C及逐block消融；日期cluster bootstrap2,000次、seed20261025。Holm只對預登記family的bootstrap sign-tail作描述調整，不當正式獨立假說檢驗。無候選因單一指標較好而自動採用。

## 結果（Brier越低越好）

| 模型 | Brier | log-loss | calibration slope |
|---|---:|---:|---:|
| 原始L10 | 0.181589 | 0.983350 | baseline文件 |
| 獨立核心 | 0.175155 | 0.527376 | 1.060 |
| 獨立全情境 | 0.176236 | 0.529326 | 0.969 |
| 市場1/price，含vig | 0.171768 | 0.521677 | 0.897 |
| 現役C（歷史重疊，非獨立） | 0.168335 | 0.509495 | 1.014 |

Full−core +0.001080，95%CI[−0.000507,+0.002883]；只有1/5時間fold full優於core。Full−市場 +0.004467 [−0.001103,+0.010222]；Full−C +0.007900 [+0.004420,+0.011553]，但C歷史重疊限制必須保留。所有arm OOF milestone 機率隨line上升的逆序違規均0。

| Block（full減去移除版的Brier，負數代表留有幫助） | 差值 | 95%CI | 解讀 |
|---|---:|---|---|
| 分鐘 | −0.000017 | [−0.001224,+0.001302] | 沒有確定額外增益 |
| 角色 | −0.000372 | [−0.001134,+0.000357] | 微弱方向，未證明；不以insample係數判保留 |
| 對手 | −0.000134 | [−0.001250,+0.001191] | 微弱方向，舊資料沒有真正容許AST／REB等資料 |
| 賽程 | +0.001662 | [+0.000618,+0.002823] | 此開發候選加入後較差；不是B2B永遠無用的因果結論 |

分stat core→full：AST .188087→.194662、PTS .176476→.177108、REB .170287→.170682、3PM .170552→.169415。不能只挑3PM升而採用全套；沒有依結果重選arm／refit或開舊terminal。

## 盈利診斷（不是SGM、不是穩膽、不是採用證據）

預登記每事件選最高正預測EV的**單腿**、原始價1.15–3.5、固定身份tie、flat1；沒有L10穩膽閘或最低預測命中率，因此不是現役banker比較。所有選擇先由OOF概率固定，才計對應Final label。

Full32場有32條，**32中12**、平均價2.934、單腿+3.42單位／ROI+10.69%。但按日期cluster的描述CI為 **−39.95%至+55.27%**；平均預測57.38%對實際37.5%，被選子集高估近20pp。核心32中6、ROI−45.25%；C有23條、23中8、ROI−20.87%。三者coverage不同；這是極小的已見開發單腿選擇，不能聲稱打贏C、盈利／高命中SGM，亦不能將maxEV門檻改到歷史收益最好。

## 擴充資料擷取

`nba_feature_intake.py` 定義41類：球員／球隊 Base、Advanced、Usage／Scoring／Misc／Defense／Four Factors、Team Opponent場均及per100、雙方12類tracking、hustle。**40 available、1 unavailable**（player Four Factors，provider返回／解析不支援，KeyError已明列）；完整原始列全部保存、不削欄。這是明列catalogue，不聲稱涵蓋NBA每個API或資料供應商。

成功資料包括potential assists、touches／TIME_OF_POSS、rebound chances、對手OPP統計。Passing／rebounding／possessions目前GP1–2；對手per100 GP2–3。新捕獲為單一NBA來源、帶每表查詢／單位／cutoff／觀察時間／schema／hash，**research_capture_not_bound_to_event**，不是昔日不可變賽前證據；未接入本輪訓練或正式排程。基本／tracking口徑和stat定義要另作交叉核對，不能把1,232個欄位位置當1,232個獨立訊號。

## 後續

保留共用分布＋逐stat參數的研究骨架，優先累積真正角色／opportunity／對手容許欄位的賽前快照。先固定新資料訓練／校準／未見forward三段與所需功效，才擬合下一版。現有schedule block不在本候選獲保留支持，其餘block仍待證據；不因本開發窗挑中某arm就自動刪改正式因素。先驗證單腿選擇子集校準，再接原生SGM聯合價／聯合概率和相關性；不能將單腿乘積價或本次單腿ROI當SGM結果。

市場是benchmark，`1/price`含margin；只有一邊milestone價不能唯一去水。價格亦不能唯一識別莊家內部公式。本輪不猜「莊家真公式」，不以市場價當真實label。

## 重現與保存

研究CLI（在研究分支）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/nba_independent_shadow.py --dataset <原verified_dataset_v2/dataset.csv> --output <全新目錄> --protocol <外置根/Protocol.json> --baseline <外置根/Baseline.json>
python3 .agents/scripts/nba_ml/nba_feature_intake.py --catalogue-only
```

外置根包含Protocol／Prerun、Baseline、Frozen code、study_v1_repair1的Summary／OOF／Artifact／models、全部原始intake、Selection_Uncertainty及完整測試紀錄。模型artifact `deployment_eligible=false`，本研究不更新live model registry。研究分支及工程驗證見外置根Final_Verification.json。
