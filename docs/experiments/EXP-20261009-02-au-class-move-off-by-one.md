# EXP-20261009-02 「今場降班」錯位一場 —— §7 正確性修正

- **日期**：2026-10-09
- **平台**：AU
- **假設**：唔係為咗變好。`horse.class_move` 讀賽績表最新一行嘅「班次」欄，嗰欄量嘅係
  「上上仗 → 上一仗」，唔係「上一仗 → 今場」—— 可以獨立證明係錯（契約 §7）。
- **搜索過嘅舊記錄**：EXP-20261009-01（發現）、EXP-20260903-01（班次乘數死咗）、
  記憶 `au-class-adjustment-dead-in-corpus`
- **改到嘅檔案／組件**：`au_racing_engine/engine_core.py`（`today_class_move`、
  `RacingEngine._class_move_today`，四個讀取點）、`build_au_logic.py` 同 engine 內嘅
  `_extract_latest_class_move`（唔再寫錯位值）、測試 `test_class_move_is_last_run_to_today.py`

## 配置
- **baseline**：`1c77d21f`（origin/main）
- **candidate**：今場班次變動 = `today_class_move(今場獎金, 上一仗獎金)`；任何一邊冇獎金 → 未知。
  另量 **live 等效版本**（今場獎金一律未知 → 班次變動一律 ""），因為 2026-08 轉 Sportsbet
  之後 `race_analysis.prize` 1,242 場得 1 場有值。

## 數據
- **語料**：`au_dump_engine_leaves.py` 全語料重評分（兩邊同一份 Logic，同一 commit 除咗呢個改動）
- **dev／terminal**：`au_eval.date_partitions`（尾 15% 日期）
- **樣本**：3,264 場 / 32,032 匹；改動郁到 2,797 場 / 8,587 匹（舊月份有今場獎金）

## 結果（配對 bootstrap，按場）
| | 正確計算版 | live 等效版 |
|---|---|---|
| dev Gold | +0.04pp [−0.12, +0.20] | +0.04pp [−0.12, +0.20] |
| dev Good位 | +0.12pp [+0.00, +0.28] | +0.08pp [+0.00, +0.20] |
| terminal Gold | +0.00pp [0, 0] | +0.00pp [0, 0] |
| terminal Good位 | −0.13pp [−0.38, +0.00] | −0.13pp [−0.38, +0.00] |
| Top5 AUC terminal | −0.00006 [−0.00076, +0.00075] | — |
| Stage 4 v2 | REJECT（`primary_regression`，terminal Good 少 1 場） | 同 |

### 預先聲明 cohort（§7：冇一個 CI 全負）
馬群 ≤8 / 9-10 / 11-12 / 13+、首選 SP ≤2 / 2-4 / 4-8 / 8-15 / 15+：兩個版本**冇一格 CI 全負**
（最差 11-12 匹 Gold −0.12 [−0.37, 0.00]）。

## 檢查
- **leakage-audit**：PASS —— 只用上一仗獎金（賽績表）同今場獎金（排位表），兩者賽前已知。
- **golden_scoring**：冇郁（golden 凍結 feature vector，唔重算 leaf；影響已經用全引擎重評分量過）
- **data_contract**：PASS
- **退步**：terminal Good 少 1 場（CI 上限 0.00），唔顯著

## 結論
**呢個冇通過表現閘，唔係一個已證實嘅改善。** 作為 §7 正確性修正上線：舊值令 15% 嘅馬報告寫錯
「降班」（例：一級賽 Sir Rupert Clarke Stakes 入面，上仗由 All-Star Mile 跑 Memsie 嘅馬被當今場降班），
其中冇官方評分嗰批經 `rating_score` 代理食咗 +6。如果績效數字相反方向，仍然會改 —— 錯係錯。
跟進：搵返今場獎金來源（Sportsbet 賽事頁冇；`claw_sportsbet_form.parse_race` 冇呢個欄），先可以
恢復真正嘅升降班訊號。

**決定**：KEEP（§7 正確性修正）
**commit**：未 commit

## 重跑
```bash
# baseline worktree（1c77d21f）同 candidate worktree 各跑一次
PYTHONDONTWRITEBYTECODE=1 python3 au_dump_engine_leaves.py --out base_leaves.json
PYTHONDONTWRITEBYTECODE=1 python3 au_dump_engine_leaves.py --out cand_leaves.json
# 比較：au_eval.compare(merged, default_scorer, cand_scorer) + 配對 bootstrap cohort 表
```
