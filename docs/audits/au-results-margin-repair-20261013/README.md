# AU 結果 CSV `Margin` 修補（2026-10-13）

## 發現

`field_health.py --platform au --trend` 第一次跑就報到：live
`AU_Historical_Raw_Race_Results.csv` 嘅 `Margin` 由 2026-W35 起非空率係 0%
（之前大約 50–95%），而 W34 跌到 57%。
`au_healthcheck.CORPUS_COLUMNS` 唔包 `Margin`／`Time`，所以之前冇警報。

## 根因

- **2026-08-21 `26283f5a`**：每晚 ingest 開始先食 `sb_results_csv.py`，再由
  reflector 補冇覆蓋嘅部分。但嗰時 `sb_results_csv.FIELDS` 冇 `Margin`。
  `au_results_ingest.load_sb_csv` 於是將 margin 寫成「—」。reflector 嗰行本來有
  margin，但因為身份一樣，被 dedup 走咗。
- **2026-10-12 `e348a74e`**：`FIELDS` 加返 `Margin`，所以 10-12 起嘅新行已經正常。
- ingest 只會加新行、唔會改已有行，所以修好寫入端都補唔返歷史。

## 修補

全部用官方 CLI `au_results_ingest.py --fill-missing --sb-csv … --sb-lineage …`。
佢有三條規則：只補空白（`''／—／-`）、名次一定要相同先補、已有值一律保留。
每次都係先 dry-run，再 apply（自動備份），然後再 apply 一次確認零改動。

| 次序 | 來源 | 範圍 | 補咗 | 衝突 | 備份 |
|---|---|---|---:|---:|---|
| 1 | Codex EXP-20261012-01 `dated-source-v2`（Sportsbet cache，2,281 個 hash） | 08-05 至 10-10 | 18,944 | 20,900（全部保留原值） | `.bak_20261013T093047774043Z` |
| 2 | `extract_sportsbet_margin_source.py`（只讀 cache、`WC_SB_CACHE_ONLY=1`） | 10-11 | 477 | 477（只係 `Good` 對 `Good 4`，保留原值） | `.bak_20261013T093350757460Z` |
| 3 | `build_reflector_margin_source.py`（48 份 `Race_Results_Reflector.md`，逐份計 SHA256） | 08-21 至 08-30 | 3,154 | **0** | `.bak_20261013T093443739651Z` |

第 3 步點解需要：`sb_archive_meeting_ids.json` 完全冇 08-22 至 08-30 嘅場次，
所以 Sportsbet 嗰條路補唔到 W35。reflector 檔本身係有日期嘅賽後來源；檔頭寫明
場地同日期，lineage 綁實日期、場地同場次。08-21 至 08-23 本身有部分行已經有
margin，喺嗰啲行上 reflector 嘅值同已有值**零衝突**，咁就驗證咗呢個來源可信。

修補後每週非空率：W32–W42 全部 ≥ 94%，W35 由 0% 變 100%。

## 限制

- 只係賽後標籤 metadata，**唔係 PIT 認證**，唔可以當賽前輸入。
- 修補工具原樣寫入來源值（例如「5.22」），但 ingest 嘅慣例係「5.22L」；2026-04
  至 06 亦有大約 3,400 格冇 L。`scratch/` 入面嘅 harness 用 `([-+]?\d+(?:\.\d+)?)\s*L`
  解析，冇 L 嘅一律當「冇 margin」。所以同日做咗兩件事（見下面「格式統一」）。
- `Time` 仍然係 0%（W30 起）。Sportsbet 頁面只有頭馬時間（`WinningTime`），冇
  逐匹馬嘅時間。所以 `field_health.ACKNOWLEDGED` 將佢標成已知，唔再每週嗌。
- 冇正式 calibration 讀結果 CSV 嘅 `Margin`，所以冇嘢要重跑。我逐個查過所有讀呢個 CSV
  嘅 code：
  - `au_draw_bias_calculator`、`au_archive_calibrator` 等完全冇用 `Margin`。
  - `inject_fact_anchors` 嘅 margin 嚟自 formguide，唔係呢個 CSV。
  - `au_statistics_aggregator` 讀 markdown，而且只計檔位同騎練。
  - 真正讀呢欄嘅只有 `scratch/` 入面 4 個一次性實驗 harness，所以要統一格式。

## 格式統一（同日）

1. `au_dated_results_repair.canonical()`：修補工具寫入 `Margin` 時加「L」，同
   `au_results_ingest.load_sb_csv` 一致；比較照舊會先剝走「L」，所以唔會造出假衝突。
2. `normalise_margin_units.py`：將 live CSV 入面 26,585 格純數字 margin 加「L」。
   - 只改格式，數值唔變；「—」、已有「L」嘅值同其他寫法一律唔郁。
   - 寫之前逐行核對：其他欄位要完全一樣，`Margin` 只可以多咗一個「L」。
   - 先喺副本試：逐行比較啱啱好 26,585 行唔同，全部只係 margin 多咗「L」。
   - 第二次 apply 係零改動。
   - 備份：`.bak_20261013T102114574746Z_margin_units`。
   - 之後 2026-08 起有 25,983 格用 harness 嘅 regex 讀得返；剩低 300 格係「—」
     （大部分係頭馬，跟 reflector 嘅寫法）。

## 重現

```bash
cd /Users/imac/wongchoi-scheduler
python3 docs/audits/au-results-margin-repair-20261013/build_reflector_margin_source.py \
  "<AU_RACING>" <out_dir> 2026-08-21 2026-08-30
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_results_ingest.py \
  --fill-missing --sb-csv <out_dir>/rows.csv --sb-lineage <out_dir>/lineage.json \
  --fill-report <report.json>            # dry-run；加 --apply 先寫
python3 .agents/skills/shared_racing/scripts/field_health.py --platform au --record --since 2026-07-01
python3 .agents/skills/shared_racing/scripts/field_health.py --platform au --trend
```

`extract_sportsbet_margin_source.py` 係由 Codex 嘅
`docs/audits/au-full-model-20261011/extract_dated_result_sources.py` 改出嚟：
root 指向排程 worktree，日期限 08-24 至 08-30 同 10-11，並強制 cache-only。
08-24 至 08-30 冇 meeting ID，所以實際只抽到 10-11。
