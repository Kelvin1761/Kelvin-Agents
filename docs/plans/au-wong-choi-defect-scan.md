# AU Wong Choi 缺陷掃描計劃

**用途**：餵俾一個長跑 agent（`/goal` 之類）做系統性掃描。
**建立**：2026-08-31，由當日一連串發現反推出嚟。
**原則**：每一節都有**明確嘅偵測方法**同**判定門檻**。唔准靠「睇落唔妥」。

---

## 開工前一定要讀

1. [`AGENTS.md`](../../AGENTS.md) —— 五件唔可以做嘅事、證據紀律
2. [`docs/model-evaluation-contract.md`](../model-evaluation-contract.md) ——
   把尺，**包括 2026-08-31 加嘅「功效前置條件」**
3. [`docs/experiments/INDEX.md`](../experiments/INDEX.md) —— 開始任何假設之前 grep

## 三條硬規矩（今日親身踩過）

- **報「呢個欄位冇人 parse」之前，一定要 grep 埋 regex 常數名。**
  `Sectionals 600m` 其實由 `RE_SECT` parse 咗，我 grep 欄位名搵唔到就報咗
  「從來冇 parse」—— 錯。
- **用任何 key 做分組之前，先量碰撞率。** 我用 Winning Time 分組，
  「證實」咗一個唔存在嘅逐駒分段（兩場 1000m 都跑 59.370）。
- **每 ship 一個改動，所有未 ship 嘅候選都要重新量正交性。**
  WinningTime vs pace_figure 嘅 ρ 由 0.005 變 0.418，一個已登記嘅重測
  就係咁失效。

---

## 掃描模式（按已知命中率排序）

### A. 「聲稱係實測值」嘅常數 —— 命中率最高

**已中**：`WET_FORM_PRIOR = 0.5  # global career wet place-rate (~0.496 measured)`
→ 實測匯總 **0.3758**，四種計法冇一個接近 0.496（`EXP-20260831-08`）。

**偵測**：
```bash
grep -rn "measured\|實測\|calibrated\|校準\|empirical" \
  .agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/*.py
```
對每一個命中：由語料重新量嗰個量，**同註釋嘅數字對比**。
⚠️ 一定要用**同一種聚合方式**（收縮式要匯總率，唔係逐馬平均／中位數 ——
三者今次分別係 0.3758 / 0.3887 / 0.4000）。

**待查清單**：
- `_JOCKEY_LY_PRIOR = 0.365`（`EXP-20260826-03` 撤回過一次錯誤指控 ——
  要對啱 population 先量：runner-level 唔係 season-level）
- `WET_OTHER_BUCKET_WEIGHT = 0.5`（配對 bucket 加重係 0.5，有冇量過？）
- `CLASS_MICRO_WEIGHTS` / `CONSISTENCY_MICRO_WEIGHTS` 每一項
- `MATRIX_ABILITY_SCALE`、`MATRIX_DISPLAY_GAINS`
- `_lookup_standard_l600` 嘅 `_STANDARD_600M` 表（場地／距離標準秒數，
  幾時建立？有冇隨賽道改動更新？）

**判定**：註釋數字同實測差 >10% → 當缺陷處理（正確性修正，唔使證明 AUC 升，
但要證明零退步）。

---

### B. Leaf 食緊一個 aggregate／proxy 去代表一個個體量

**已中**：`pace_figure_score` 食 race-level `L600 Delta`，個名同報告都話係
「本駒步速」（`EXP-20260831-03`）。

**偵測**：對每個 leaf，問「呢個值係逐駒獨有，定係一組馬共用？」
```
分組鍵：(場地, 日期, 場次, 距離)   ← 唔可以用時間、獎金呢類會撞名嘅欄位
量：同一組內出現 >1 個唔同值嘅比例
0% = race-level（同名唔符就係缺陷）
```
**先量碰撞率**：確認分組鍵喺呢份數據入面真係 unique。

**待查清單**：`class_score`（食獎金水平 —— 場級定駒級？）、
`track_score`、`pace_map_score`（memory 話係 4 級階梯、96.6% 同分）

---

### C. 「支援」嘅欄位其實 0% 有值

**已中**：`_parse_pf_token` 支援 12 個欄位，73,806 條 pf_runs 只有
`l600_delta` 有值，其餘十個 **0.0%**（Racenet 遺留）。

**偵測**：
```python
# 對每個 parser 嘅輸出 dict，逐 key count 非空 / 總數
# 覆蓋 <5% 而 code 仲為佢計 _avg/_best → 死 code
```
`test_pf_field_liveness.py` 已經為 PF token 釘住呢件事 —— **同一個模式要
複製去其他 parser**。

**待查清單**：`claw_sportsbet_form.parse_race` / `parse_runner_blocks` 全部
輸出欄位、`_parse_formguide_jt_ly`、`ra_fields.py`、racecard parser

---

### D. 嚴格 regex 靜靜掉走一整類數據 —— 今日中咗兩次

**已中**：
- `margin:\s*(-?[\d.]+)L` 硬要 `L`，漏走 Racenet 格式 `margin:10.4`
  → 326 場 A/B 全部 `+0.0000`（`EXP-20260831-05`）
- `sb_results.py --top` 預設 6，270 行只寫 174（35.6%）
- 歷史上同一模式已中 4 次（`Settled`、`L600 Delta`、試閘 header、finish 名次）

**偵測**（唯一可靠方法）：
```
對每個 regex：count(頁面/來源有呢樣嘢) vs count(我哋 parse 到)
兩個數唔等 → 逐個差異睇原文
```
**唔可以**只睇「parse 到嘅有幾多」—— 分母錯就永遠睇唔到。

**待查清單**：`claw_sportsbet_form.py` 每一條 `RE_*`（約 20 條）、
`inject_fact_anchors.py`、`sb_results.py`、`ra_fields.py`

---

### E. 中性預設 ≠ 群體平均表現

**已中**：6 個 leaf 嘅 `==60` cohort 超額上名率顯著負（`EXP-20260831-08` 附錄）：
賽績線 −0.070、路程 −0.064、騎師 −0.062、近況 −0.036、練馬師 −0.036、試閘 −0.034。
「冇證據」實際上係負訊號，但當中性。

**偵測**：
```
超額 = 實際上名(0/1) − 3/馬匹數
比較 leaf==60 嗰批 vs 0，bootstrap CI
```
**⚠️ 呢個係 cohort gap，唔係可上線嘅收益**（`au-cohort-gap-is-not-a-gain`）。
落手之前先問「模型係咪已經另有路捉到」——
今日九個未入排名 leaf 重測全部 CI 跨零（`EXP-20260831-09`）。

**待做**：`form` / `trial` / `jockey` / `trainer` 四個**有入排名**嘅，
試「no-evidence 嗰批降到量出嚟嗰點」（`au-neutral-point-is-per-leaf`）。
`trial` cohort 最大（30.3%），優先。

---

### F. 欄位寫落去但冇人讀

**已中**：`WinningTime` 寫咗落 form line，引擎零人讀（`EXP-20260831-07`
測過，被 pace_figure 個體化食走）。

**偵測**：
```bash
# form line / Facts 寫咗嘅每個 token，去 engine 度 grep
for tok in $(grep -o 'tail += f" [A-Za-z]*:' claw_sportsbet_form.py); do
  grep -rn "$tok" au_racing_engine/ || echo "冇人讀：$tok"
done
```

**待查**：`RaceClass:`（註釋自己寫住 "transport-only, scorer does not consume"）、
`starters:`、`@1200m` / `@Settled`、配備變更

---

### G. 閘門／測試睇唔到自己要守嘅嘢

**已中**：
- `golden_scoring.py` 個 `ability` 係純矩陣分，**兩個 overlay 都喺範圍外**
  —— 43.7% runner 嘅 wet 值郁咗而佢照報「120 匹全部一致」
- 同一個檔對 formguide parse 亦零覆蓋
- `race_compliance_scan.py` 掃咗凍結快照，令 QA 閘每次 rebuild 都假 CRITICAL

**偵測**：對每個閘門，明文寫出「covered surface」，然後**故意破壞範圍外
嘅嘢**，確認閘門真係唔叫（而唔係假設佢會叫）。

**待查**：`data_contract.py --gate`、`racing_data_health.py`、
`au_source_compare`、`健康.sh` 每一項

---

### H. Cache／時效令數據靜靜凍結

**已中（歷史）**：RA 州曆永久 cache → 七個州凍結 11 日
（`au-official-rating-is-time-windowed`）；`.pyc` 靠 (mtime, 大細)
（`macos-stale-bytecode-hazard`）；Drive 鏡像 TCC。

**偵測**：對每個 cache，量「最舊一筆嘅年齡」同「有 TTL 嗎」。
```bash
grep -rn "cache\|TTL\|ttl\|expires" .agents/skills/au_racing/*.py | grep -v test
```

**待查**：`AU_Profile_Stats_Cache.json`、`AU_Sportsbet_People_Cache.json`、
`.sportsbet_cache`（733MB，08-09 起，有冇 TTL？）、
`sb_archive_meeting_ids.json`

---

## 每個發現要交嘅嘢

1. **量度**：命令、語料範圍、樣本數、CI
2. **分類**：正確性缺陷（改咗要證零退步）／ 表現候選（要過 gate）
3. **功效前置**：閘門 MDE vs 部件預算 —— 唔夠就記 `UNRESOLVABLE` 唔係 `REJECT`
4. **記錄**：`docs/experiments/EXP-YYYYMMDD-NN-*.md`，失敗要寫**點失敗**
5. **失敗實驗嘅 model code 唔准 commit**（patch 存 `docs/experiments/patches/`）

## 唔要做嘅嘢（已測過，唔好重複）

- `pace_perf` 重配權（第八個 REJECT，holdout CI 全負）
- 讓磅**殘差**（AUC 0.4989 擲毫）
- 濕地拆軟/重地、改收縮強度、改 SCALE（三個都重驗過）
- 九個未入排名 leaf 直接加落 ability（全部 CI 跨零）
- 市場價入排名（w=0.0，等於放棄 edge，要改 methodology）
- 跳過低命中場次（ROI 反而變差）
