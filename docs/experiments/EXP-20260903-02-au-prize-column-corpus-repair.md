# EXP-20260903-02 — 「班次水平調整」喺評估語料上熄咗 12 個月

- **日期**：2026-09-03；**平台**：AU
- **baseline**：`8b1a71499a3a`（= 當時 origin/main = production）
- **假設**：`horse_prize_level()` 讀嘅 Facts 獎金欄喺舊語料完全缺失，
  所以每一次回放評估喺 dev 窗量緊嘅係一個**冇施加班次水平調整**嘅模型，
  而 production 係有施加嘅。
- **搜索過嘅舊記錄**：EXP-20260903-01（同一輪，K1-K4）、EXP-20260825-02/03/04、
  EXP-20260826-06、EXP-20260902-06 候選 A、EXP-20260902-07 候選 L。
- **改到嘅組件**：`au_racing_engine/engine_core.py`（新 helper）、
  `au_dump_engine_leaves.py`（駁線）、新 regression 檔。

## 缺陷（可獨立證明，唔靠績效數字）

`horse_prize_level(facts_section)` 讀 `_record_rows` 嘅 `cols[18]`，
係 `_form_score` 入面「班次水平調整」`CLASS_PRIZE_K × (本駒近四仗獎金 log10 −
場內中位)` 嘅唯一輸入。個欄由 fact writer **2026-07-31** 先開始寫。

實測（20,843 匹）：**實際有施加**嘅比例

| 窗口 | 馬匹 | 有施加 |
|---|---:|---:|
| 2025-08 → 2026-07（12 個月） | 8,965 | **0.0%** |
| 2026-08 | 10,957 | 95.2% |
| 2026-09 | 921 | 92.6% |

**Live pipeline 冇壞。** 2026-09-03 當日四個場次實測 90.7–94.7%；
即係 production 一直有施加。壞嘅係**評估語料**。

⚠️ 後果：任何回放 harness（`au_dump_engine_leaves` → `au_eval` /
`au_matrix_refit` / leaf 消融）喺 dev 窗評緊嘅係一個同 production **唔同**嘅模型。
呢個唔止影響今次；EXP-20260902-06 候選 A、EXP-20260902-07 候選 L 兩個
「逐仗獎金班次係數」都聲明用「現有獎金來源」，而嗰個來源喺佢哋成個 dev 窗係空。
**嗰兩個 dev 結果要當作未測過，唔可以當已否定。**
`_form_score` 註釋寫嘅「A/B（713 場）K=10：dev 全部指標變好或平」亦係同一個問題：
713 場大約就係 2026-08 之前嘅語料量，即係嗰次驗證好可能量緊一個冇生效嘅功能。

## 唔係數據冇咗，係表冇寫

Facts 由 Formguide 生成，而 Formguide **243 個語料場次全部仲喺度**，
逐仗 `$獎金` 逐月 **100%** 覆蓋（169,424 條非試閘行）。
旁證：`class_move`（獎金比率推導）喺 2025-08 已經 98.5% 有值 —— 生成當時有獎金，
只係冇寫入表。

## 修復

新 `backfill_prize_column(logic, meeting_dir, race_no, meeting_date)` 喺
`engine_core`，由 `au_dump_engine_leaves` 喺 `_build_field_summary` **之前**呼叫
（同 `refresh_pf_own_l600` 同一個理由：調整係「本駒 − 場內中位」，兩邊要同一個量度）。

邊界：

- 賽日**當日或之後**嘅往績一律唔用。語料實測 62 行係賽後重抓污染。
- 試閘行唔郁。
- 已經有值嘅欄唔覆蓋（2026-08/09 回填後覆蓋率 95.3%→95.3%、93.2%→93.2%，冇郁）。
- **檔名要逐字對死場次號**。⚠️ 開頭條 regex 用 `Race\s*(\d+)`，
  而有啲 meeting 除逐場檔仲有合併檔 `03-28 Race 1-10 Formguide.md`，
  喺佢度會攞到 `1`；合併檔入面每場嘅 `[N]` 由 1 重新數，
  所以第 1 場 3 號馬會靜靜攞到第 2 場 3 號馬嘅獎金。**實測 3 場中招**，
  已改為 `\bRace\s*(\d+)\s+Formguide\b` 並加咗 regression 測試。

回填後：每個 2026-08 之前嘅月份由 **0.0% → 87.5–100%**；全語料 51,035 行填返。

## 結果 —— 呢個**冇通過**表現閘

配對同場同馬，1,861 場共同場次（baseline dump 之後語料多咗 2026-09-03 四個場次，
已鎖返預先登記嗰批）。sample hash `35b97b5085…e00b8a`。7,132 匹（38.4%）分數有變。

| dev 指標 | baseline | 修復後 | Δ |
|---|---:|---:|---:|
| gold | 17.365% | 17.216% | **−0.150pp**（−2/1336 場）|
| good_positional | 22.081% | 22.754% | **+0.674pp**（+9/1336 場）|
| pass | 44.611% | 44.686% | +0.075pp |
| champion | 23.428% | 23.503% | +0.075pp |

一個 primary 跌、一個升 → **過唔到 Stage 4 v2 候選閘，terminal 冇開，
亦冇換指標／換窗去救佢**。

### 合約 §7 驗收（2,000 次逐場配對 bootstrap）

| 指標 | 窗口 | Δ | 95% CI | CI 全負？ |
|---|---|---:|---|---|
| gold | 全部 (1861) | −0.108pp | [−0.431, +0.215] | 否 |
| gold | dev (1338) | −0.150pp | [−0.599, +0.300] | 否 |
| good_positional | 全部 | +0.484pp | [−0.108, +1.130] | 否 |
| good_positional | dev | +0.674pp | [−0.150, +1.572] | 否 |

⚠️ **terminal 兩個 primary 都係 +0.0000pp、CI [0,0]** —— 唔係「terminal 通過」，
而係**terminal 窗（2026-08-19 起）本身已經有獎金欄，回填喺嗰度完全冇嘢做**。
所以呢個驗收實質上只喺 dev 量到。要如實咁講。

18 個預先聲明 cohort（馬群大細 ×4 + 首選 SP ×5，兩個 primary）
**冇一個 CI 全負** → §7 條件 2 滿足。
收益集中喺大馬群：`good_positional` 13+ 匹 **+2.546pp [+1.091, +4.727]**、
11–12 匹 +0.866pp [0.000, +1.948]，同「場內相對班次比較喺大場次有更多嘢可比」一致。

§7 濫用測試「如果數字方向相反，你仲會唔會照修？」——**會**。
一個逐匹馬嘅調整靜靜熄咗 12 個月，代表嗰段時間所有評估量緊嘅唔係 production 個模型；
呢個同數字方向無關。

## 順帶：矩陣 refit（用戶要求嘅第 3 項）

喺**修復前**語料 refit（3,000 條隨機權重 → 380 贏 dev → 130 過 4/5 fold）：
Stage 4 頭 5 位 AUC dev −0.0016、holdout −0.0002 [−0.0060,+0.0056] → REJECT。
喺**修復後**語料重跑（145 條過閘）：共識
`stability .3059 / pace_perf .1397 / race_shape .0147 / jockey_trainer .6747 /
class_weight .3633 / track .1112 / preparation .3212`，
Stage 4 頭 5 位 AUC dev −0.0016、holdout −0.0017 [−0.0069,+0.0039]，
gold −0.37、Good位 −0.58 → **REJECT / primary_regression**。

修復前嗰個 refit **唔算數**（尺本身錯）。修復後嗰個先係第一次喺啱嘅尺上做嘅 refit，
結果係第四次獨立確認現行權重郁唔到。

## 檢查

- **leakage-audit**：PASS。只讀存檔賽前 Formguide；賽日當日／之後嘅往績一律剔走
  （實測 62 行）；獎金係該仗**已完成**賽事嘅公開資料，落注時刻攞得到；
  賽果只作評估 label。⚠️ 保留限制：2026-08-05 之前嘅 archive 本身有事後重建問題
  （`au-archive-rescored-post-race`），呢個修復冇改變嗰個限制。
- **golden_scoring**：冇郁 —— helper 只由 dumper 呼叫，live 評分路徑完全冇改。
- **data_contract**：冇 live 改動。
- **退步**：dev `gold` −0.150pp（CI 跨零，唔顯著）。已記錄。

## 結論

1. Live 模型冇壞；壞咗嘅係**評估語料**，而且壞咗 12 個月。
2. 修復令 dev 窗嘅回放同 production 對齊。**呢個冇通過表現閘，
   唔係一個已證實嘅預測改善** —— 走合約 §7 正確性修正。
3. 呢個修復令一批舊結論要重新審視：任何**用 dev 窗判死同班次／獎金有關嘅候選**
   嘅記錄（至少 EXP-20260902-06 A、EXP-20260902-07 L）要當作未測過。
4. 矩陣 refit 喺啱嘅尺上一樣 REJECT。

**決定**：**KEEP（合約 §7 正確性修正，非表現改善）**；refit **REJECT**。

## 重跑

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out /private/tmp/au-repaired-corpus.json
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_prize_section7_20260903.py \
  --baseline /private/tmp/au-class-baseline.json --candidate /private/tmp/au-repaired-corpus.json --iterations 2000
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_matrix_refit.py refit --data /private/tmp/au-repaired-corpus.json --obj place
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_eval.py \
  --data /private/tmp/au-repaired-corpus.json --matrix-weights /private/tmp/refit-repaired-consensus.json --leakage-audit-passed
```

baseline dump（修復前）要由 `8b1a71499a3a` 產生，唔可以喺候選工作樹重新命名。
原始 dump 全部留 `/private/tmp/au-*.json`（每個約 11 MB），冇入 repo。
