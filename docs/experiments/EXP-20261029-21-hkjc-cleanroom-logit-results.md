# EXP-20261029-21 — HKJC clean-room 簡單模型 vs 現行模型（結果）

- **日期**：2026-10-29；平台：HKJC；mode：`walk_forward_oos`
- **協議**：[EXP-20261029-21-hkjc-cleanroom-logit-protocol.md](EXP-20261029-21-hkjc-cleanroom-logit-protocol.md)（睇結果之前鎖定，冇改過）
- **假設**：只用賽果庫、零人手規則嘅 conditional logit 唔差過現行 9D 引擎。
- **搜索過嘅舊記錄**：EXP-20261010-02、EXP-20260928-01、EXP-20261014-10、EXP-20261019-02
- **改到嘅檔案**：只係新增研究 harness `docs/experiments/patches/hkjc_cleanroom_logit.py`；冇改到引擎

## 配置
- **baseline**：`hkjc_eval_harness.py run`（production `score_race` + PIT priors），HEAD `fadb6ed1`
- **candidate**：14 個賽果庫 as-of 特徵 → 同場 softmax conditional logit（L2 1.0），每個賽日只用之前嘅賽日 fit

## 數據
- **語料**：harness 411 行，7 行 error，剔走 `speed_score` 死咗嘅賽日之後得 **345 場、35 個賽日**（2026-04-12 → 2026-10-28）
- **sample hash**：`bcd7940fdb8777d3…`
- **candidate 訓練**：每次 fit 用 1,217 → 1,628 場（2024-12-01 起，嚴格早過評估日）
- **候選集**：每場用 baseline `picks` 嗰批馬。有 20 場包含退出馬（賽果庫冇佢），排喺最尾

## 結果（v3 全紀錄，賽日 bootstrap 2000 次）

| 指標 | 現行 | clean-room | 差 | 95% CI | p | 6 個時間塊 |
|---|---:|---:|---:|---|---:|---|
| **Gold** | 13.91% | 11.30% | −2.61pp | [−7.49, +2.02] | 0.304 | −1.7, −8.3, 0.0, −7.5, +4.9, −4.2 |
| **Good 位** | 24.06% | 18.55% | **−5.51pp** | **[−10.63, −0.58]** | **0.028** | −8.3, −15.0, −4.8, +11.3, −3.3, −12.5 |
| 首選勝出 | 24.64% | 23.19% | −1.45pp | — | — | — |
| top3 capture@5 | 62.32% | 62.27% | −0.05pp | [−2.56, +2.45] | 0.985 | |
| NDCG@5 | | | −0.0098 | [−0.0316, +0.0131] | 0.407 | |
| competitive recall@5 | | | −0.17pp | [−1.91, +1.62] | 0.840 | |
| 頭三平均模型名次（越細越好） | | | −0.033 | [−0.177, +0.107] | 0.632 | |

**判決器**：`REJECT / primary_regression`（Good 嘅 CI 全負，6 個時間塊只有 1 塊 ≥ 0）

### 分層（Δ pp，clean-room − 現行）
| Cohort | 場數 | Gold | Good | 首選 |
|---|---:|---:|---:|---:|
| 沙田草地 | 213 | −4.23 | −5.63 | −2.82 |
| 跑馬地 | 113 | −2.65 | −5.31 | +0.88 |
| 沙田泥地 | 19 | +15.79 | −5.26 | 0.00 |
| 今季 26/27 | 144 | −1.39 | −4.17 | −2.08 |

冇一個主要 cohort 嘅 Good 係正數。

### 診斷
- 兩個排名好相似：場內 Spearman 中位數 0.811。
- **頭五名入面有邊幾匹，兩個模型一樣好**（capture@5 62.32% vs 62.27%）。差距全部喺**頭三／頭四嘅次序**。
  即係話，賽果庫有嘅資訊已經足夠揀出頭五；現行引擎多出嚟嘅資訊用嚟分出邊匹應該排最前，呢部分係有用嘅。
  多出嚟嘅資訊包括段速、晨操、賽績線、官方評分同配備，加上一啲人手規則。
- 敏感度測試：從兩邊都剔走退出馬之後，現行 Good 24.35%、clean-room 18.55%，結論不變。
  退出馬冇幫 clean-room 執到平宜。
- 係數每日都穩定，冇一個翻轉符號。最大嘅係：上仗名次百分位 −0.20、近三仗名次 −0.17、
  近三仗輸距 −0.14、騎師上名率 +0.14、檔位 −0.11～−0.14。

## 檢查
- **leakage-audit**：PASS。今仗只用排位資料：檔位、負磅、騎師、練馬師、路程、班次、場地。
  歷史、騎練率同出賽數一律喺**整個賽日完結之後**先更新，同日嘅場次互相睇唔到。
  fit 嚴格只用 `day < D` 嘅數據。賠率完全冇讀。
  退出馬唔當出賽，修正咗 `hkjc_expanded_corpus.py` 會將約 275 個退出記錄當成冇名次出賽嘅問題。
- **反方向殘留風險**：如果 baseline 嘅存檔 Logic 仲有未發現嘅前視，偏差只會幫現行模型。
  不過 EXP-20261015-02 修完之後，回放 4,477 匹得 7 匹有郁，影響細過今次 5.5pp 嘅差距。
- **golden_scoring／data_contract**：唔適用，引擎冇改。
- **退步**：成個候選就係退步，見上表。

## 結論

**唔應該用「簡單模型取代成個引擎」嘅方式去砍掉重練。** 一個乾淨、冇人手規則嘅 logit，
喺「頭五有邊幾匹」呢方面同現行引擎打和，但頭三排序明顯差：Good −5.5pp，CI 全負。
即係話，現行嘅複雜度**有一部分係真係有貢獻**，而貢獻集中喺頂部排序。
如果重寫，一定要將賽果庫冇嘅資料來源同規則一齊重建，唔可以由呢個簡單模型做起點。

**呢次測唔到嘅嘢**：「同樣嘅資訊，換一個更乾淨嘅結構會唔會更好？」
要答呢條，就要將現行 leaf 輸入 clean-room logit。
不過 EXP-20261019-02（外層權重 walk-forward refit 打和）同 EXP-20261019-03（內部份額）
已經做過最接近嘅版本，結果都係打和。

**決定**：REJECT（只限「簡單模型取代現行引擎」；現行引擎冇改）
**commit**：記錄同 harness 推咗去分支 `claude-hkjc-cleanroom-20261029`，未入 main

## 重跑
```bash
S=<scratch 目錄>
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run --out $S/base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_cleanroom_logit.py \
  --baseline $S/base.jsonl --out $S/cand.jsonl --weights-out $S/weights.jsonl
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare \
  $S/base.jsonl $S/cand.jsonl --stage4 walk_forward_oos --leakage-audit-passed
```
