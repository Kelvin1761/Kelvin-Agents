# Tennis 統一研究執行進度

開始：2026-10-28 Sydney；跨午夜於 2026-10-29 繼續。用戶已授權實際執行 [統一計劃](../../tennis-research-execution-plan-20261028.md)，目標係提高分析準確度。**執行中，未證實模型改善，未更換正式模型。**

## 2026-10-29最新更新：市場批次完成，仍未有合格候選

[EXP-20261029-05](../experiments/EXP-20261029-05-tennis-market-offset-devig.md)完成C02去水、C01固定市場offset及C13 training診斷。**power／Shin／inner去水／offset四個新候選全部REJECT_DEV；連同首輪共15個候選被拒絕，未啟動新forward或更換正式模型。** 本節取代下方較早「價格資格／市場比較尚待完成」嘅時點描述，舊checkpoint證據保留。

- 27,795個publisher原始價格行 → 23,225個canonical match／46,169個同書報價；只用B365／PS，BFE及Max／Avg留置。26個唯一身份但winner／比分矛盾或無法核對事件，喺fit前**連所有歷史輸入**隔離，clean cohort 27,237場、features 24,857行；不重跑舊失敗候選救結果。
- 額外身份scope audit使用全部30,879原始紀錄（含未完成／無效比分），全部可讀identity；23,225個已配對事件冇新歧義。實驗仍係unclocked quote conditional SEEN_DEV，唔係已證PIT。
- `market-lock.json`於2026-10-28T23:00:14.440794Z鎖定，SHA `63e262a1df0f419946093afb2d5eee9cc8ca374e97a118ddbb8ec3534edbf092`；原38比較／76檢定family不變，舊raw p及拒絕照帶入。
- 五fold同11,725場／23,393個book observations，N=2,592／1,896／2,596／1,943／2,698。先逐book算loss再同場平均，每場訓練權重合計1；不以平均概率代替平均loss。
- Proportional市場LL .58497479／Brier .20106651；offset .58507150／.20117815，兩項相對市場退步，只3/5段不退步。Offset相對純網球 .62044135／.21615562較好，但只證明市場資訊有用，**唔係網球修正改善市場**；整體REJECT_DEV。
- Power pooled LL gain+.00055089但CI跨0，Brier只有2/5段不退步；Shin LL gain+.00047621、未調整CI高於0，但Holm p=.755811，2025H1兩項退步。Inner五次選Power仍失敗。無改clip／fold／參數救結果。
- Hypothetical加權offset ROI −8.6798%（−100.035u／1,152.5u），95%CI［−13.9392%,−3.4854%］；純網球 −10.2537%。無報價時鐘，不可稱真實盈利。純去水在PS嘅6個假設下注全屬固定[.02,.98]clip造成假edge，raw去水無正EV；輸出已逐arm列clipping-created計數，無事後修改政策。
- 獨立script無import候選runner，重建24,857行七欄、五fold尺度／ridge gradient／inner選法、全部物理價格／概率／loss、4,000次bootstrap及76檢定，並重算ROI／假edge數，PASS。價格誤差0、最大概率1.84e−13、bootstrap3.47e−16。PIT FLAG仍在。
- `market-phase/report-export/`九份報告含exact nested round-trip Parquet、paired metrics、subgroups、calibration、分book ROI、row-flow、exclusions及feature availability，hash全部通過。獨立source/report及原始結果不覆寫，shared model runtime無改。
- 65項研究測試、quick及最終完整16組suite全通過（完整771秒）；無改／skip測試。結果只保存non-main研究分支，無release／activation。

證據沿用同一external run嘅`market-phase/`：`qualified-inputs/`、`market-lock.json`、`development/`、`full-identity-universe-audit.json`、`independent-replay*`、`report-export/`、`checkpoint-manifest.json`及保存後`checkpoint-git.json`。原source price檔在`f03-f09/price-official-prefix/`，網址及SHA不丟失。

本批checkpoint manifest涵蓋36份artifact，SHA256 `749dfeaf063b6113d8076ee9a1912d99aea31f2d48dedbb95367ab9ccff5b5fa`；三份stage manifest及原／新method lock全部核對未變。Git保存後SHA另記外置`checkpoint-git.json`，不以尚未產生嘅commit hash預填證據。

**下一步**：F01完整MCP／PBP解析及身份／coverage、F02歷年規則mapping、C14真正14日分鐘與完賽hours時間資格、C09 props合約；現有0份qualified live feature projection及daily board警告另須追查。不重跑失敗模型／擅改把尺；全部研究及提高準確度目標仍未完成。

## 2026-10-29執行更新：已完成首輪真正模型比較

[EXP-20261029-03](../experiments/EXP-20261029-03-tennis-unified-feature-study.md)完成來源隔離歷史cohort及F04／05／06／08；[EXP-20261029-04](../experiments/EXP-20261029-04-tennis-fixed-feature-head.md)完成相同features嘅非線性head。**今批10個特徵候選及1個head全部REJECT_DEV，未有合格候選入新forward。** 下方F00–02段保留初次checkpoint嘅時間及證據；當中價格缺失現況已由本節更新。

- 30,879 raw rows → 27,263 canonical完整賽事；24,880個2021起feature rows。176個season/calendar界線紀錄喺任何fit前由首版錯誤額外排除修正，兩版保留。27,131場有效雙方box scores；缺當場stats不剔走預測。
- `study-lock.json`喺首個候選fit前鎖定38比較／76個LL/Brier檢定，SHA `a5eb5f8be49213ad7731adfd12e88198916c0b3fedc2075fe345719562c61b64`。同13,274獨立場，五段N=2,937／2,162／2,944／2,315／2,916；448場至少一方cold-start亦保留。
- Surface收縮及serve R有細幅總增量，但有fold退步；R/E/S合併比原profile控制更差；opponent-strength及H2H亦未過穩定性。各serve candidate同000及B_simple比較，RES另有三個leave-one-out；無以較弱控制救失敗。
- C11只用原七欄、預定HGB設定。Refit logistic同原simple逐場誤差0。命中率64.8862%→65.1273%，但LL .62016007→.62116061、Brier .21605694→.21637029，兩項僅1／5段不退步；拒絕改用命中率救候選。原76名額維持，不重設family。
- 獨立script不import研究runner，重算全24,880行Elo／dynamic、全13,274場fitted probabilities／losses／bootstrap統計／76名額Holm，及固定seed100場raw serve/H2H，PASS。另一script核對五個自己產生嘅head model hashes／參數及全量推論，概率誤差0。證明計算一致，**historical publication-clock FLAG仍在，不能promotion**。
- 已有逐fold模型／scaler、JSONL、4000次paired bootstrap、全部校準／分層／排除／feature availability。另以外置隔離PyArrow18.1.0輸出兩份13,274場`predictions.parquet`，讀回逐欄／逐概率完全相同；shared venv正常import path無新增套件。可信報告在`report-export/`，包括paired_metrics.json、subgroups.csv、calibration.csv及明示N/A嘅roi_by_book.csv。首版formatter在`parquet-export/`誤將自己嘅空manifest digest計入，已留底並以新目錄修正；新18份報告檔hash逐一核對通過，預測bytes相同，原模型結果及manifest未改。

### 價格來源缺口已取得原檔；模型輸入資格尚待完成

舊URL及non-www變體均404；追查[固定版本公開原站連結](https://github.com/narvall018/tennis_modele/blob/ae98457673a0cccda3527e37cd08180e2fe36599/models/wta_live_strategy/metadata.json)後確認publisher目錄改為`hrjk-85HytOjkhth76j_ygh4jf7/`。**2020–25 ATP/WTA十二份原publisher XLSX全200 capture，27,795 raw rows**。六份2022–24與既有原站cache逐位元相同。另先凍結ATP鏡像作對照，2025版本與當次原publisher不同，兩者保留；價格實驗將用原publisher固定capture，唔按結果揀版本或把鏡像當新樣本。

原檔配對欄2020–24有B365／PS，2025另有BFE。新增價格類型／合約／commission尚未驗，不因欄存在就當普通可執行book價。部分實際Date跨season年界，inventory列出但唔直接當無效日期；後續canonical join按實際日期／賽事身份驗，不重犯檔名年份排除問題。Quote captured_at仍無證據；只能dev研究，Sportsbet forward不可由呢批價格替代。

**下一步**：先完成原publisher價格cohort嘅identity、同書合約、quote type及時間資格，凍結新phase input recipe，才跑原預留C02／C01／C13比較。Workload仍欠實際時間資格；F01全量parser及F02歷年規則mapping未齊，joint props另受合約閘限制。全部失敗候選不改判；現有Elo shadow不重設。統一研究／目標均未完成。

最新證據根目錄係同一external run下`f03-f09/`：`cohort-v2.json`、`features.json`、兩份lock、`development/`、`head-development/`、兩份independent-replay及其source、`report-export/`、保留嘅首版`parquet-export/`、`price-official-prefix/{source-spec,source-manifest,qualification}.json`、`price-mirror-atp/`、`price-nonwww/`。新snapshot冇複製；大型raw及自己訓練嘅模型只在外置碟。

`checkpoint-manifest.json`記錄108個新artifact hashes，SHA256 `a8851f74bfb44bb86e09984bcde8388133fe171b880eab6c522cd4a4eb4777cc`；另外逐項驗證五個可信model/report manifest目錄及原method／head source lock均未變。Formatter runtime binaries另由pip install-report記wheel hash，唔當模型輸入。保存後Git lineage另記`checkpoint-git.json`；全部研究仍為non-main、未activate。

價格phase須先鎖完整row-flow及身份規則：唔用winner／比分揀一個有利身份，應先有唯一event／round／format／pair對應，再核對label／比分；同場多book總權重1、切fold及bootstrap按match。各book先算loss再按match聚合，唔以平均概率代替平均loss。季檔名年份不代替實際日期；新增BFE合約未知先留置，唔暗中當普通book。

44項研究測試、兩次scope quick及**最終完整16組suite全通過**（Shared1,757／Tennis875）。此前只含feature研究嘅完整16組亦通過，兩份log保留；無新增skip／改測試救候選。模型／測試進程均已完成，無新forward／模型activation；研究失敗code及記錄保存non-main研究分支。

## 可核實成果及目前界線

- 已由四份**已安裝兼 loaded** Tennis launchd plist 確認 runtime：`/Users/imac/wongchoi-scheduler`，SHA `1f46514bf9f7ab3386e9054363da93baf9ad3d83`。四者同用主 checkout 嘅 live DB 及 venv interpreter；唔係 worktree 同名 DB。Daily 上次 exit=1，preclose=0；唔將「loaded」等同「最近成功」。
- Registry 仍為 `wc:tennis:model-release:tennis-pricing:8b149c85aafa:shadow`。Runtime code、登記 model release、歷史預測版本分開記錄，不將舊保存成績當成今日完整模型成績。Runtime 源碼已另外凍結，冇複製 `.env` 或 secret。
- 建立 [離線研究工具](../../research/tennis_unified/README.md)：create-only SQLite backup、source inventory、保存概率完整重現、固定來源 blob 驗證及 typed CSV 審計、獨立數學 oracle／MC 對照。所有 production consumers 未接入呢批研究工具。
- F00 方法及源碼已喺 `preflight_lock.json` 鎖定，未有候選 arms。**完整DB capture與Central corpus audit均已通過**：40張表、1,939,058,688 bytes、15,851行預測；SHA256 `67e62704fc83299ee1cb2172eed9a747aa9d46415bd24715c7fde6969aa02f58`。Snapshot從23:36開始，跨午夜00:15完成一致性／完整索引驗證；冇因慢而重啟或換語料。Central同時核對4份已登記archive及watermarks，全部ok。原本額外cache/mmap驗證只作讀取診斷，喺原完整驗證通過後取消，唔用佢當成功證據。

## F00：已量 baseline，同時發現資格缺口

3,845場有首份賽前預測及一致完成結果；排除280場冇首價、3場報價並非喺forecast前完成觀察／入庫、15場inactive fixture，餘3,547場。完整保存概率重現再排除66場metadata不足、1,734場冇active Elo、4場nudge重建不符，得到1,743場，誤差全部≤1e−6。

| 同一群體 | N | 保存模型LL | 去水市場LL | 保存模型Brier | 市場Brier |
|---|---:|---:|---:|---:|---:|
| 時間／市場資格 | 3,547 | .664201 | .560515 | .235416 | .190444 |
| 完整parity | 1,743 | .662752 | .572953 | .234516 | .195363 |
| 有frozen fixture兼parity | 7 | .854606 | .876647 | .324936 | .317031 |

1,743場 `market−model` LL gain = −.089799，95% match CI [−.105992,−.073217]；Brier gain = −.039153，CI [−.046255,−.031930]。係多個舊版本及級別混合嘅 **SEEN_DEV歷史診斷**，唔係今日main-tour完整模型表現。7場亦欠完整frozen raw-source資格驗證、遠低於600及power要求；唔當新holdout或可靠提升。

`audit_model_data.py --with-roi`完成，但**資料健康未全過**：83個有爭議／無效winner嘅fixtures（settlement已hold）、1個winner唔屬於該場球員、以及2026-08-27後3,087/13,243 props係post-start或無法定時。保留原觀察，唔刪結果或倒填timestamp救數字。新模型訓練須隔離不合格labels／inputs，promotion繼續封鎖；呢個問題唔可以用一份綠色code tests掩蓋。

營運另見連續2026-10-26／27／28 daily run回 `analysis_board_missing`（對應分析27／28／29日）；preclose雖exit=0但近期candidates=0。實際native log顯示：10月28日same-day有65／55場分析，但completeness gate因disputed fixtures（22057等）hold；next-day 24個fixture零Sportsbet價兼來源失敗。唔將舊全DB警報直接當成板缺失原因，亦唔移除完整性閘救發布。

既有canonical feature-provenance verifier實跑：120個prediction records、118個snapshot bundles verified，但**0份feature projection／0個qualified predictions**。118個blocker係`feature_artifact_missing`，2個bundle未驗。最近status artifacts明示`observation coverage incomplete`或`active Tennis component has unresolved warnings`。Builder已接入CLI，唔係單憑檔案不存在就判斷「未接線」；下一步要查實際observation／warning來源，不能倒填舊snapshot或清warning冒充證據。

### C10 歷史價格資料現況

已凍結現有2022–24 ATP/WTA共6份XLSX，合共15,388 raw rows，逐book只認同書成對欄，排除Max/Avg作book、禁止混兩書W/L。原始2020／2021／2025下載URL實測HTTP及HTTPS均404，全部列MISSING_SOURCE，不縮年份冒充完成。P04提供嘅Tennis My Life 2025兩份CSV可讀（ATP2,943／WTA2,622行），已另行凍結；headers只有賽果／排名／serve box scores，**沒有bookmaker價格**，所以不能補個價格缺口。未納入任何候選訓練，亦未改已鎖定時間fold。

## F01：已完成嘅來源盤點／仍未完成嘅全量資格

GitHub connector 已凍結 MCP commit `1813a1309b7ed7ebf1c7e884b32bf675d00e4edf`；較大 CSV 內容讀取回空白，所以 byte-transfer fallback 只取固定 commit 原始檔，驗 expected bytes 及 Git blob SHA。八份檔案合共約19MB，全部核對通過；冇執行外部 repo 程式／notebook／pickle。

| 已核對來源 | 實際結果 | 目前資格 |
|---|---|---|
| MCP 男子 metadata／Overview | 原7,566行；typed可用7,531；35行因欄位數／日期／賽制等留置；Overview56,850行，含 Total 及各盤，唔可全部加埋當獨立比賽 | 須再做 canonical identity join、來源發布時鐘及選樣 coverage |
| MCP 女子 metadata／Overview | 原4,264行；typed可用4,244；20行留置；Overview28,014行 | 同上；原始重複 keys 及異常值已保留 |
| P08 2024 US Open matches／points | 253個match IDs、45,289 point rows，match/point keys無重複；253行 winner/status metadata全空白；506行0X/0Y，server/winner=0 | 只係一站成對 schema 樣本，未完成全 corpus／terminal state／退賽與獨立結果核對 |
| P05 原 `JeffSackmann/tennis_pointbypoint` | GitHub API及公開web均404 | MISSING_SOURCE，不用另一schema靜靜取代 |

第一版 source audit 原樣保留為 `qualification.json`；型別留置修正另寫 `qualification-v2.json`。初版未驗日期就取 lexical max，得到 `RR`，唔係有效最新日期。V2先驗欄位／日期／賽制再計範圍，原檔及持有理由保留，唔猜測修復欄位。MCP typed範圍男子1960-05-29至2026-05-21，女子1979-09-28至2026-09-09；唔等於發布時鐘。

來源授權及 attribution 已記錄 NC-SA；目前只作研究 capture，未聲稱已取得商用 clearance。P08同源鏡像不計新增獨立樣本。以上資料**未入任何模型訓練**。

## F02：數學驗證

固定22個case、每個100,000 simulations、seed20260826、family-wise α=.01嘅 exact Clopper–Pearson／Bonferroni對照全部通過。涵蓋BO3/BO5、同質／不對稱 hold、先後發球、7/10-point TB；另有1-2-2、deuce closed form、swap/complement及set mass invariants。

呢個係**數學正確性結果**。現有MC只同「相同簡化hold-ratio TB假設」嘅DP比較；逐分oracle另外驗證，唔等於現有TB近似已獲真實賽果支持。歷史tournament/year賽制mapping、real-data Brier/LL、props market/settlement資格仍未完成。

另有確切API缺陷已喺研究分支修正：`MatchDistribution.player_wins_a_set('b')` 原用 `sets_a<=1`，A贏2-1時錯回0，實際B已贏一盤應為1。修正直接按所選球員贏盤數判斷；新增9個BO3/BO5確定比分測試，相關147測試通過。靜態搜尋只有定義及測試，現役daily win-a-set經另一條`set_joint`路徑；唔將修正呢個未接線helper當成已提高現役準確度。修正後另跑相同22-case數學對照，原結果及新結果分開保存。

規則來源：[ITF 2026 Rules，5(b)/6/7/14](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)、[AO官方計分說明](https://ausopen.com/articles/news/guide-scoring-tennis)。2019 AO與2022起其他大滿貫嘅final-set變化須用明示年份合約處理，唔統一回填現代規則。

## 尚待執行

Baseline及row-flow已保存；下一步係完成source/feature及label隔離資格、追查目前每日board缺口，再完成F01 parser／全量盤點與F02歷史規則mapping，先鎖F03–F09全比較清單／消融。價格缺失嘅依賴要明列，不換窗救候選。勝出候選才F10及新forward。現有Elo shadow不重設；600 floor/power、未看過嘅forward及promotion gate不變。未有任何候選獲KEEP或promotion。

校準／CLV／ROI／coverage嘅promotion數值須追溯frozen ruler及現有執行contract；無數值來源就列gap，唔自創門檻。Registry/runtime不一致亦須先分清來源，不因目前模型落後就改尺。

## 證據位置及驗證

External run：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/`。有 `run_manifest.json`／完整DB、`warehouse_inventory.json`、`baseline/`全部summary／paired rows／excluded rows、`preflight_source/`／`preflight_lock.json`、`runtime/`、`sources-f01/`、`books-2020-2025/`、`tml-source-check/`、`tennis_feature_provenance.json`及兩版`kernel-f02*/`。兩版kernel全部22個case數值相同，第二版另記legacy simulator精確source hash。`checkpoint_manifest_20261029.json`記217個已完成artifact hash；較後完成嘅feature verifier另有content hash及checkpoint addendum。原始結果／失敗抓取及三份完整gate log都保留。

20個研究測試通過；快速檢查通過。第一次完整檢查：Tennis866測試通過，但sandbox阻擋HKJC測試寫log及NBA測試讀`ps`；正常權限重跑完整16組suite通過。API修正後147個相關測試通過，最新完整gate再跑亦**16組全部通過**（含Tennis875）。全部log保留，不改／跳過測試掩飾失敗。研究未完成部分保存在非main研究分支；不部署。
