# EXP-20260902-06 — AU 評分矩陣用戶反饋與 Sunburnt Country

- 日期：2026-09-02；平台：AU。
- 基準：`fbf1499878b08aac5829cdae4dbfe5f9b7f2ccb4`，現行引擎重算。
- 原始 dump：`/tmp/au-matrix-feedback-baseline.json`。
- 前置 quick gate 通過；已有 AU data-contract stale-baseline 警告。
- 搜索過：EXP-20260825-02/03/04、EXP-20260826-04、EXP-20260831-06、EXP-20260901-05/06。
- 現役模型不作候選覆蓋；研究程式只在自身 process 內建立替代 method。

## 預先登記（讀取候選績效之前）

沿用 au_eval whole-date 尾 15% 日期 terminal、dev 五個時間 fold、canonical Gold / Good位及既定五個 ranking metrics。不調參、不搜索組合。先 dev；任何 primary dev 回歸即停止該候選，不開其 terminal。通過 dev 的固定候選才作一次 terminal 確認。排序勝出前須先量中和部件預算與 paired CI 半寬；非資訊性不得作 ranking win 證據。

1. **A — 逐仗獎金班次係數**：以現有獎金來源與 K=10，逐仗 `mult = clip(1 + K*(log10(prize)-field_median)/60, .7, 1.2)`，替換舊恆定班次係數，移除平均分後的同類加減。未知獎金不猜。這是編碼假設，並非宣稱獎金等於真班次；不把 country OPEN 當 metro 高班。
2. **B — 配搭分移除一般試閘獎勵**：trial_ok_bonus / trial_ok_top_jt_bonus 設零；同一騎師實際策此駒試閘及正式賽的配搭證據保留；其他 trial leaf 不變。
3. **C — 冠軍馬群可靠度**：只改有實際出馬數的勝仗，base `60 + 40*(N-1)/(N+1)`；Beta(1,1) 對手勝負收縮的保守編碼，非校準概率。3 匹=80、14 匹≈94.7；其餘名次及缺出馬數不變。
4. **D — 淨對手賽績線**：移除 22% form、移除 class_move 後置加減，直接取 `_formline_score`；固定 3% 主矩陣份額，其餘矩陣同比例縮至 97%，overlay 原樣保留。這仍是現有粗略對手資料，不是完整對手能力模型。
5. **E — 合成跑道正面近績轉草地折半**：僅今日明確非合成場地時，合成往績的 base>60 部分乘 .5；其他 leaf 不變。單獨檢驗轉場質素可轉移性，不能聲稱已修好表現質素分或草地適性。

候選新增輸入只讀存檔賽前 Facts；歷史日期必須早於賽日。賠率只作診斷/cohort，當場賽果只作評估 label。不重新抓取或把今日 formline index 回填入舊場次。舊 archive 賽後重抓限制要保留；不能宣稱全語料 point-in-time 乾淨。

分層：field ≤8 / 9–10 / 11–12 / 13+；meeting venue；今日 going；baseline 首選 SP ≤3 / 3–5 / 5–10 / 10–20 / >20。新候選只以同場同馬 hash 配對。

## 結果與實施

**C 保留於本機工作目錄；其餘四個排名候選不採用。未 commit、push 或發佈。**
另外保留報告／資料正確性修正；不宣稱這些清理帶來已量到的排名收益。

### 語料、基準及可重現性

- 1,822 場／18,216 匹；dev 1,310 場（2025-08-02 至 2026-08-17），terminal 512 場（2026-08-18 至 2026-09-01）。
- `_counts` 依現有規則排除兩場前三不完整記錄，dev primary 分母為 1,308；沒有為候選另改排除條件。
- baseline Gold：dev 17.1254%、terminal 23.8281%；Good位：dev 22.0183%、terminal 25.5859%。
- Gold＝實際前三全部包含於模型 Top 4；Good位＝模型首兩揀皆上名。
- baseline replica 18,216 匹 max|Δ| 0.009938，沒有 >0.01；接受既有 evaluator 精度。
- 同馬同場配對；sample hash：`16bc9a24be537b2e598862a181bc41fb870658e8d9257d8005e3e642f331c9f7`；baseline dump SHA256：`130a3a7cd7e6224b58a8d0decf4024443a815c95ed3d6e2ea3adb1eb328d73e1`。
- 新 form 修正涉及的往績共 62,711 行（包括個案重播），未發現缺日期／當日／未來日期。
- 舊 archive 賽後重抓／field-size 覆蓋不均限制仍存在。新變換沒有加入市場價或賽後 label；這不等於全 archive 是乾淨 point-in-time。

### 預先登記候選的開發期消融

| 候選 | Gold Δ | Good位 Δ | 決定 |
|---|---:|---:|---|
| A 獎金調整移入逐仗係數 | -0.076pp | -0.153pp | 開發期 primary 回歸，停止 |
| B 配搭分移除一般試閘加分 | -0.688pp | -0.306pp | 開發期 primary 回歸，停止 |
| C 冠軍按馬群收縮 | +0.076pp | +0.000pp | 進入 terminal；RANKING_WIN |
| D 純對手賽績線佔 3% | +0.229pp | -0.229pp | 開發期 primary 回歸，停止 |
| E 合成往績正面部分轉草地折半 | -0.076pp | +0.229pp | 開發期 primary 回歸，停止 |

這只否定上述**確切編碼**，不代表「逐仗真班次」「試閘應分類」「草地轉換」概念已被否定。A 只試獎金 proxy，沒有完成真實對手強度模型。
D 另外存在舊對手摘要缺少逐次 follow-up 時間證據的限制；不能把舊摘要當完整 point-in-time 對手能力。

### C：一次 terminal 確認

| 指標 | baseline | candidate | 變化／95% paired CI |
|---|---:|---:|---|
| Gold | 23.8281% | 24.2188% | +0.3906pp；[-0.5859,+1.3672]pp |
| Good位 | 25.5859% | 25.9766% | +0.3906pp；[-0.7813,+1.7578]pp |
| Pass | 48.8281% | 49.6094% | +0.7813pp |
| Champion | 26.9531% | 26.5625% | -0.3906pp（2 場） |
| Top-5 pairwise AUC（pooled evaluator） | — | — | +0.004275；[+0.001375,+0.007334] |

Gold、Good 各多 2 場，但 CI 跨零，因此**不是 PRIMARY_WIN**。

真引擎（未經兩位 leaf 四捨五入）的 canonical 按場 paired evidence：

| 排序指標 | dev Δ | terminal Δ | terminal 95% CI |
|---|---:|---:|---|
| 實際前三平均模型名次（越低越好） | -0.008906 | -0.020020 | [-0.035156,-0.005046] |
| competitive_recall_at5 | +0.001476 | +0.004395 | [+0.000879,+0.008301] |
| ndcg_at5 | +0.000729 | +0.001959 | [-0.002103,+0.005772] |
| top5_pairwise_auc（按場平均） | +0.001145 | +0.004833 | [+0.001800,+0.008131] |

pooled AUC 與按場平均 AUC 的權重口徑不同，不能互换。以上數字按各自既有 evaluator 原樣報告。

功效前置：terminal 開啟之前已中和 form leaf，記錄五個部件預算。與候選實際 CI 半寬比較後，`top3_capture_at5` 不具資訊性，剔走此項；其餘四項有資訊性，再交原 `evaluate_candidate` 仍為 **RANKING_WIN**，沒有換尺。

- dev 五個 whole-date fold：前四個 primary 無變化，第五個 Gold +0.1776pp、Good 打和。大量早期往績缺 field size，所以不能把這稱為五個獨立窗口都驗出改善。
- terminal field ≤8：Gold／Good 各 +1.2270pp；9–10 各 +0.5525pp；11–12 各 -0.7519pp（1 場）；13+ 打和。
- field／venue／going／baseline 首選 SP 合共 113 個分組，主要指標沒有 terminal CI 全負；部分組別樣本稀少，無法證明每個場地都有收益。
- 真引擎重跑全部 1,822 場：3,132 匹 form leaf 改變。相對研究候選 max ability 差 0.009915、沒有 >0.01；兩場近乎平手因四捨五入換位，真引擎重新判決仍是 RANKING_WIN。

### Sunburnt Country：真正缺口仍在

2026-09-02 Warwick Farm R3 #6：原模型第 2、66.7361 分；C 本機重播仍第 2、約 66.1 分。

| 近四仗 | 地面／級別 | 獎金 | 成績 |
|---|---|---:|---|
| 08-21 Canberra Acton | Synthetic；Sportsbet `OPEN BM79` | $35,000 | 1/9 |
| 08-07 Canberra Acton | Synthetic；BM70 | $22,000 | 3/9，負 1.29L |
| 07-25 Kembla Grange | Good；BM64 | $42,000 | 6/8，負 3.00L |
| 07-08 Canberra Acton | Synthetic；BM65 | $22,000 | 2/7，負 1.03L |

本機賽前 Formguide：Synthetic 5:3-1-1；Turf 11:0-2-0；未跑過今次 2200m。三場勝仗全部在 Acton 合成跑道，曾勝 1750–1900m。
[Racing NSW 上仗官方賽果](https://mdata.racingnsw.com.au/FreeFields/Results.aspx?Key=2026Aug21%2CNSW%2CCanberra+Acton) 把該 meeting 分為 Country，地面 Synthetic；[今仗官方場次](https://mdata.racingnsw.com.au/FreeFields/Acceptances.aspx?Key=2026Sep02%2CNSW%2CWarwick+Farm) 是 Metro、草地 Good 4、BM72、2200m、$60,000。

問題不應簡化成「所有 Canberra 賽事都差」或「市場知道這馬差」：長價只代表市場較不看好，並非真實能力標籤。更具體的風險是**合成跑道成績轉草地、1900→2200m、Country→Metro、以及對手質素不足以由 OPEN/BM 字樣代表**。

模型原來表現質素 82.98（全場最高）、近績 71.81；獎金班次只扣約 0.62，proven_class 反加約 0.705。form 內歷史 `class` 欄沒有接 raw 班次，本場四仗係數全部 1.00；當日 race_class 亦只保存贊助名稱，不是 BM72。`source_race_class` 目前另供 proven_class 使用。

PQ 主要按輸距＋獎金作場內比較，沒有驗證這些合成跑道好表現能否轉移至今次草地。E 的粗略折半雖把個案降至第 3，dev Gold 卻跌，不能用單馬迎合市場代替驗證。

### 已落實的清理

1. `form_line` 改為 100% formline leaf，取消原 22% form；參考維度倍率回 1。仍不加入正式排名。這只拆掉重複近績，未把原對手分重建成成熟的賽績線模型。
2. 修正 `sb_horse_index` 漏列 Warwick Farm Metro；讀取舊 cache 會重新分類，不改歷史日期。Facts 消費索引分類，取消第二份不同的 Metro 名單。
3. 對手上名率的分子及分母皆用完整記錄；partial sightings 不再混入分子、製造高於實際或甚至 >100% 的上名率。部分記錄仍可證明「見過勝出／上名」，不能證明完整率。
4. 「近績分亢奮但級數分偏弱」改成實際分數＋門檻：form≥72 且 class<60；原 -4 規則未改。這是評分衝突，不是馬匹生理／情緒狀態。
5. 矩陣原始分與幅度換算分清楚分開，不再稱「統一尺」；修正 `Rating 68 ×70%=65.9` 這種漏了中性錨點的錯算式。保留正式排名倍率，避免未驗證的全模型重配。
6. 逐仗近績列出實際出馬數，冠軍底分顯示一位小數。

### 暫不採用與下一步設計

- 一般試閘密度語義上屬備戰；同一騎師策此馬的試閘才屬配搭。B 直接刪一般試閘 bonus dev Gold 跌 0.6881pp，這次沒有照刪；需以分類重構保留適當有效訊號，再量邊際貢獻。
- 「官方評分對位」宜分清：官方 rating 是能力評級、今日淨負磅是讓磅補償、歷史班次是能力證據。缺 rating 才有 class／weight 代理；現時不是一個完整 class+weight advantage 模型。EXP-20260831-06 已測過負磅，結果未可解決，不能稱完全不計磅是合理定論。
- 真賽績線要以對手身份／賽事身份去重，按**本馬賽日前**的對手後續實際級別、輸距、出馬數與場地衡量；同場交手時本馬的輸距亦不能忽略。現有「曾與頭馬交手」不等於跑得接近頭馬。
- 只拆 22% 近績，不能消除上述原料與定義問題；本次沒有宣稱賽績線已恢復可入排名。

## 驗證、檔案及界線

- `./檢查.sh --quick` 最終全綠。
- 新 regression 檔＋既有 index tests：25 passed；完整 AU suite：580 passed；其餘 Python suites 全通過。
- `./檢查.sh` 完整執行：Dashboard Node 有一條**開工前既有改動**造成的失敗，`test_static_template.mjs:1426` 仍要求 `前置馬唔多`，但原有未提交 HTML 已刪該套話。該條測試對 HEAD HTML 在隔離目錄通過。沒有修改這份其他工作，也沒有 commit。
- golden：保留原相同 120 匹 fixture，只更新 115 個參考 form_line 預期，ability／grade 不變。注意 frozen-feature golden 不能測 form 公式；由新 winner 測試與全引擎重跑覆蓋。
- 舊 golden 及 matrix_mapper 保存於 `/tmp/au-matrix-feedback-rollback/`；baseline commit 亦可復原。
- data_contract 用 2026-08-05 起 1,134 場／11,356 匹重校，解除原 stale-baseline；AU 模型說明由官方生成器更新。
- 主入口在 `/tmp/au-matrix-feedback-preview/2026-09-02 Warwick Farm Race 1-7/` 重播 R3，Data Health 與 Race QA 通過；Cloudflare 明確 skip。
- 本次沒有修改現有賽前 snapshots、推送遠端、發送 Telegram 或部署。

## 重跑

原始 baseline dump 必須用上面 baseline commit、相同語料產生；不能在候選 worktree 把新 dump 命名為 baseline。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /tmp/au-matrix-feedback-baseline.json
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data /tmp/au-matrix-feedback-baseline.json
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_feedback_20260902.py --phase build
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_feedback_20260902.py --phase dev
# 固定 C 通過 dev，先量 power 中和預算，再開一次 terminal：
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_feedback_20260902.py --phase terminal
```

研究程式從 baseline commit 讀出舊 form method，即使 C 已在工作目錄，仍可重播；每匹原 baseline form／fit 都會核對，對不上即中止。

原始證據：`/tmp/au-matrix-feedback-eval.json`、`.enriched.json`、`/tmp/au-matrix-feedback-power.json`、`/tmp/au-matrix-feedback-cohorts.json`、`/tmp/au-matrix-feedback-after.json`、`/tmp/au-matrix-feedback-actual-engine.json`、`/tmp/au-matrix-feedback-final-decision.json`。全部原始大檔留 /tmp。



## 乾淨 main 發佈覆核（2026-09-02）

為免帶入原分支另外 11 個 commit，只將本次差異移植到 `origin/main`
`b2c08d6a51c9f31e00f9a40a9540001e68677c52`。main 同原研究 HEAD 的舊分數有193匹差異，
所以沒有混用 baseline：在 main 引擎還原 parent `_form_score` 跑
`/tmp/au-field-main-baseline.json`，再用候選跑 `/tmp/au-field-main-candidate.json`。
相同1822場／18216匹、相同日期切法。dev Gold +0.07645pp，Good 0；terminal
Gold +0.390625pp、Good +0.390625pp。四個有效 ranking metrics 同向，三項 terminal CI
支持，判決仍為 RANKING_WIN。證據見 `EXP-20260902-06-main-evidence.json`。

本次 release 只包含冠軍馬群修正、賽績線去重／partial及Metro修正、解說，以及
新增有日期的賽績線來源保存。EXP-07 拆倍率／備戰分類不在這個 release；
Central 要求評估轉接與模型分開發佈，完整候選保留在原工作區及 `/tmp/au-matrix-release`。


## 最終 main 同步驗證

保存時 main 已進到 `926eac54de7f67f78a8f6f7a5c3632a7d95b0cce`。已將 exact-scope 修正以三方合併套到新隔離工作樹。其 engine_core／matrix_mapper／scoring 三個父版本逐 byte 等於原實驗 `fbf14998`；候選三個檔亦逐 byte 等於已驗證 field-size 工作樹。故 EXP-06 原始同語料 A/B 適用（1822 場、18216 匹），無混用舊 main 的 absolute 分數。hash 見 main-evidence JSON。生成資料按新 fingerprint 重建。
