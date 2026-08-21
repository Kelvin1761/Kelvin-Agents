# EXP-20260821-01 AU 語料庫有一半係所有評估工具睇唔到嘅

- **日期**：2026-08-21
- **平台**：AU（HKJC 已檢查，唔中招）
- **類型**：數據品質審計（唔係模型實驗）
- **起因**：`./檢查.sh` 第 4 步兩個平台都出 `stale-baseline` 警告。查成因嗰陣發現咗更大嘅問題。
- **搜索過嘅舊記錄**：`au-archive-folder-is-the-corpus`（同一個問題，當時 33 個場次中招）

## 一、原本要查嘅嘢：stale-baseline 係假警報

`data_contract` 嘅基準帶住引擎指紋，指紋一變就拒絕相信自己。

| | 基準建立時 | 而家 |
|---|---|---|
| AU 指紋 | `2bcf60a0c371` | `230ac5bc7b00` |
| HKJC 指紋 | `202f8c6353ff` | `60e3db4064a5` |

成因係 commit `900e49c1`（08-21 14:36）「引擎改為獨立命名 package」。實測：

- `au_racing_engine/scoring.py`、`hkjc_racing_engine/scoring.py`：**0 行改動**（純搬位）
  → `MATRIX_WEIGHTS`、`MATRIX_FORMULAS`、`MATRIX_DISPLAY_GAINS` 逐個 byte 一樣
- `matrix_mapper.py` + `engine_core.py`：合共 9 行，**全部** 係 `from x` → `from .x`
- golden snapshot 係 `f385c0cc`（14:15）錄嘅，**早過** refactor，refactor 冇動過佢，
  而家仍然 **AU/HKJC 各 120 匹馬全部一致**

**結論：模型行為冇變，指紋漂移純粹係 import 路徑。** 呢個警告本身係對嘅設計
（指紋涵蓋整個檔案內容），但呢一次唔代表數據或模型有事。

## 二、真正嘅發現：`Archive/` 令一半語料消失

AU 資料根目錄嘅結構：

```
AU_Racing/
  2026-08-21 Sale Race 1-9/        Race_*_Logic.json   ← 2 層
  ...
  Archive/
    2026-08-20 Dubbo Race 1-7/     Race_*_Logic.json   ← 3 層
    ...
```

每日排程會將完成嘅場次搬入 `Archive/`（`au_runtime_micro_ablation.py:137` 寫明）。
但大部分 harness 用 `*/Race_*_Logic.json` 或 `root.iterdir()` —— **只掃一層**。

| | 場次 | 場數 | 日期數 | 範圍 |
|---|---|---|---|---|
| 頂層（睇得到） | 90 | 779 | 65 | 2025-08-02 → 2026-08-21 |
| `Archive/`（睇唔到） | 96 | **751** | 21 | 2026-07-15 → 2026-08-20 |

- **零重疊**（場次名 0 個相同、日期 0 個相同）—— 唔係複本，係淨損失
- **49.1%** 嘅已評分場次隱形
- 頂層最新一個非今日嘅日期係 **2026-07-12**，之後 40 日全部喺 `Archive/`

### 最嚴重嘅一點

按 `au-archive-rescored-post-race`，AU 語料只有 **2026-08-05 之後**係乾淨
point-in-time（之前嘅係賽後重新評分過）。而：

- 頂層 08-05 之後嘅日期：**1 個**（就係今日 08-21）
- `Archive/` 08-05 之後嘅日期：**16 個**

**唯一冇洩漏嘅一段語料，恰好就係所有工具睇唔到嘅一段。**

### 實測影響（同一個 harness，只改枚舉方式）

`au_dump_engine_leaves.py` 係 `au_eval` / `au_feature_ab` / `au_matrix_refit`
三個判決工具嘅唯一數據來源。

| | 場數 | 匹數 | `pace_figure` state=ok |
|---|---|---|---|
| 現行（`ARCHIVE_ROOT.iterdir()`） | 721 | 7,642 | 33.7% |
| 遞歸（連 `Archive/`） | **1,413** | **14,121** | **62.9%** |

拆開睇 PF 覆蓋率：

- 睇得到嗰半：2,575 / 7,642 = **33.7%**
- 睇唔到嗰半：6,309 / 6,479 = **97.4%**

新增嘅 692 場全部係 2026-07-15 之後（Sportsbet 年代），所以 PF 覆蓋率跳升
係組成造成，唔係欄位變好。但呢個直接影響 `au-pf-coverage-unlock-needs-refit`
嗰條線：當時三次試「補」PF 覆蓋率都輸，而**真實**嘅 97.4% 覆蓋數據一直坐喺
`Archive/` 冇人睇過。「PF 覆蓋率只有 33.7%」呢個前提本身就係盲點造成嘅。

### 邊個中招

修正係逐個 harness 補嘅，唔係一次過：

**✅ 睇得到（用 `rglob` 或 `[root, root/"Archive"]`）**
`au_archive_calibrator`、`au_results_ingest`、`au_paired_significance`、
`au_runtime_micro_ablation`、`au_build_jt_ratings`、
`au_backfill_sportsbet_performance_quality`、`au_daily_schedule`

**❌ 只掃一層**
`au_dump_engine_leaves`（← 最要緊嗰個）、`data_contract`、`racing_data_health`、
`golden_scoring`、`explain_model`、`au_hkjc_gap_report`、`au_auto_orchestrator`、
`au_healthcheck`、6 個 reflector shadow test、`au_data_explorer`、
`au_overrated_horse_audit`、`au_jt_*`、`extract_top2_misses` 等（共 29 個檔）

### 修法唔可以係「一律改 rglob」

HKJC 遞歸會多 22 個 Logic，但佢哋係 backup／重複：
`2026-06-24_HappyValley/_pre_v52_backup`（9）、
`2026-06-27_ShaTin/.backup_before_trackwork_fix`（4）、
`2026-05-13_HappyValley/2026-05-13_HappyValley`（9 —— 自我嵌套）。
`rglob` 會靜靜雞把 backup 當語料，同時重複計一個場次。

AU 嘅深度分佈乾淨：779 個 2 層 + 751 個 3 層（**全部** 第一段係 `Archive`），
冇 4 層、冇 backup 目錄。

所以正確修法係 **`[root, root/"Archive"]` 各掃一層** —— 同 `au_results_ingest.py:169`
及 `au_paired_significance.py:57` 已經用嗰個 pattern 一致，對 HKJC 係安全 no-op。

## 三、我停喺邊，同點解

**冇重新 calibrate `data_contract`。** 原本計劃係 calibrate 兩個平台。唔做，因為
基準會由「睇得到嗰半」學返嚟 —— 即係把盲點寫成正常。現有基準只有 40 場 / 1 日
（`2026-08-21 Beaudesert` → `Sale`），本身就係盲點造成：頂層根本冇 07-12 至 08-20
嘅數據可以入窗。

**冇改任何枚舉 code。** 改 `au_dump_engine_leaves` 會令每一個未來 A/B 換一把尺，
並且令 07-15 之後所有用過呢個 harness 嘅結論需要重算。呢個係 Kelvin 嘅決定，
唔係我可以順手做嘅。

## 四、建議次序

1. 改 `data_contract` + `racing_data_health` 嘅枚舉（純閘門，唔影響評分）→ 重新 calibrate
2. 改 `au_dump_engine_leaves` 嘅枚舉 → 重建 leaves → **重跑 `au_matrix_refit verify`**
   確認 replica 仍然同引擎逐匹一致
3. 之後才立 baseline。喺 721 場語料上立嘅 baseline 唔應該用嚟判 1,413 場嘅候選。

**決定**：待 Kelvin 決定（第 2 步會令舊 A/B 數字作廢）
**commit**：未 commit

## 重跑

```bash
# stale-baseline 成因
git diff -M --stat 900e49c1^ 900e49c1 -- '*racing_engine/scoring.py' '*racing_engine/matrix_mapper.py' '*racing_engine/engine_core.py'
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform au
python3 .agents/skills/shared_racing/scripts/golden_scoring.py --platform hkjc

# Archive 盲點規模
find "$AU_RACING" -name "Race_*_Logic.json" | sed "s|$AU_RACING/||" | awk -F/ '{print NF}' | sort | uniq -c

# 現行 vs 遞歸（遞歸版靠 in-memory patch 跑，冇改 repo 檔案）
cd .agents/skills/au_racing/au_wong_choi_auto/scripts
PYTHONDONTWRITEBYTECODE=1 python3 au_dump_engine_leaves.py --out /tmp/leaves_current.json
# 遞歸版：把 `ARCHIVE_ROOT.iterdir()` 換成 `{p.parent for p in ARCHIVE_ROOT.rglob("Race_*_Logic.json")}`
```
