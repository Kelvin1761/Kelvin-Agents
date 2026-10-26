# EXP-20261027-03 — HKJC 沙田全天候適性：由存檔賽績重建 PIT 證據再測

- **日期**：2026-10-27
- **平台**：HKJC
- **狀態**：**A／B UNRESOLVABLE（REJECT for live）；新假設 H2「AWT 經驗」登記 forward test，未上線**
- **起因**：2026-10-28 沙田全日 9 場全天候跑道。排名用嘅「同程」唔分草地／泥地，
  AWT 證據（`distance_suitability_v2` ST_AWT、`surface_performance_shadow`）全部
  權重 0。111 匹有 40 匹最近七仗冇跑過泥地。
- **搜索過嘅舊記錄**：
  - EXP-20260928-05：AWT archive < 30 場 → `UNRESOLVABLE / SHADOW`；要 ≥30 場先按同一規則重測。
  - EXP-20261007-05：預先登記咗沙田 AWT profile「exact blend，8%，cap 4」，但存檔 Facts
    冇可識別嘅 AWT target evidence（8 場全部 0），所以 weight 固定 0。
  - EXP-20261014-02／03：AWT 來源識別同 parser 修正。
- **今次新嘢**：唔再靠存檔 Facts（佢哋喺修正前生成，AWT 證據全部係 0）。改為用
  production 嘅 `parse_hkjc_formguide(賽績.md, as_of_date=賽日)` 重新讀存檔賽績，再餵入
  production 嘅 `compute_distance_suitability_v2`／同一套收縮規則。

## 量度前已知嘅覆蓋（2026-10-27 掃描）

存檔有賽果＋Logic 嘅沙田 AWT 賽事（排位表「場地: 全天候跑道」）：04-19 ×5、05-06 ×9、
06-07／06-13／06-27／07-04 各 ×2、09-27 ×3、10-04 ×4、10-11 ×3 = **32 場**。
現存 Logic 入面有 AWT 證據嘅只有 10-11 嗰 3 場（32 匹入面 23 匹 v2 target > 0）。

## Arms（只改 AWT 賽事；草地賽事 bit-identical）

候選 raw = `(1 − w) × baseline_raw + w × (60 + clip(score − 60, ±cap))`，即係引擎
`_build_distance_suitability_v2_shadow` 嘅同一條式。`w = 0.08`、`cap = 4` 係 EXP-20261007-05
預先登記嘅 AWT profile，**唔係由今次數據 fit**，所以用 `fixed_rule`。

- **A — 路程殘差（v2 原設計）**：production `compute_distance_suitability_v2`，target = 沙田AWT。
- **B — 場地殘差**：同馬、賽前、今場路程 ±200m；AWT 後驗減「香港全部場地」後驗
  （兩邊都係 365 日半衰、4 場中性收縮、名次百分位），score = 60 + 40 × 殘差；冇 AWT 證據 = 60。
  減全場地後驗係為咗唔將一般能力當成泥地適性再計多次（同 v2 一樣嘅理由）。

兩個 arm 同一家族，用 Holm 調整。

## 判決（預先寫死）

1. **忠實度**：10-11 三場用重建證據計出嚟嘅 v2 score，同 Logic 入面 production 值比，
   ≥ 90% 馬匹相差 ≤ 0.01；唔達標 = harness 無效，乜都唔判。
2. **leakage**：賽績行日期一律 < 賽日（`as_of_date`）；同日／未來行數要報 = 0。
3. **功效前置（§6）**：AWT 賽事入面頭四有變嘅場數 < 10 → `UNRESOLVABLE`。
4. **EXP-20260928-05 規則**：有 AWT 證據可以計分嘅賽事 < 30 → `UNRESOLVABLE / SHADOW`。
5. 其餘跟 Stage 4 v3 `fixed_rule`（全紀錄）；另報「沙田泥地」分層。
6. 只有 v3 判 WIN（Holm 後）先可以上線；否則 10-28 照用現行模型。

## 結果

### 可重現

```bash
S=<scratch>
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run \
  --since 2026-04-19 --until 2026-10-25 --dump-matrix --out $S/base.jsonl
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_awt_aptitude_pit_rebuild.py $S/base.jsonl --out-dir $S
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare $S/base.jsonl $S/cand_B.jsonl \
  --stage4 fixed_rule --leakage-audit-passed
```

Baseline 喺 `21703a4a` 之後嘅 main（`c60bcb38`）。語料 382 場，7 場評分出錯兩邊一齊剔走，配對 375 場。

### 檢查

| 檢查 | 結果 |
|---|---|
| 忠實度（10-11 三場重建 v2 score vs production Logic） | **32/32** 匹相差 ≤ 0.01 ✅ |
| leakage（重建歷史入面日期 ≥ 賽日嘅行） | **0** ✅ |
| AWT 賽事 | 32 場，全部有至少一匹有證據 |
| 有證據馬匹 | A：124/391 匹分數 ≠ 60（場內 SD 1.01）；B：220/391（SD 1.84） |

### 判決

| Arm | AWT 頭四有變 | v3 fixed_rule | 32 場 AWT：Gold／Good位／頭馬／頭五捕捉 |
|---|---:|---|---|
| A 路程殘差 | **1** | REJECT `ranking_evidence_too_weak` | 2→2／8→8／5→5／18→18 |
| B 場地殘差 | **7** | REJECT `ranking_evidence_too_weak` | 2→3／8→8／5→4／18→18.67 |

兩個都低過預先登記嘅「頭四有變 ≥ 10 場」→ **UNRESOLVABLE**。唔上線。

### 訊號本身有冇料（診斷，唔係判決）

場內 AUC（實際頭三 vs 其餘，只計有證據嘅馬），按場 bootstrap：

| 訊號 | AUC | 95% CI | 對數 |
|---|---:|---|---:|
| 現行模型 raw（同一批 32 場） | 0.6712 | [0.5972, 0.7470] | 873 |
| A 路程殘差 | 0.5177 | [0.4459, 0.5878] | 451 |
| B 場地殘差 | 0.4697 | [0.3848, 0.5553] | 446 |

**所以唔係「w=0.08 太細聽唔到」，而係「泥地適性分」本身冇預測力**。加大權重唔會救到佢，
仲會令排名追噪音。現行模型喺 AWT 賽事已經有 0.67 AUC。

### 事後發現：H2「冇泥地經驗」（⚠️ 喺同一批數據搵到，唔算證據）

將馬按模型排名分組（1–3／4–6／7+），比較近 730 日、今場路程 ±200m 內有冇跑過沙田 AWT：

| 模型排名 | 冇 AWT 經驗 | 有 AWT 經驗 |
|---|---:|---:|
| 1–3 | 10/27 = 37.0% | 32/68 = 47.1% |
| 4–6 | 4/33 = 12.1% | 17/62 = 27.4% |
| 7+ | 6/70 = 8.6% | 27/127 = 21.3% |

分層加權差 **+12.7pp**，按賽日 bootstrap 95% CI **[+5.6, +21.1]**（9 日、32 場）。

點解唔即刻上線：

1. 係睇完 A／B 之後第三次望同一批數據先搵到 —— in-sample，CI 唔可以當證據。
2. cohort gap ≠ 可上線收益（`au-cohort-gap-is-not-a-gain`）；要變成排名改動仲要揀幅度，
   幅度由同一批數據揀 = fit，合約要 walk-forward。
3. 只有 9 個賽日；混雜因素（出賽次數少、新到港、班次轉換）未拆。

### H2 forward 登記（由 2026-10-28 起，未望過嘅 AWT 賽事）

- 定義凍結：`surface_performance_shadow` 沙田AWT「原始」= 0（近 730 日、±200m、有馬匹數嘅香港 AWT 仗）。
- 量度凍結：上面同一個「按模型排名三組分層加權差」，按賽日 bootstrap。
- 10-28 一日 9 場只係開始；≥ 30 場 forward AWT 賽事先判，正數而且 CI 下界 > 0 先可以開
  排名候選（幅度要 walk-forward）。
- 10-28 模型頭四入面冇 AWT 經驗嘅：R1 #7／#2／#4、R2 #11／#3／#5、R4 #3、R5 #5、R7 #12、
  R9 #5／#3／#10（只供報告顯示）。
