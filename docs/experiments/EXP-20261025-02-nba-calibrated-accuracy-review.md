# EXP-20261025-02 固定真價集合內的機率排序審計

- 基準：beb9cade56d8746432da90084476d5b437df9a2d；C機率／正式selector／EV閘／B0/B1/B2不變。
- 已搜：EXP-20261022-02（stat白名單／CoV／賠率過濾未確認）、20261024-02／03；20261025-01研究分支（分鐘／產出趨勢未晉升）。本輪不是重試stat禁令或fit新模型。
- 假設：在既有有界搜尋已報價的相同候選集合內，按現有adjusted joint probability排序，是否比現役L10排序候選更適合準確率目標。研究工具只提供可驗證比較，不代表改善已證明。

## 實作前固定規則

獨立family banker-accuracy-review-v1，A0為既有Q1現役selector候選，A1為同一quote_attempts集合內真實SGM價>=2、已通過capture驗證、完整有限機率的最高adjusted_joint_probability。只改排序：相同joint時依最弱單腿機率較高、腿數較少、固定hash排序。不新增機率門檻、角色過濾、白名單、機率修正或報價。A1可為負EV，必須明列，不升為BET、不算正式ROI。報價到期後不得成為current候選；歷史capture留作不可交易證據。

集合受既有shortlist及報價預算限制；不是全市場最優解。保留原Q0/Q1/Q2規則與結果，新比較不改原family。每腿額外顯示C/現有模型機率、L10/L5、CoV及平均分鐘；缺資料明列missing。歷史原生報價檔未有新增欄位就留空，唔事後補成當時已知。

球員主要角色不由姓名／位置／PTS和AST數值大小推斷。Herro舊L10混合新隊2場及舊隊8場，新隊AST_PCT僅2場支持；這是角色穩定證據弱，不是證明射手不能買助攻。未有足夠同隊歷史／potential assists，不硬加角色filter。

## 評估與時間界線

2026-10-25結果已看過，全部只作描述及正確性檢查，不作holdout或調參。既有2026-10-24搜尋報價與翌晨final_refresh不同，重播結果必須分開，唔同4中6前瞻候選混比較。新forward資料要在未見結果前凍結A0/A1、模型ID、原生quote及最弱腿；報命中率、同場配對差、覆蓋率、真價ROI、校準。確認規則及功效需另定；30個賽日只有營運檢查用途；promotion_allowed=false。

狀態：協議於任何A1結果前固定。工程工具可發佈，但不採用A1作正式穩膽，未證明準確率／盈利改善。

## 固定規則重播結果（已見日，非採用證據）

來源：既有engineering-preview的8份`.banker_search.json`，保存原生capture機率及真價。回放時current候選一律null（舊價已過期）。不重新報價，不與翌晨final_refresh混為同一批候選。

| 指標 | A0現役排序 | A1固定joint排序 |
|---|---:|---:|
| 有真價>=2候選 | 8/8 | 8/8 |
| 平均模型joint | 32.30% | 43.30% |
| 已有完整box score組合 | 6 | 6 |
| 全中組合（僅描述） | 4 | 5 |
| 最弱單腿機率的全體最低值 | 52.4% | 52.9% |

A1仍選Herro AST 4+（該capture為62.5%，非翌晨64.3%），未解決角色可靠性；WAS–CHI將Buzelis REB 6+改為4+，並加入Trae Young PTS 15+。機率排序提高模型自身目標屬預期，不等於實際準確率已改善；6場、已見結果不足以判勝，亦不因5/6再調規則。新工具只公開可重現研究比較，不改正式selector、不晉升A1。

主結論：舊L10優先與C機率不一致是值得驗證的設計問題；角色是另一個需獨立PIT資料及消融的假設。AST_PCT有現有抽取入口，但Herro的新隊當季樣本只有2場，沒有potential assists／持球時間或足夠同隊資料證明角色穩定；不能以「主要射手」印象硬禁助攻。未測角色filter，未聲稱角色filter提高準確率。

重現：在此commit的worktree執行證據目錄`Replay_Accuracy.py`；固定source與code SHA見`prerun.json`，完整逐場結果見`Replay.json`。原始quote檔位於`/Users/imac/WongChoiData/NBA_Research/2026-10-24-banker-search-audit/engineering-preview/`；六場box score使用`2026-10-25-forward-review-0356/Results_Brief_2026-10-24.json`。

工程：27項search／accuracy針對測試及quick通過；完整發佈gate及實際commit見證據目錄Final_Verification.json。只在既有`--banker-search-audit` opt-in模式出現新欄位，未啟用每日排程或改Dashboard。狀態NEEDS MORE TESTING。

補充覆蓋診斷（不是新候選／調參）：同一已報價集合內，僅3/8場有全部單腿現有機率>=70%的組合。此70%只作易讀參考，沒有設為filter。高命中可靠性與每場都有組合／真價>=2存在取捨；受報價預算限制，不能推論其餘5場全市場找不到。
