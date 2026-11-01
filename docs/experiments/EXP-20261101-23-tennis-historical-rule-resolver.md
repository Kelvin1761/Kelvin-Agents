# EXP-20261101-23：F02 歷史規則解析器及接線驗證

狀態：研究規則解析器已實作；110個支援情境、1980個接線比較通過，2個已取消情境拒絕。正式pricing未接入，未證實準確度／ROI改善，F02完整整合仍未完成。

發佈核對：原候選b18478aed7639fea975c3900a885be3ef31890a3完整gate通過（1329.8秒）；排隊期間main更新，Central自動重放為37df3367b71fd3eb1294329da0527037a474f17a，對新SHA重跑完整gate（929.056秒）後merge／activation成功，runtime HEAD已直接核對一致。Tennis1065項測試通過；原候選manifest由自動流程supersede，沒有另開重複release。證據另存`resolver-v1/release-37df3367b71f/`；研究程式已同步不等於正式pricing使用它。

## 輸入、範圍及來源

只接受canonical event `ausopen/frenchopen/wimbledon/usopen`、嚴格整數edition year 2011–2024、明示ATP/WTA、draw=`adult_singles_main`。不接受別名／模糊名稱、qualifying、doubles、juniors、不從球員名字推tour、不以終局比分推BO3/5。這些欄位是caller的明示assertion，不代表解析器已認證fixture身份。

`research_kernel/slam_rules.json` 逐byte保存既有pinned registry，SHA-256 `8bd52b089ed026f5e43c79b9178266ec6009c1ba1fdc16a6ab86f04da634e247`；載入時驗hash，毀損不能靜靜用另一規則。該registry的source URLs是來源清單，不表示每個URL都支持每個年代／賽事。

- AO2019起決勝盤10@6；之前長盤。
- Roland Garros2022起10@6；之前長盤。
- Wimbledon2019／2021用7@12；2011–2018長盤、2022起10@6。
- US Open2022起10@6；之前7@6。
- 普通盤7@6；本範圍成人男單正賽BO5、女單正賽BO3。詳細來源及限制沿用[EXP-22](EXP-20261101-22-tennis-rule-aware-kernel-protocol.md)。

2020 Wimbledon另行拒絕為cancelled edition，不能把registry的連續規則區間誤當每屆都有舉行。[USTA 2020-04-01公告](https://www.usta.com/en/home/stay-current/national/usta-statement-on-the-cancellation-of-2020-wimbledon.html)已直接讀取及保存147,098-byte HTML receipt；[LTA當日公告](https://www.lta.org.uk/48fc73/siteassets/about-lta/press-releases/2020/2020-major-events-cancelled.pdf)亦核對第1頁。HTML存在檢查本身不等於語義認證，取消事實另由已讀正文支持。2025原官方URL仍502／404，2026亦未加入此歷史resolver；不能自動延伸或回填。

## 固定驗證及結果

事前protocol：112個event/year/tour組合，其中110支援、兩個2020 Wimbledon拒絕；每支援情境跑9對point probabilities（.45/.60/.75交叉）×兩個首發，共1980比較。expected transitions在runner另外明示，不由resolver registry lookup產生；檢查BO、普通盤及決勝盤參數，再對相同explicit kernel比較差≤1e−8。

| 驗證 | 結果／限制 |
|---|---|
| kernel＋resolver針對測試 | 76 passed（0.29秒），含各交界、未知值、bool年份、取消屆次、損壞resource拒絕 |
| 接線比較 | 110支援／2取消符合預期；1980比較最大差0；source hashes前後一致 |
| 全量既有Slam規則路由 | 49份metadata CSV全數驗hash；既有v4完整10513條審計記錄全部能路由規則；原reason及training flag照留 |
| 套件resource | 獨立build環境成功建wheel；Python `-I` 直接從wheel zip載入resolver／JSON，WB2019取得7@12、BO5並可呼叫研究kernel |
| repo quick | 通過；完整gate由Central發佈流程執行，確切SHA及成功狀態以immutable manifest為準 |

這1980比較驗的是規則選擇及參數傳遞，**不是1980個新增獨立數值oracle**；底層數值證據仍是EXP-22固定255個DP／MC比較。10513條路由沒有重新跑point state machine，也沒有建立新canonical身份、發布時計或訓練資格；不能把`ROUTED_RULES_ONLY`寫成10513條乾淨可訓練比賽。archive addendum明示已有v4結果可見，不稱新holdout。

最初用現有venv建wheel失敗，因setuptools58及缺bdist_wheel，沒有把它當程式通過或改生產環境。另建tmp venv裝setuptools82.0.1／wheel0.48.0／packaging26.3後成功。wheel SHA-256 `b2ea7d7f32ec01e8423c55737fd159308e6daec8abff046cc10bc325ca06ccc4`；載入路徑明確來自zip內package，非原始碼目錄fallback。所有版本及build log保留。

## 重現及停止界線

程式：`tennis-wong-choi/scripts/validate_rule_resolver_research.py`；以package目錄及`PYTHONPATH=src`執行，`--output`必須是新目錄。可選`--source-manifest`與`--archive-matches`必須成對；本次用f01-full/slam-singles/source_manifest.json及f01-full/slam-audit-v4/matches.jsonl，不縮細原49站輸入。

證據根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/resolver-v1/`。含事前protocol、原registry、官方receipt、archive addendum及`validation/`內逐行routing、結果、source快照、wheel、build logs及版本。

- protocol SHA-256：`7a3eae421474e4a04deaf80706580efe0f87183f49af3552afd8d32faeb2d9e2`。
- archive addendum SHA-256：`dac1ef03d2861eb75aefaf97c1dd5c0ecc6433047ec6c2e23cdb06927e845479`。
- validation result SHA-256：`5586fa7f83eb2ee8376b336af1127781faef7cfeb3d2d2ce2f675bc060d15b3f`。
- validation manifest SHA-256：`a1e144563e165ebe544fcda2110dce22cba7da1797d2c3c43043c403d0634c5b`。

下一個整合前提仍是可識別、合格的point skill與明確fixture/draw規則；現役只輸入hold probability的近似不能靜靜反推point skill。此resolver不做live名稱匹配、不改正式pricing或投注family、不解除F10依賴；15個REJECT_DEV及frozen tennis-v1不變。沒有LL/Brier、ROI或新forward判決。
