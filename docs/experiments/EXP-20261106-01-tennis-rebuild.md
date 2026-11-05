# EXP-20261106-01 — Tennis Wong Choi 全面重建（重播等價）

- 日期：2026-11-06；平台：Tennis；類型：**結構重建**（模型數學 `tennis-v1` 冇改；7 個定價 family 輸出逐行一樣）。
- 計劃：`docs/plans/2026-11-05-tennis-strategy-and-rebuild-plan.md` 階段三；執行紀錄
  `docs/plans/2026-11-06-tennis-rebuild-log.md`。Kelvin 2026-11-05 確認：成個重建、唔係部分。

## 量度方法（預先定好）

- 凍結 DB：live `tennis_wc.db` 嘅 `.backup`（2026-11-06 00:48，main `c6e0e092`），放外置碟
  `WongChoi-Archive/scratch/tennis-rebuild-20261105/baseline.db`，以 `immutable=1` 開。
- **定價層**：`docs/experiments/patches/tennis_rebuild/replay.py`。舊引擎經攔截 `record_prop`、新引擎經
  `tennis_wc.engine_api.price_props`，比較每一行會寫入 `prop_tracker` 嘅值（包括寫入嗰刻凍結嘅
  `pricing_evidence_json`），`utc_now` 釘喺每日 00:00 UTC，容差 1e-9。窗口 2026-10-28 至 11-05。
- **結算層**：`replay_settle.py`。瘦身 DB（`prop_tracker`、`match_results`、`matches`、`player_match_history`），
  將 2026-10-01 起所有已結算行重設做 PENDING，新舊 `settle_props` 各跑一次，比較每一行。

## 結果

| 層 | 樣本 | 差異 |
|---|---|---|
| 定價（7 family） | 9 日、482 場、978 行 | **0** |
| 結算 | 11,712 行重新結算（10,849 計分、445 void、73 棄結） | **0**（summary 同每行都一樣） |

唯一預期差異（預先列明）：舊 evidence 入面 ace／雙誤 profile 唔再出現（呢兩個 family 已暫停定價）。

## 改動

| | 重建前 | 重建後 |
|---|---|---|
| `src/` | 36,907 行、158 檔 | 約 17,500 行、102 檔 |
| CLI 命令 | 47 | 7（init-db、config-check、network-check、price、review、featured、record-live-prop-bet） |
| 排程入口 | `tennis_daily_schedule.py` 1,401 行 ＋ `tennis_night_card.py` | 一個約 330 行嘅 `tennis_daily_schedule.py` ＋ `run.py` |
| 帳本 | `prop_tracker`、`clv_tracker`、`combo_tracker`、`market_predictions`、`predictions` BET | `prop_tracker` ＋ `featured_picks` ＋ `prop_live_bets` |
| 測試 | 104 檔 | 60 檔、551 個測試，全過 |

- 新結構（第二輪 2026-11-06 完成）：`sources/`（原 `ingestion/`、`providers/`、`identity/`、`validation/`）、
  `store/`（原 `database/`，併埋重複嘅市場捕捉同賽果一致性 module）、`model/`（原 `features/`、`modelling/`、
  `history/`、`segment_risk`）、`pricing/`、`select/`、`settle/`、`publish/`、`run.py`、`monitor.py`。
  再剷 23 個冇人引用嘅函數／常數（453 行）同死咗嘅 `app/dashboard.py`。搬完後定價重播仍然 0 差異。
- 剷走：81 個冇入口可達嘅 module（21,879 行：agents、bet_filter、ledger、combos、devig、5,208 行 daily_report、
  research_*、ace／雙誤模型等）、33 個一次性研究腳本（git 歷史保留）。
- 計劃列明要修嘅 bug：
  1. card 用累計歷史封鎖 → 已喺階段一由精選取代；重建後冇呢條路。
  2. 兩本帳結算唔一致 → 只寫 `prop_tracker`。重新量：8 月 49 注球員總局數兩本帳唔一致，抽樣逐注對實際局數，
     錯嘅係 `clv_tracker`（例如實際 9 局、Over 10.5，`clv_tracker` 判贏）；`prop_tracker` 啱，所以唔使重算。
  3. 組合冇記錄 → 組合 code 剷走。
  4. 自動閘重複測試 → `recommendation_gate` 剷走；精選只會停唔會自動開。
  5. 同場疊注 → 精選一場一注（階段一）。
- Dashboard（`tennis_tracking.py`）只讀 props＋精選＋實盤；舊 match／market／combo 紙上注留喺 DB，唔再顯示。
- 重建途中搵到：`EXP-20261105-08` 撞號（AU 同 tennis 共用），tennis 改為 `EXP-20261105-10`。
- 冇改：模型數學、15 個 REJECT_DEV、Codex 數據防線（event id、賽前階段、排名日期、身份合併、來源歸屬；
  相關測試照跑）。

## 未做／限制

- 抓數層（而家喺 `sources/`）已搬位同清死函數，但冇逐行重寫：原始 HTML 冇存，冇辦法做重播對比；
  live 結構未變，改寫要等有回應存檔先做（計劃「兩層重播」嘅抓數層未能做到，照實記低）。
- 舊 match／market 紙上注同 CLV 唔再計。

## 重現

```bash
B="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-rebuild-20261105"
python3 docs/experiments/patches/tennis_rebuild/replay.py --src <old tree>/tennis-wong-choi/src --db "$B/baseline.db" --start 2026-10-28 --end 2026-11-05 --out old.json
python3 docs/experiments/patches/tennis_rebuild/replay.py --src tennis-wong-choi/src --db "$B/baseline.db" --start 2026-10-28 --end 2026-11-05 --out new.json
python3 docs/experiments/patches/tennis_rebuild/replay.py --diff old.json new.json
```
