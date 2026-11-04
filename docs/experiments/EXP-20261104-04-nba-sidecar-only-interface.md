# EXP-20261104-04 — NBA Stage 2：sidecar 做唯一機器介面

- 日期：2026-11-04
- 平台：NBA（dashboard 匯出、發佈防火牆、SGM 匯總報告）
- 基準 commit：`2cdee5f2`（nba_engine 上線）
- 類型：**工程重構，唔改模型**。`report.py` 寫出嚟嘅 Markdown 逐 byte 不變；sidecar 加兩欄。

## 改咗咩

| 位置 | 之前 | 之後 |
|---|---|---|
| `multisport_exporter` | `_parse_nba_combos` / `_parse_nba_leg_row` regex 解析 Markdown 標題同 `🧩` 腿表格，`_hydrate_nba_quotes` 再對 sidecar | `nba_report_sidecar()`（`report_sha256` 對得上先信）+ `nba_combos()` 全部由 sidecar `combos`／`legs` 砌 |
| exporter 入口檢查 | Markdown 要有 `SPORTSBET_LIVE`、`Python Auto-Selection`、`未填寫項目 殘留: 0`、冇 `[FILL]` | sidecar 綁定 + `schema_version == nba-market-eval-legs/v1` |
| `nba_tracking` | 同一套 Markdown 解析 | `nba_combos()` |
| `nba_engine/publish.py` | 由 Markdown 標題讀組合 id 同「印出嚟嘅價」再對 sidecar | 只讀 sidecar：報價要等於組合自己嘅 `sportsbet_sgm_price` |
| `generate_nba_sgm_reports.py` | 由 Markdown 剪組合區塊 | 由 sidecar 砌；sidecar 缺失／對唔上 → exit 1，唔寫檔 |
| `report.py` sidecar | — | 組合加 `heading`（標題字串）；每條腿加 `cov` |

舊引擎（11-04 之前）嘅 sidecar 冇 `heading`，exporter 用 `NBA_LEGACY_TITLES`（由 418 份歷史報告實際出現過嘅
7 種標題列出，按 `combo_id` + 有冇 `selection_rule` 分）。舊 sidecar 冇 `p_market`，edge 用舊報告嘅慣例
`p − round(1/price, 4)`（試過 `p − 1/price`，12/591 條腿差 1e-4）。

## 事前核對（418 份 sidecar：資料根 + `/Users/imac/wongchoi-scheduler`，連 `_prediction_snapshots`）

- `report_sha256` 全部對得上報告。
- 每份報告嘅 Markdown 組合標題 id 同 sidecar `combos` id 完全一樣（0 份唔同）—— 所以刪走防火牆「兩邊組合唔同」呢個檢查唔會放生任何歷史報告。
- 標題價 = `sportsbet_sgm_price`（有報價時，160/160）否則 `product_of_leg_prices`（144/144）。
- 940 條組合腿全部喺 sidecar `legs` 搵到（L10 命中率由嗰度攞）。
- Markdown 有 `正式穩膽政策：banker-steady-b2-v1` ⇔ `strategy_profile == banker-steady-b2-v1`（180/180）。

## 結果：匯出 JSON 前後對比

命令（`docs/experiments/evidence/EXP-20261104-04-nba-sidecar-export-parity.py`）：

```bash
git worktree add --detach <scratch>/base 2cdee5f2
PYTHONDONTWRITEBYTECODE=1 python3 <evidence> dump <scratch>/base before.json
PYTHONDONTWRITEBYTECODE=1 python3 <evidence> dump . after.json
python3 <evidence> diff before.json after.json
```

27 個賽日 × {live snapshot、settlement（無防火牆＋舊策略）、betting card（凍結時刻防火牆）} + tracking（55 條記錄）。

**完全一樣**：每個賽日嘅推薦 id、組合價、`odds_status`、標題、risk、decision、腿（球員／盤口／線／價／模型機率／L10／edge）、
analysis cards、latest_analysis；tracking 55 條記錄嘅 id、價、state、profit、腿結算。

**有分別（全部預期）**：

1. `source_row`（原本嘅 Markdown 表格行）冇咗 —— 495 處。前端冇用。
2. 舊引擎腿嘅 `coefficient_of_variation` 由 Markdown 數字變 null（舊 sidecar 從來冇存 CoV）。前端只喺單項 banker
   卡顯示 CoV，而 banker 單項只喺 settlement 路徑出現，唔顯示 —— dashboard 睇唔到分別。新引擎 sidecar 而家有 `cov`。
3. 3 條腿 `expected_value` 差 1e-4（例：−0.0416 → −0.0415）：舊引擎用未四捨五入嘅機率計 EV，sidecar 只存咗 3 位小數。
4. `wongchoi-scheduler` 入面 2026-10-10～10-15 季前賽報告**冇 sidecar**（sidecar 之前嘅年代），而家 settlement 匯出
   報 `nba_report_validation_failed`（41 個季前賽 shadow 推薦唔再匯出）。呢幾日早已結算、唔喺 tracking（由 10-25 開始），
   亦唔喺 task 要求嘅 10-21 之後範圍。

新引擎報告（未有真實賽日；用 `nba_engine/tests` 嘅 fixture）：舊 Markdown 解析 vs 新 sidecar，id／價／標題／狀態／腿一樣；
機率、edge、EV 由 Markdown 嘅 1 位小數百分比（0.643）變返 sidecar 精度（0.6429）。

## 測試

Dashboard 154、NBA 472 全過；`./檢查.sh` 見交付紀錄。fixture 由「寫 Markdown」改為「寫報告 + 綁定 sidecar」，
新加：報告改過之後 sidecar 唔再被信（exporter 同 SGM 匯總）。

## 未做（跟進）

- **Reflector 仲讀 Markdown**：`nba_reflector_orchestrator.parse_combo_table_rows`／`parse_player_cards` 同
  `verify_props_hits` 解析 `| 🧩 n |` 腿表格。搬去 sidecar 之前，`report.py` 嘅腿表格格式唔可以改。
- extractor／orchestrator 簡化（Stage 2 第 4 項，optional）未做。
