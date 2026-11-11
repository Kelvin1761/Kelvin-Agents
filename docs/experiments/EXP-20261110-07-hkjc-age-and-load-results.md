# EXP-20261110-07 — HKJC 馬齡同出賽負荷：結果

- **日期**：2026-11-10
- **平台**：HKJC
- **假設**：老馬（≥8 歲）被高估、年輕馬（≤4 歲）被低估；60 日內出賽 ≥4 仗嘅馬被高估；備戰第 3–4 仗嘅馬被低估（[協議](EXP-20261110-07-hkjc-age-and-load-protocol.md)）
- **搜索過嘅舊記錄**：EXP-20261027-12（P5 快速回師、P6 長休）、EXP-20260904-08（長休罰分）、EXP-20261029-01（上仗後負荷）；引擎冇讀馬齡
- **改到嘅檔案／組件**：冇改 live；新增 `patches/hkjc_age_load_scan.py`、`patches/hkjc_results_dedup.py`

## 配置
- **baseline**：`origin/main` 80e734dd，`hkjc_eval_harness run`（point-in-time），同 EXP-20261110-06 同一份排名
- **candidate**：冇（研究掃描）

## 數據
- 賽果庫 2024-09-08 → 2026-11-08，**已去重**（見下）。D 10,276／V 7,319／M 5,431 匹次（5,312 對到模型排名）
- 馬齡：M 段 45 個賽日排位表，對上 5,305／5,312 = **99.87%**
- leakage：0 行

## ⚠️ 發現：賽果庫 2026-05 起每場存咗兩份

第一次跑嘅時候，F1 喺 M 段有 1,781 匹次，但同樣長度嘅 V 段得 137 —— 唔合理。查落去：
`HKJC_Race_Results_Database/hkjc results */<日期>/` 由 2026-05 起每日有 `<日期>_<場地>_全日賽果.json` **同**
`full_day_results.json` 兩份，350 場逐匹馬一模一樣。`hkjc_situational_overlay_scan.load_days` 用 `*/*.json` 兩份都讀，
所以每場計兩次，60 日內出賽數直接翻倍。

- 研究掃描：新增 `patches/hkjc_results_dedup.load_days`，按（日期、場地、場次）留一份。本實驗同 EXP-20261110-06 已改用。
- EXP-20261027-12 覆核：P1 +5.13 → +4.73 [+1.09,+8.49]，p 仍然 0.003，**結論企得住**（重複主要係同日加倍權重，賽日 bootstrap 頂得住）。
- 生產：`hkjc_racing_engine/overlays.py::_jockey_wins_by_day` 用同一個 glob，頂級騎師勝出數 2026-05 起會計雙倍。
  但 `OVERLAY_WEIGHTS` 全部係 0（shadow），**live 排名冇受影響**；受影響嘅只係匯出畀 refit／ML 嘅 overlay 欄。
  其他讀賽果庫嘅 code（`hkjc_results_db.py`、`build_rail_draw_dataset.py`、`build_comprehensive_stats.py`）只讀其中一個檔名或者用 set，冇呢個問題。
- **已修（同日）**：
  - `overlays.py::_jockey_wins_by_day` 按（日期、場地、場次）去重。用真數據比較，104 個賽日入面有 11 個（2026-06-13 → 09-09）頂級騎師名單換咗一個人
    （例如舊版因為 5 月後勝出數計雙，揀咗莫雷拉而唔係何澤堯）。overlay 全部 shadow，HKJC golden 冇郁。
  - 根源係兩個 writer（`hkjc_results_db.sync_meeting_results` 同 `sync_hkjc_results_database.sync_meeting_results`）每日寫兩個名。
    而家只寫 `full_day_results.json`／`.md`，所有 reader 本身都用緊呢個名。
  - 37 個 `*_全日賽果.*` 重複檔（2.8 MB，逐 byte 同 canonical 一樣）搬去 `~/.Trash/hkjc-results-duplicates-20261110/`（保留相對路徑，要還原就搬返去）。
    賽果庫而家 1,876 場、0 場重複。

## 結果（去重後）

L2 模型鏡頭（主判決，模型排名分層 1–3／4–6／7+，賽日 bootstrap 2000 次）：

| Pattern | 方向 | M 匹次 | 入位率 | 分層差 | 95% CI | p 單邊 | Holm | 候選 |
|---|---|---:|---:|---:|---|---:|---:|---|
| A1 馬齡 ≥8 | − | 154 | 18.8% | −3.73pp | [−9.93, +2.59] | 0.125 | 0.500 | ✗ |
| A2 馬齡 ≤4 | + | 2,416 | 24.0% | +1.16pp | [−1.04, +3.30] | 0.132 | 0.500 | ✗ |
| F1 60 日內 ≥4 仗 | − | **51** | 25.5% | +0.29pp | [−10.47, +10.97] | 0.507 | 0.507 | ✗（n < 80） |
| F2 備戰第 3–4 仗 | + | 688 | 26.2% | +1.33pp | [−1.52, +4.02] | 0.171 | 0.500 | ✗ |

L1 市場鏡頭（只有 F1／F2，佐證）：

| Pattern | D | V |
|---|---|---|
| F1 | −3.97 [−8.93, +1.06] n226 | −1.65 [−9.23, +5.59] n137 |
| F2 | **−5.91 [−10.41, −1.52]** n324 | −1.33 [−3.04, +0.34] n1,508 |

未去重嘅第一次跑法（只作對照，F1／F2 喺 M 段係錯嘅）：A1 −3.70 n280、A2 +1.17 n4,282、F1 +1.34 n1,781、F2 −1.65 n1,768。

## 檢查
- **leakage-audit**：PASS —— 負荷只用 < 賽日紀錄（leak 0）；馬齡係靜態欄
- **golden_scoring**：冇郁
- **data_contract**：唔適用
- **退步**：冇（冇改 live）

## 結論

四個都**過唔到閘**，冇 overlay 候選。

- **馬齡**：方向同預期一樣（老馬 −3.7pp、年輕馬 +1.2pp），但都唔顯著。≥8 歲喺 M 段得 154 匹次，CI 闊到 ±6pp，
  **係冇功效，唔係證明冇效**。年輕馬樣本夠大（2,416），效應最多大約 +3pp，模型應該已經大致捉到（馬齡同評分、
  近績、生涯場數高度相關）。馬齡淨係 2026-04 之後先有，要等多啲數據先值得再測老馬。
- **出賽密度（F1）**：香港 60 日內跑 4 仗好罕見（M 段 51 匹次），**呢個問題喺香港基本上唔存在**，測唔到亦唔重要。
  再加上 EXP-20261027-12 P5 快速回師冇訊號，「跑得密會攰」喺模型鏡頭下冇證據。
- **備戰週期（F2）**：模型鏡頭 +1.3pp 跨零。市場鏡頭 D 段反而顯著負（−5.9pp），即係市場**高估**咗第 3–4 仗嘅馬，
  但 V 段只係 −1.3 跨零，冇重現。

**決定**：REJECT（全部 pattern 唔過；馬齡老馬一項係功效不足，記低等數據）
**commit**：未 commit model code（冇 model code）

## 重跑
```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py run \
  --since 2026-04-12 --until 2026-11-08 --out <scratch>/model.jsonl
python3 docs/experiments/patches/hkjc_age_load_scan.py --model-run <scratch>/model.jsonl --out <scratch>/age_load.json
```
