# EXP-20261029-06：MCP／全量單打逐分來源及歷年規則資格

2026-10-29 Sydney；統一研究F01／F02、C07／C08／C14／C16。呢份係**資料及正確性審計**，無新候選fit、無重新揀模型或改原76檢定family。EXP03–05全部15個候選保持REJECT_DEV。

## 固定來源及界線

沿用一次完整warehouse snapshot及市場批次clean source cohort，不複製DB。MCP固定commit `1813a1309b7ed7ebf1c7e884b32bf675d00e4edf`，審計完整男子／女子metadata及Overview；唔聲稱已讀MCP所有shot-by-shot檔。P08固定commit `83733587353df8a41f2fd4f516147d5aa83f5a8d`，GitHub connector重新核對完整tree後，在下載前固定**全部49站、98份adult main-draw singles matches／points**，合共272,359,879 bytes。雙打／混雙排除；同源Aneeshers鏡像不算新增獨立樣本。

逐檔驗bytes、Git blob SHA及SHA256；沿用原2024 US Open兩份capture，唔重下載或另算樣本。新transfer有固定spec及每檔receipt，resume先驗bytes/hash，不改source roster；舊檔遺漏receipt時不捏造retrieved_at。原P05 `JeffSackmann/tennis_pointbypoint`仍404，encoded-string schema **STOP_MISSING_SOURCE**，不偷換成Slam CSV宣稱完成。

所有原檔／版本／URL／下載時間在同一external run嘅`f01-full/slam-singles/source_manifest.json`。來源attribution及NC-SA限制沿用upstream README；capture只供研究，無聲稱商業使用clearance或歷史發布時鐘已驗。

## MCP：身份、點數及選樣

身份宇宙用全部30,879原始紀錄，不先按complete／比分篩選；兩條相同身份觀察collapse成30,877個key。146行surface空白保留作潛在歧義，不能先剔除再稱唯一。按tour、唯一完整姓名、unordered pair、event／round／surface／best-of及實際chart day距tournament start 0–20日選身份，**之後**才驗Overview。

只取兩個player嘅`Total`；每盤rows不再加一次。檢查整數／非負／分母、first/second exposure、雙方serve／return點數守恆，再同原source雙方box逐項比較。重複chart映射同一canonical match全部留置，不選第一份或吻合比分嗰份。

| MCP metadata／Overview | ATP | WTA |
|---|---:|---:|
| 原metadata | 7,566 | 4,264 |
| Typed metadata | 7,531 | 4,244 |
| 唯一身份配對key | 2,678 | 1,767 |
| 身份及雙方點數同原source一致 | 2,377 | 1,525 |
| MCP與source box衝突（留置） | 234 | 195 |
| Clean source母體 | 14,257 | 12,980 |
| 點數一致覆蓋率 | 16.6725% | 11.7488% |

合共3,902場點數一致，唔係新增3,902場獨立賽事。Final覆蓋ATP44.89%／WTA27.84%，R32只有11.93%／8.89%；不能將crowdsourced charted subset當隨機樣本或已矯正選樣偏差。各surface／level／round分層、malformed原值及全部原因另存報告。

**C07決定：NOT_QUALIFIED_FOR_SOURCE_AUGMENTATION。** 3,902場只證明相應身份／點數一致，全部欠chart提交／發布時間；capture／commit時間唔係當年可用時間。唔用呢批額外來源fit feature／augment corpus，亦唔根據point衝突去揀一個有利來源覆寫原結果。

額外回查上一價格研究：146行unknown surface喺寬鬆pair／day／format篩查有一個重疊，但原紀錄係BJK Cup RR，實際book係1st Round；既定round合約本來已排除。寬鬆FLAG及實體原行／book核對PASS分開保留，原23,225場價格cohort無改。

## P08：全量逐分重建及格式差異

全部49站共有10,513行metadata、1,922,136 point rows；無points-without-metadata。逐行記錄duplicate／gap、server／winner、point ordering、比分、TB、terminal state、metadata status／winner及原canonical結果。不能從贏分數較多推斷贏比賽；不能插補缺點、刪退賽、或改winner救解析。

審計過程確認三類source schema：

- IBM比分採每盤GameNo及贏局後score重設0；開場可能係`0`或`0X/0Y`非比賽marker，唔計作一分。
- 2018–21 AO／French轉換檔GameNo跨盤累計；2020–21 French及2021 AO贏局score可為`GAME`，TB終局仍係數字。只按明示event/year選schema，唔按候選結果或逐場「邊個parser過就用邊個」。
- 空白GameWinner／SetWinner／累積點數等仍係missing，不能當0。分開記`state_machine_pass`及`full_scoreboard_verified`；成功由逐分推導terminal，亦唔會填回原本空白metadata winner/status。

首版將0 marker誤當缺點及空白欄當比分衝突；v2保留missing及0 marker；v3加入累計GameNo／GAME；v4核對2011 `round_1`–`round_7`、Quarters及Semis明示別名。**所有版本保留**，無模型fit／績效選擇介入。最終可信輸出用`slam-audit-v4/`，首三版只供forensic比較。

最終v4：**7,596場state-machine pass，其中6,101場full scoreboard亦驗證**；其餘1,495場係已明列部分scoreboard缺欄，不能稱完整欄位驗證。全量10,513場中，1,872場同clean source身份、terminal賽果／逐盤比分及雙方發球點數一致；8,641場留置或在固定canonical年份外，無偷縮raw行數。

| v4逐metadata去向（互斥） | N |
|---|---:|
| 身份／terminal／發球點數一致 | 1,872 |
| 逐分規則或供應比分矛盾 | 2,880 |
| 固定canonical 2020–25年份外 | 4,809 |
| 完整姓名缺失／歧義（含initial-only名字） | 911 |
| Participants無效 | 32 |
| 有metadata但無points | 5 |
| Metadata明示非完整賽事 | 3 |
| Canonical label／contract原已留置 | 1 |

原始points讀取1,922,136行；可逐步重建1,880,215個numeric points。出現致命point gap／service錯誤後不插補，餘下raw仍保留，唔將部分成功當完整match。所有供應比分錯誤、時間倒退、retirement及缺值另列。

獨立script**不import研究parser**，重核98個physical blobs及全部MCP3,902個full-universe身份／點數；另一條按原SetNo／GameNo分組嘅逐局計分／發球順序重建，覆蓋全部7,596個passing point matches，再核對1,872個canonical結果，PASS。MCP與Slam嘅已配對canonical key有424場重疊，union 5,350；同場兩來源不能當兩個獨立樣本。

**C16 Slam決定：全量審計完成，NOT_QUALIFIED_FOR_SOURCE_AUGMENTATION，training eligible仍0。** 無historical publication clocks，任何parser成功都唔會自行取得training／promotion資格；P05 missing schema亦維持停止。

## F02：Slam歷史規則合約

只涵蓋P08 adult main-draw singles、2011–24；ATP BO5、WTA BO3。所有非決勝盤係6–6打7分TB；下表係決勝盤，均須領先兩分或兩局。其他年份、賽事或draw明確UNKNOWN，唔默認現代規則。

| 年份 | AO | French | Wimbledon | US Open |
|---|---|---|---|---|
| 2011–18 | advantage set | advantage set | advantage set | 7分TB @6–6 |
| 2019–21 | 10分TB @6–6 | advantage set | 7分TB @12–12 | 7分TB @6–6 |
| 2022–24 | 10分TB @6–6 | 10分TB @6–6 | 10分TB @6–6 | 10分TB @6–6 |

依據：[AO2019官方格式公告](https://ausopen.com/articles/news/final-set-tiebreaks-australian-open-2019)、[WTA轉載AELTC2019公告](https://www.wtatennis.com/news/1438560/wimbledon-announces-final-set-tiebreak-from-2019)、[US Open／Grand Slam Board 2022公告](https://www.usopen.org/en_US/news/articles/2022-03-16/us_open_to_join_all_grand_slams_in_playing_10point_final_set_tiebreak.html)、[US Open舊TB歷史](https://www.usopen.org/en_US/news/articles/2020-09-02/the_us_open_introduced_the_tiebreak_set_50_years_ago_today.html)及[AO回顧說明](https://ausopen.com/articles/news/guide-scoring-tennis)。一般發球1-2-2／轉盤首發及計分法另依[ITF Rules5/6/7/14](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)；ITF2026唔當舊年份event assignment證據。

測試涵蓋7／10分不提早終止、12–12與advantage分別、deuce／AD、TB後由first receiver先發、terminal後禁止加點，以及未知歷史規則無fallback。呢個係source replay／數學合約，**未改正式simulator**。現有legacy MC仍只用hold-ratio近似、無歷年TB輸入，唔將原22-case相同假設下DP/MC通過當作已支援全部歷史規則或真實準確度改善。

## C14：時間資格停止，唔造疲勞數字

全30,879條raw：28,376有正minutes、129係0 sentinel、2,374缺失。所有非空時間相關欄只有`minutes`及`tourney_date`，無實際開始／完賽UTC；原23,225場book calendar Date亦唔係end clock或報價發布時鐘。

按原source tournament-start context及+21日release政策，不能建立真實14日工作量／rest-only控制／距完賽hours；選樣Slam嘅ElapsedTime亦唔補到全tour實際賽日、end clock及當時可用性。**STOP_INPUT_QUALIFICATION_C14**：五個workload比較保留原名額、raw p=1、零fit。不將未觀察最近minutes填0，不用盤數冒充minutes，不移動forecast context或fold救可跑性。

## 重跑及證據

Repo方法：[MCP qualification](../../research/tennis_unified/mcp_qualification.py)、[source capture](../../research/tennis_unified/slam_capture.py)、[point state machine](../../research/tennis_unified/slam_points.py)、[full audit](../../research/tennis_unified/slam_qualification.py)、[rules](../../research/tennis_unified/slam_rules.json)。外置`f01-full/`保存原檔／receipts、MCP、四版Slam報告、unknown-surface核對、workload資格及獨立script／hash。全部不接production。

```bash
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
RUN='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028'
PYTHONDONTWRITEBYTECODE=1 "$P" -m research.tennis_unified.slam_qualification --manifest "$RUN/f01-full/slam-singles/source_manifest.json" --cohort "$RUN/market-phase/qualified-inputs/cohort.json" --database "$RUN/warehouse.db" --output "$NEW_CREATE_ONLY_AUDIT"
```

未有C07／C16新source獲准入訓練；C14停止；C09聯合props仍受無合格serve候選及獨立market／settlement合約限制。新forward及activation均未啟動，統一研究／提高現役準確度目標未完成。

90項研究測試及最後quick通過；完整16組suite亦全部通過，無新增skip或改正式測試。獨立source replay、九份CSV／JSON報告及hash manifest另存`f01-full/`。無candidate predictions所以唔製造空Parquet／ROI檔冒充績效交付。研究方法及暫停判決保存non-main分支，不release。
