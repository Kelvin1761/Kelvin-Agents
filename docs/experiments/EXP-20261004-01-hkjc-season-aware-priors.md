# EXP-20261004-01 — HKJC 季初 current-season priors

- **日期**：2026-10-04
- **平台**：HKJC
- **狀態**：KEEP DATA REPAIR / LIVE WEIGHTS UNCHANGED / FORWARD MEASURE
- **上游**：EXP-20260910-01、EXP-20260929-03

## 問題

`26/27` 賽果已保存 7 個賽日、67 場、847 runner-results，但
`build_comprehensive_stats.SEASONS`、production `GENERAL_PRIOR_FILES`／
`MASTER_STATS_FILES` 同 PIT loader 仍只列 `24_25`、`25_26`。所以統計檔即使今日
重建，live 騎練先驗仍睇唔到今季結果。研究 dataset 亦將 HKJC 四元組
`(冠-亞-季-其餘)` 錯標成 starts/wins/seconds/thirds。

呢兩項屬可以獨立證明嘅資料正確性缺陷；即使績效方向相反亦要修。但任何
season weighting／7D 改動仍要行候選閘，唔會借「資料修正」名義偷渡。

## 凍結改動

### D1 — season discovery（正確性）

- `build_comprehensive_stats` 從 canonical `hkjc results YYYY YY` 目錄發現賽季。
- 有 materialized `race_results_YY_YY.csv` 就用佢做 base；新季未有 base CSV 時，
  只由已完成 meeting 嘅 `full_day_results.json` 建立 current-season master／combo／
  change 統計。
- production priors 讀所有 materialized season stats；現有 `24_25` trainer ×0.3
  衰減維持不變，其他 season 沿用1.0。今次唔搜尋新衰減值。
- PIT loader 同步讀相同 discovered seasons，並嚴格 `Date < target_date`。

實作途中發現 JSON 雖然冇獨立 `distance`／`track` 欄，但官方
`sectional_times` header 完整保存「1200米」及「草地／全天候」；因此偏離最初
「distance priors 保持空」嘅保守假設，改為只從同一份官方 header deterministic
還原。呢個唔係外部補值，亦冇睇未來結果。

### D2 — HKJC record tuple（正確性）

研究 dataset 將 `(冠-亞-季-其餘)` 正確輸出為：wins、seconds、thirds，starts 等於
四項總和。唔改 production `parse_record`（佢已經正確）。

### M1 — season reliability（候選，唔直接上線）

今輪唔改7D外層權重。current-season rows 透過現有 empirical-Bayes `k=100` 自然按
樣本量向全體平均收縮；combo／distance 亦保留既有 minimum-start gates。若 D1 只靠
正確資料仍未能通過零退步，唔再事後搜尋 shrink 常數，轉做 forward shadow。

## 固定評估

- baseline、D1、D2 必須同一 corpus；D2 只應改 research columns，engine ranking
  bit-identical。
- 2026/27 replay 只可用每個 target meeting 前已完成賽果；禁止用10月4日結果。
- 報 canonical Gold／Good、capture@5、NDCG@5、top5 pairwise AUC，同沙田草地／
  跑馬地／AWT cohort。
- 因2026/27已被用作問題診斷，結果只可證明 no-regression／接線，唔可叫 blind
  promotion。真正改善要由10月4日後 immutable snapshots forward 證明。

## 預定判決

- D1、D2：按 evaluation contract §7 正確性修正；要 leakage PASS、冇顯著 primary
  regression、golden／data-contract／完整測試全綠。
- M1：若只有 retrospective 正向，仍然係 NEEDS MORE TESTING；不可稱已改善。
- 不論結果，唔會自動 commit、push、merge 或 deploy。

## 結果（2026-10-04）

### 資料完整度

- 發現並建立 `26_27`：7 個已完成賽日（2026-09-06→2026-10-01）、837 個有效
  finisher rows。
- `Date/Venue/Track/Distance/Horse/Jockey/Trainer/Rank` 缺失全部 0；沙田543行、
  跑馬地294行；草地801行、AWT 36行；同日同馬重複0。
- 產出：22騎師、23練馬師、126騎師×路程、131練馬師×路程、268騎練組合。
- production manifest 已見 `24_25 / 25_26 / 26_27`；歷史 replay 仍受 point-in-time
  guard 保護，唔會讀 latest snapshot。

### 嚴格 PIT A/B

同一個 live engine、同一批67場逐場重跑；baseline 完全剔除 `26_27`，candidate
只容許 `Date < target meeting date`：

| cohort | races | Gold Δ | Good Δ | Champion Δ | Top3 champion Δ | Single Δ (95% CI) |
|---|---:|---:|---:|---:|---:|---:|
| 全部 | 67 | 0.00pp | 0.00pp | 0.00pp | 0.00pp | −1.49pp [−4.48, 0.00] |
| 沙田 | 42 | 0.00pp | 0.00pp | 0.00pp | 0.00pp | −2.38pp [−7.14, 0.00] |
| 跑馬地 | 25 | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 0.00pp [0.00, 0.00] |

primary Gold／Good 同冠軍指標全部 bit-equivalent；只有沙田一場最低門檻由命中變
唔命中，CI 接觸0而且唔係 primary。故 D1/D2 按 §7 保留為資料正確性修正，但
**唔聲稱提升模型表現**，亦唔用呢67場搜尋 season multiplier／改7D權重。

## 判決

- **KEEP D1**：新季統計自動發現、官方 header 路程／泥草還原、live priors 接線。
- **KEEP D2**：研究四元組 parser 修正；production parser 本身冇錯。
- **HOLD M1**：現有 EB／權重不變。67場證明接線冇 primary regression，但冇改善
  證據；10月4日後 immutable snapshot 繼續收 forward evidence。
- 唔 commit、唔 push、唔 deploy；今日已生成本機 `26_27` stats snapshot，供下一次
  pre-race run 使用。

## 10月4日沙田賽後固定 replay（2026-10-05）

賽後先從 HKJC 官方賽果抽取11場結果；評分輸入鎖定最後一份真正賽前 immutable
snapshot（`20261004T111833.253092+1100-c0c429faff67`）。23:59 賽後 automation
重跑嗰份唔當預測。candidate 只用 `Date < 2026-10-04` 嘅21,944行 PIT 資料，最新
賽果係10月1日，冇將10月4日結果餵返入評分。

| 指標 | 原本賽前分析 | season-aware重計 | Δ |
|---|---:|---:|---:|
| canonical Gold（實際前三全入model Top 4） | 18.18% | 27.27% | +9.09pp |
| Gold strict（model頭三全上名） | 18.18% | 18.18% | 0.00pp |
| Good positional（第1、2選都上名） | 45.45% | 36.36% | −9.09pp |
| Min（頭三選至少兩匹上名） | 72.73% | 63.64% | −9.09pp |
| Single | 90.91% | 90.91% | 0.00pp |
| Champion | 18.18% | 18.18% | 0.00pp |
| Winner in model Top 3 | 72.73% | 63.64% | −9.09pp |
| 實際前三 Top-4 capture | 21/33（63.64%） | 22/33（66.67%） | +3.03pp |
| 平均頭馬排名（低為佳） | 3.182 | 3.273 | −0.091 |
| MRR | 0.4828 | 0.4492 | −0.0336 |

candidate 喺R1將實際第三名補入第4選，所以 canonical Gold／Top-4 capture增加；但R11
將頭馬由第2選推落第4選，直接失去一場 Good、Min 同 Winner-in-Top-3。按照 evaluation
contract「任何 primary 點估計回歸即 reject」規則，呢個係 **TRADE-OFF／NO PROMOTION**，
唔應用賽果事後覆寫10月4日分析。資料接線正確性修正照留，權重照舊。
