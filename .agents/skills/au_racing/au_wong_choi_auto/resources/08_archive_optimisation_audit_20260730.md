# AU Wong Choi Archive Optimisation Audit — 2026-07-30

## 結論

今次以 current Python `RacingEngine` 重新評分 710 場、7,530 匹已對齊
archive 馬匹。主要成果係修正資料／語義 bug、移除已證實無效或不穩定嘅
ranking micro rules，同保留經時間切割驗證仍然有用嘅核心矩陣。未有任何新
interaction 或 top-level 權重改動同時通過 development folds、獨立第五 fold
及 terminal 15% holdout，所以冇為追求 in-sample 數字而加入新規則。

Current runtime baseline：

| 指標 | 710 場結果 |
|---|---:|
| Gold / Good positional | 40 / 136（5.6% / 19.2%） |
| 0-hit / 1-hit | 87 / 335（12.3% / 47.2%） |
| Top-3 capture@5 | 65.8% |
| Winner@3 / Winner@5 | 52.3% / 72.0% |
| Top-5 false contender rate（實際第 6+） | 38.1% |
| Mean / median within-race score SD | 3.440 / 3.243 |
| SP ≥ 31 actual Top-3 captured@5 | 41 / 167（24.6%） |

呢份 baseline 係診斷基準，唔係聲稱已經預測到 exact Top 3。優先目標仍然係
提高真正有競爭力馬匹進入 Top 5 嘅 recall，同減少 0-hit，而唔係事後追逐
精確名次。

固定 scoring snapshot 嘅同場版本比較：

| 版本 | Dev Comp R@5 | Dev NDCG | Dev 0-hit | Terminal Comp R@5 | Terminal NDCG | Terminal 0-hit |
|---|---:|---:|---:|---:|---:|---:|
| Archived mixed production | 62.94% | 52.06% | 14.26% | 58.67% | 45.85% | 19.26% |
| Current weights, pre-clean | 63.23% | 52.43% | 12.52% | 59.00% | 46.69% | 17.78% |
| Signal-cleaned | 63.42% | 52.62% | 12.35% | 59.19% | 46.70% | 17.78% |

上表用同一批 archived leaf/matrix snapshot 比較 model version；下面嘅 710 場
current runtime baseline 則係由 raw Logic 重跑完整 engine，兩者用途唔同，唔應
混合當成同一條 score series。

## 資料對齊及 bug 修正

1. Cache manifest 加入 schema、archive/results source path 同 file signature；
   source 改變就拒絕舊 cache。CSV、JSON、manifest 改用 atomic write。
2. 歷史結果按 date/track/race 驗證：少過四匹、冇頭馬、或少過三匹 Top-3
   label 嘅 race 會隔離。呢個規則識別並排除 `2025-08-09 Randwick`
   全部馬錯標 position 8 嘅 corruption。
3. Result position、SP 同 barrier result label 只喺 pre-race scoring 完成後
   join；唔會進入 `race_context`、horse input 或 feature computation。
4. 修正 jockey-horse fit 將 wins 再加落 formal places 嘅 double count。
   Racenet `places` 已包括 wins。
5. 修正 generic jockey-change text 令 upgrade/downgrade tier 判斷永遠
   unreachable 嘅 alignment bug。Tier 變化而家可以正確描述，但因 710 場
   folds/holdout ranking 結果唔穩定，唔會直接加減分。

Archive 掃描共有 739 個 direct Logic files；710 場完整對齊，22 場冇可對齊
result race，7 場 horse/Top-3 overlap 不足。所有 rejected races 都明確記錄，
唔會靜默混入樣本。

## Production model 簡化

以下只係移除 dead、重複或未能泛化嘅 ranking code；展示／診斷資料仍然保留：

- `class_weight` 移除重複嘅 direct `class_score` leaf，改用 neutral-centred
  formula；class 仍供 contextual interaction 同報告使用。
- 移除 class-up zero penalty、latest RT high/low modifiers。RT 能力已經由
  rating／sectional 層表達。
- 移除冇統計時按內外檔猜測嘅 pace fallback。
- 移除 jockey token 名單 fallback；冇 DB／官方統計就中性 60。
- 移除 trainer hardcoded elite fallback 及未有重複驗證嘅低場地上名率微罰。
- 移除未有一致 holdout 支持嘅 jockey-change upgrade/downgrade 大額分數。
- 移除 archive 未有正確觸發、亦未通過驗證嘅 wet-bloodline bonus。
- 保留 pace base、career-15 maiden suppressor、pace、fit、trainer、track 等
  經 ablation 顯示仍有作用嘅核心訊號。

將全部 micro families 一次刪除會令 development competitive recall@5
跌 1.68pp、NDCG@5 跌 1.27pp、winner@5 跌 1.74pp，terminal 亦變差。
因此「簡化」唔等於將整個模型削平；只刪除有 archive 證據支持嘅噪音。

## Failure analysis

- 730 匹 actual Top-3 落喺 model rank 6+；常見低位來源係 stability、
  pace performance、track、class/rating evidence，以及 consistency、
  sectional、form 同 trial。
- 1,353 匹 model Top-5 最終只得第 6+，顯示 false contender 仍然係下一輪
  最值得研究嘅問題。
- 0-hit race mean score SD 3.348，而 2+-hit race 係 3.493；差距唔大。
  失敗主因唔係普遍分數壓縮，單純放大分差會增加假信心。
- 13+ 大場 0-hit 率 16.8%，1–8 匹細場只係 1.4%。大場、資料缺失同
  extreme outsiders 應該繼續做獨立 cohort review。
- SP ≥ 31 actual Top-3 平均 model rank 8.09。市場賠率只用作賽後 cohort
  label，絕不作 pre-race model input。

## Racenet 欄位及新訊號評估

Feature within-race AUC 較穩定嘅包括 form、consistency、trainer、rating、
jockey；distance 亦有穩定但較細嘅訊號。新近先有較完整 coverage 嘅 measured
pace figure 喺 recent/terminal window 有價值，但舊 archive 大量缺失。

已測試但冇升 production：

- 將 distance 加入 class matrix、由 track/race-shape 轉權、或只喺高分時
  conditional 加權：部分 development 指標改善，但較後 fold／terminal
  competitive recall 或 0-hit 轉差。
- recent settled/400m shape × expected pace interaction：大場 development
  有細改善，但 2/5 folds NDCG 為負，terminal 冇增益。
- 90 個單一 matrix pair weight transfers：早段最佳係 stability →
  race-shape 3%，但獨立第五 fold competitive recall 跌 0.41pp，terminal
  0-hit 增 0.74pp；保留現行 top-level weights。
- 可解釋 pairwise linear ranker（只用之前日期訓練、目標係 leading-third
  competitive tier）：`matrix_6 + distance` 喺 terminal 有 NDCG +2.91pp、
  winner@5 +7.41pp、0-hit -2.22pp，但 earlier folds 只有 3/5 NDCG 同
  3/5 0-hit 非負。跨七個 SGD seeds 及 seven-model averaged weights 後，
  最早 fold 仍有 competitive recall -3.84pp、NDCG -4.10pp，最後
  development fold winner@5 -5.17pp。呢個係 data coverage/regime drift
  下未能泛化嘅 shadow candidate，唔升 production。
- generic jockey upgrade/downgrade scoring：雖然修正後影響 511 場分數及
  286 場排名，時間 folds 方向互相衝突，只保留準確描述。

`distance_profile`、recent shape/entropy、formline 等 Racenet 欄位已列入
coverage audit；要升級成 ranking feature，必須再有新增、較完整嘅前瞻資料窗，
並通過相同 fold + terminal gate，唔應再加單場式 micro rule。

## 防 hindsight／overfit 規則

- Outcome/SP 必須 scoring 後先 join。
- 任何候選至少報 development、五個時間 folds、terminal 15% holdout。
- Weight search 只准 folds 1–4 揀候選；fold 5 同 terminal 只作確認。
- 優先 gate 必須同時包括：
  - `Good positional` 不跌，即 model Rank 1、2 都跑入實際 Top 3；
  - actual Top-3 全部落入 model Top-4 嘅比率不跌（dead-heat safe）；
  - competitive recall@5、NDCG@5、winner@5 不跌，同 0-hit 不升。
- 改善只出現喺單一窗口、單一場地或細樣本，就保持 shadow，不升 production。
- 新資料應優先改善 missing evidence，而唔係將同一 narrative 重複計分。

## Corrected-gate fresh optimisation loop

2026-07-30 再做一次由 failure review 開始嘅迭代。Google Drive connector
完整讀取 84 份 `Meeting_Auto_Scoring.csv` 同 850KB 歷史結果表；7,679 匹
成功按 date / track / race / horse 對齊。清洗後重現 710 場：

- `2025-08-09 Randwick` 132 行結果全部錯標 position 8，整日隔離；
- `2026-04-08 Sale R2/R4` 分析 field 冇包含後來入位嘅馬，屬 pre-race
  coverage 缺口，唔作事後補馬；
- `2026-06-27 Caulfield R3` 係四匹 dead-heat Top-3 集合，保留並用
  dead-heat-safe Top-4 gate。

Drive scoring snapshot只用嚟發現 hypothesis；production promotion仍以 raw
Logic current-engine gate為準。新一輪預先限制候選範圍，冇按個別賽果開
exception：

| 方向 | 候選設計 | 結果 |
|---|---|---|
| 多證據共識 | people/rating、contender core、balanced core；4個細幅度 | 12個全部未過 selection + fold-5 + terminal |
| 13+ 大場 | 兩組共識、4個幅度，只喺大場啟動 | 有4個過早期 selection，但全部喺獨立 fold 5 跌 recall/NDCG/W@5 |
| 假爭勝／首選大敗 | rating、jockey、distance、pace-map、track 弱支持 swap/penalty | swap terminal NDCG -0.18pp；最佳 penalty 早期 0-hit +0.20pp |
| 冷門／孤立強證據 | strongest-one / strongest-two evidence，全部馬或 rank 4–8 | 16個全部未過 selection；早期 outsider capture多數倒退 |
| 可解釋 pairwise | 既有 matrix-6 + distance expanding walk-forward | terminal好但 earlier folds及seed ensemble方向衝突，新增 Good/Top4 gate下仍不可升級 |

呢次 fresh loop冇 production scoring候選同時守住正確 Good、Top3-in-Top4、
competitive recall、NDCG、winner@5同0-hit。停止再加規則係實證決定：
繼續調 threshold只會用 confirmation結果反向揀參數，構成 overfitting。
下一個合理重開條件係有新增、完整嘅前瞻 meeting window，而唔係再搜尋同一
710場。

## 重跑

主要 reproducible 工具：

- `au_runtime_micro_ablation.py`：raw Logic current-engine micro/group ablation
- `au_runtime_failure_audit.py`：0/1-hit、misrank、cohort、outsider、coverage
- `au_signal_simplification_audit.py`：matrix/leaf neutral ablation
- `au_feature_value_audit.py`：feature/matrix within-race AUC
- `au_shape_interaction_audit.py`：Racenet shape × pace interaction
- `au_architecture_audit.py`：simple distance/threshold architecture variants
- `au_matrix_weight_search.py`：time-ordered one-pair matrix weight search
- `au_pairwise_ranker_audit.py`：expanding walk-forward competitive-tier
  linear ranker gate

快速測試：

```bash
python3 -m unittest discover \
  -s .agents/skills/au_racing/au_wong_choi_auto/tests \
  -p 'test_*.py'
```

今次結果：

- AU auto engine：106 tests passed；
- shared racing metrics：18 tests passed；
- pipeline/content guards：16 checks passed；
- 所有本輪改動 scripts 已通過 `py_compile`；
- AU full orchestrator 同 auto orchestrator `--help` 入口 smoke test 通過。

## Objective completion matrix

| Objective | Authoritative evidence | Verdict |
|---|---|---|
| 全 archive、0/1-hit、misrank、compression | 710 場 raw runtime failure audit；逐場 underrated/overrated records | 完成 |
| Micro individual/group/all-off ablation | 70 個 individual parameters、7 families、all-micro variant、5 folds + terminal | 完成 |
| Neutral/weak/double-count signal cleanup | score/rank-change diagnostics、feature AUC、class/jockey/RT/fallback removals | 完成 |
| Meaningful separation | SD、Top1–Top3、Top3–Top5、compressed cohorts；證實 0-hit 唔主要由 compression 引起 | 完成 |
| Granular metrics beyond G/G/P | capture@4/5、winner@3/5、competitive recall/precision、NDCG、MRR、miss severity、false contenders | 完成 |
| Extreme outsider analysis | SP≥31/51 outcome-only cohorts、capture/mean rank；冇用 SP 入 model | 完成 |
| Racenet used/unused field review | field coverage/classification、within-race AUC、missing/fallback counts | 完成 |
| New data / interactions | distance、shape×pace、jockey tier、pairwise ranker gates；全部按 repeatability 決定 promote/shadow | 完成 |
| Structured failure records | 0/1-hit race records含 underrated、overrated、drivers、missing evidence、cohorts | 完成 |
| Hindsight/overfit protection | scoring-before-label join、date folds、terminal holdout、selection/confirmation separation | 完成 |
| Model version comparison | archived production、no-micro、pre-clean、signal-clean、architecture candidates，同一 archive metrics | 完成 |
| Explainable production simplification | active engine 移除 dead/fragile micro rules；舊一次性 research scripts 退出 active path | 完成 |
| Correct Good + Top3-in-Top4 gate | 所有主要 AU optimization scripts、報表欄位及 regression tests | 完成 |
| Repeatable further improvement gate | pair-transfer、interaction、distance、linear pairwise、共識、大場、弱支持、冷門 union 均未同時通過 folds + terminal | 暫無可升級候選 |
| Git delivery | prior AU cleanup/pairwise commits已推送；本輪 corrected-gate改動已完成驗證，隨本 audit commit 一併交付 | 完成 |
