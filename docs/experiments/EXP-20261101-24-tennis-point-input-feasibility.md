# EXP-20261101-24：point kernel 輸入可行性，WTA-only盤點

狀態：完成唯讀輸入診斷；整體模型改善目標尚未達成。不是模型候選、訓練資格認證或準確率評估。原15個REJECT_DEV、frozen tennis-v1及正式pricing不變。

## 問題及已知限制

EXP-22/23已驗研究point kernel及歷史規則resolver，但現役props輸入是hold_a/hold_b。不能只因主history表沒有service-point總數就宣稱所有provider都沒有；WTA另有`wta_match_stats`，Sackmann／TML亦須另查raw counts，這次先盤點WTA，沒有概括全庫。

先搜尋EXP-20261026-04（fresh WTA）、EXP-20261027-09（對手校正S/R），沿用原拒絕結論，不重開已看績效窗。使用data-quality-audit及現有`_cached_stats_valid`／`_stats_quality_issue`，不是另造放寬版guard。

## 輸入及方法

凍結DB：`ranking-date-contract/source.sqlite`，1,943,166,976 bytes，完整重驗SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。以SQLite `mode=ro&immutable=1`及query_only讀取，不寫生產DB。

研究截點固定2026-11-01T00:00:00Z。所有966條WTA player-side逐條核對：原status、原始完整比賽品質guard、raw provider/HTTP/entity/請求tournament+year、stored/raw收集時計早於cutoff、point counts對原文、原始姓名／WTA ID及唯一canonical player/opponent、aware實際比賽timestamp、合法整數exposure。沒有由hold反推point，也沒有因見到結果更改門檻。

此cutoff只能支持「目前研究時已取得哪些輸入」，**不能支持歷史比賽／歷史市場快照時已可得**。未解釋的naive／缺失時計繼續暫扣。canonical姓名要求也是本次保守盤點條件，不能由此斷言所有暫扣姓名都錯。

## 結果

| 檢查 | 結果 |
|---|---:|
| 全部WTA sides | 966（954舊OK、12 UNVERIFIED_STATS） |
| 通過本次研究cutoff檢查 | 302 sides／151完整配對matches |
| 涉及玩家／raw receipts | 185／37 |
| 暫扣 | 664 sides；不刪除 |
| 本批至少5條已核實記錄的玩家 | 5 |

各暫扣原因會重疊，不能相加：player canonical identity未唯一對應243、opponent243、actual timestamp未核實390、raw stats品質失敗48、stored status非OK12。

48個raw品質失敗均為`partial_match`，其中36條舊標OK、12條未核實；**現有guard會拒絕這48條**。這不是新發現「正式pipeline必然正在採用36條錯誤資料」的證據，也未重寫舊status或任何結果。資料物理存在、舊OK標籤、完整point-skill模型合格三者不可互換。

185個玩家在本批核實資料中的記錄數：1場111人、2場44人、3場22人、4場3人、5場5人。這只是WTA這張表的樣本量，不是合併所有provider後的profile覆蓋率，也不是新設定最低5場的promotion規則。

沒有fit、LL/Brier／ROI、候選擇參、新forward、歷史publication-clock認證或訓練資格變更。下一步先以相同availability原則盤點Sackmann／TML原始point denominators及來源身份，再決定是否能建立點數輸入合約；不能把302條當足夠部署或把664條暫扣當全球無資料。

另用現成`inspect_tennis_feature_provenance`核對截至2026-11-01T07:25:44.546714Z的原生證據：129 records、127完整bundle、0 verified feature predictions；127份feature_artifact_missing、2份prediction_bundle_unverified。與較早盤點相同，沒有新forward資格或promotion。保存於同一證據根`native-feature-current-20261101T072544Z/report.json`，SHA-256 `f6d80d86901029d6bfce94fc80e506c362baafc2f2bacbc38972cbbfcc7a59be`；不能用個別diagnostic行代替原整份card驗收。

## 失敗、重現及證據

第一版審計把欄名`wta_player_id`誤寫成`player_wta_id`，首段中止；v1 source／failure／partial output保留，沒有當通過。只修正這個欄名，用同一snapshot、cutoff及條件跑全新v2。細項統計已另以保存的method source重播，結果與原detail.json一致。

根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`；`point-input-feasibility-v1/`與`point-input-feasibility-v2/`均有manifest。v2保存protocol、逐行原因、result、detail、兩份method source及execution-context（含當時checkout與既有helper的SHA）。

- v1 manifest SHA-256：`bd717d0f5fe58079010a688642848d17986ddddeb289b93720cadc0a7d6d04a9`。
- v2 manifest SHA-256：`aef8f9bf8ec51ded15f901c7fea13317c45b584f94df26f19ecb3d5bfffc6fbb`。
- v2 result SHA-256：`0ebd25fc8ae88b9235857d0b0f916d9f3dddd65aa41c35c5ffbd09900c5e4265`。

原命令：repo根目錄，`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python /private/tmp/tennis-point-input-feasibility-20261101.py`，source已另存v2/source.py。重跑需先複製source並只將OUTPUT改為全新目錄、記錄新source hash；原程式拒絕覆寫既有結果。detail重現source另存`detail-method-source.py`，讀取本輪固定rows.jsonl，不額外選樣。

補充：cutoff檢查依據凍結DB的時計欄位；它們不單獨構成當時已被獨立觀察的證明。未來使用仍須有早於預測的實際canonical capture／first-observed證據。Sackmann／TML補充盤點見[EXP-25](EXP-20261101-25-tennis-public-point-input-inventory.md)。
