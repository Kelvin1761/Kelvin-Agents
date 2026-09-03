# EXP-20260902-07 — AU 矩陣結構、班次及跨跑道證據

## 預先登記

Parent `fbf1499878b08aac5829cdae4dbfe5f9b7f2ccb4` 加 EXP-06 已驗證小馬群頭馬修正。
Baseline `/tmp/au-matrix-feedback-after.json`，1822 場；沿用 EXP-06 日期切法及所有場次。
本輪不能稱為全新未見 holdout：同一 terminal 已在 EXP-06 開封。不得據 terminal 調參。
賠率只作評估分層，不進入候選。現行評估合約不改。

獨立候選，先 dev；Gold/Good 任一倒退即停，不因個案好睇保留：

- N：移除矩陣 gain 及最終 ability scale；把兩者代數併入單一合成係數
  `舊權重 × 舊gain / 舊scale`。矩陣顯示原始分項分。不是 refit；舊 gain 封頂不保留。
- P：只移除 `form >=72 and class <60` 的近績 −4。
- S：只對表現質素正面偏差按最近四仗「已知同跑道種類的近期權重 / 已知跑道近期權重」
  折算；草地與合成跑道分開，未知不臆測；負面分不變。測 PQ，與 EXP-06 的近績減半不同。
- L：每仗以獎金相對全場歷史獎金中位數校正：
  `班次係數 = 1 + 10 × (log10(該仗獎金) − 場內中位) / 名次底分`。
  移除額外聚合獎金項及讀不存在 class 欄位的舊階梯；缺資料係數 1。
  呢個仍是獎金 proxy，不聲稱已用真 BM 或官方評分/負磅解決班次。
- F：純對手賽績線佔 3%，其餘 97%；若最近四仗無任何一仗第六或更前兼落後不超過
  五馬位，強線封頂 60。沿用 HKJC 的「自身有競爭力」概念，AU 模型保持獨立。
  舊對手摘要缺每次後續賽日期，故只可 shadow，不能因績效升就 promotion。
- T：同騎師試閘上名證據不再因已有正式配搭而被 `elif` 排除；沿用既有 2.57 cap、3.8 mult。

多候選不得只測合併版。N 是結構候選亦需測封頂差異；P/L/S/T 是模型候選。
一般試閘密度重新分類另作語義分離，須保持原有影響且沒有雙計；不以刪除訊號代替分類。

## 結果（percentage points）

| 獨立項 | dev Gold | dev Good | 決定 |
|---|---:|---:|---|
| N 拆倍率 | 0 | 0 | 使用者要求的結構簡化；不是效能提升候選 |
| P 刪 −4 | 0 | −0.07645 | 不採用；不能證明舊扣分有用，亦不能證明刪除更好 |
| S PQ 跨跑道比例 | +0.07645 | −0.07645 | 不採用評分公式；補保留來源及風險提示 |
| L 逐仗獎金係數 | −0.38226 | −0.84098 | 不採用；未解決班次問題 |
| F 賽績線 proximity | −0.07645 | −0.30581 | 不採用；亦有舊摘要日期不足的限制 |
| T 正式配搭也加試閘 | −0.15291 | +0.15291 | 不擴大加分；保留原有同騎師試閘訊號 |

P/S/L/F/T 都在 dev 停止，沒有開 terminal 來挑參數。
N 的 terminal Gold、Good、Pass、Champion、winner@3、top3 precision 全部零差；
field-size 四桶的 Gold/Good 亦全零差。dev winner@5 少一場（−0.07645pp）。
原 gain 封頂不再存在，19 匹能力分變化超過 0.01，最大 +2.3124。
因此不聲稱逐匹數值完全相同，也不聲稱這次 refactor 提升預測表現。
Stage 4 的效能判決是 `REJECT / ranking_evidence_too_weak`：沒有改善訊號。
N 保留的理由是用戶明確要求移除尾段倍率、合併成一套可 refit 係數；
這是獨立的結構交付，不能冒充 `PRIMARY_WIN` 或 `RANKING_WIN`。
真正有排名改善證據的仍是 EXP-06 的頭馬馬群修正；不能將其功勞歸給 N。

## 實作與 ablation

- 新 `compose_matrix_score` 成為 engine、validator、evaluation、golden 的共同方程；
  numpy refit 與共同方程比較。legacy gain map 為空，scale 只保留相容常數 1，
  不再參與 live 合成；refit 收到非 1 gain 會拒絕。
- 試閘密度兩項由 fit 拆成 preparation_score／試閘備戰矩陣。
  係數 `.6626585553070451 × .380952 = .25244110196132946`，不是新加權。
  原 class context 條件先算，再拆出來源，避免默默改門檻。
  用完整 engine 再驗證合併版，主要命中指標仍零差；測試證明無重複計算。
- 序列化與輸入矩陣都用六位小數。之前只輸出兩位，refit 有 235 匹差 >.01；
  修正後 18,216 匹 max delta .0039，沒有一匹 >.01；numpy 浮點邊界差低於一個矩陣刻度。
- PQ 原始證據保留 venue、going、RaceClass，不能將 Synthetic 丟掉之後聲稱是草地能力。
  近績明細及核心分析顯示跨跑道提示；不把提示冒充已校準的扣分。
- 新 Facts 保存 `AU_FORMLINE_EVIDENCE` JSON 註解，包含 as_of、本馬名次／輸距、
  對手身分、每次後續賽日期／名次／場地／partial；helper 自身亦截走同日／未來資料。
  這為下一輪去重、接近程度及班次驗證提供來源，不會自動提高賽績線排名權重。
- 班次／負磅尚未有通過的替代公式；現行獎金 proxy、官方 rating 及 −4 都保留。
  不會把 `OPEN BM79` 看成無條件比 metropolitan BM72 強，亦不把 sponsor title 當成真班次。

## Sunburnt Country

2026-09-02 Warwick Farm R3，修正後仍排第 2、66.1 分。近四仗三仗 Synthetic，
真實歷史班次 OPEN BM79 / BM70 / BM64 / BM65；不能聲稱高估已修好。
新摘要明確標示轉草地證據不足。市場價格沒有用來強迫壓低此馬。

## 重現與限制

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_followthrough_20260902.py build
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_followthrough_20260902.py dev
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_followthrough_20260902.py terminal
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /tmp/au-exp07-engine-final.json
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_matrix_followthrough_20260902.py final
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py verify --data /tmp/au-exp07-engine-final.json
```

EXP-06 的 enriched cache、baseline 及本輪 baseline 在 `/tmp/au-matrix-*`；原模型可由
parent commit 還原。新候選計算不讀目標賽果／賠率，history boundary 由 EXP-06 審核；
但 2026-08-05 以前 archive 本身有事後重建限制，不可稱整份語料是原始賽前快照。
共 1822 場／18216 匹，dev 1310、terminal 512，樣本 hash 見附帶 evidence JSON。
模型說明經生成器更新，golden 保留原有同一批120個 feature vectors；舊基準仍在 parent commit。

## 乾淨 main 發佈（2026-09-03）

EXP-06 已於 `6b97eea1808c` 發佈、merge 並 activate（Central 記錄
2026-09-03 13:45:54）。本輪只將 EXP-07 差異移植到該 main，開新隔離工作樹
`codex-au-exp07-release-20260903`，parent `6b97eea1808cbdfff9be16403a957ef952006c74`。

移植範圍只包含本實驗實際採用嘅嘢：

- N 拆倍率：`MATRIX_DISPLAY_GAINS` 清空、`MATRIX_ABILITY_SCALE` 只留相容常數 1、
  新 `compose_matrix_score` 成為 engine／validator／evaluation／golden 共同方程。
- 試閘密度重新分類：`preparation_score` 由 `jockey_horse_fit` 拆出成獨立
  「試閘備戰」維度，係數 `.6626585553070451 × .380952 = .25244110196132946`
  係代數拆分，唔係新加權；測試證明冇雙計。
- `au_matrix_refit` 改為直接 fit 原始分項係數，收到非 1 gain 會拒絕；
  序列化改六位小數。
- 有日期嘅 `AU_FORMLINE_EVIDENCE` 來源保存、PQ 原始 venue／going／RaceClass 保留。

**冇移植**嘅係本實驗五個 dev 回歸候選（P 刪 −4、S 跨跑道 PQ、L 逐仗獎金班次、
F 賽績線 proximity、T 擴大試閘配搭）。已逐項核對移植後嘅工作樹：`−4` 規則仍在、
`form_line` 仍然零權重、同騎師試閘仍然喺 `elif` 之下、舊班次階梯未改。

此發佈**唔帶排名改善主張**。EXP-07 terminal 主要指標全部零差，Stage 4 判
`REJECT / ranking_evidence_too_weak`；保留理由係用戶明確要求「唔好喺尾段放大分數」
同「令將來 ML refit 做得到」，屬結構交付。

發佈前驗證（本工作樹）：`./檢查.sh --quick` 全綠（ruff、AU／HKJC 評分 golden、
AU／HKJC 模型說明新鮮度、AU／HKJC 數據合約）；`./檢查.sh` 完整 10 個 suite 全綠，
AU 600 passed。EXP-06 提到嘅 Dashboard Node 衝突已隨 dashboard HTML 入 main 而消失。
