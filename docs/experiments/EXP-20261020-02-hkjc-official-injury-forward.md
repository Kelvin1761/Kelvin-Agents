# EXP-20261020-02 — B1 forward 一次性確認：預先登記

- **登記日期**：2026-10-21，forward 窗口開始**之前**（今晚跑馬地係第一個賽日）
- **觸發**：回放 B1（官方傷患記錄當醫療事故 −12／有康復證據 +6）Holm 後唔顯著 → UNRESOLVABLE。
  Kelvin 2026-10-21：由 2026-10-21 起逐場記錄 B1 排名做 forward shadow，≥ 60 場一次性確認先轉 issue。
- live 維持 `scoring.OFFICIAL_INJURY_SCORING = "off"`；forward 期間**唔改**。

## 點量

每週 review（`hkjc_daily_schedule.run_weekly`）代跑，結果放 `<HK 資料根>/Forward_Checks/EXP-20261020-02/`：

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
python3 $H run --since 2026-10-21 --out live.jsonl
python3 $H run --since 2026-10-21 --arm $P/hkjc_arm_official_injury_issue.py --out candidate_issue.jsonl
python3 $P/hkjc_official_injury_forward.py live.jsonl candidate_issue.jsonl
```

harness 行嘅係 production scoring path；B1 係同一份 Logic 開咗開關重算，所以係 shadow 排名，唔影響 live 推介。

## 判定（寫死喺 `hkjc_official_injury_forward.py`，唔准改）

- 剔走 score 失敗同 `risk_score` 死欄位嘅賽日；兩邊都有先計。
- **< 60 場** → WAIT，每週照報。
- **第一次 ≥ 60 場** → 一次性判定，之後凍結（state `official_injury_forward_final`），唔再重跑：
  - Gold Δ ≥ 0 **而且** Good Δ ≥ 0 **而且** NDCG@5 Δ ≥ 0 → **CONFIRM**：可以將預設改做 `"issue"`；
  - 任何一項 < 0 → **STAY_OFF**：維持 `"off"`，顯示照留。
- 冇 CI、冇 Holm：呢個係預先登記嘅「方向唔反」確認，唔係新嘅顯著性檢定。CONFIRM **唔等於已證實改善**。
- **永遠唔自動轉**：CONFIRM 之後要 Kelvin 決定，用 `./保存.sh` 將 `OFFICIAL_INJURY_SCORING` 改做 `"issue"` 發佈。

## 已知限制

- 60 場 ≈ 6 個賽日；每場受影響馬 ~0.5 匹，回放 355 場只有 44 場排序改變。60 場入面預計只有 ~7 場有分別，
  三項「≥ 0」好大機會係 0 = 0 通過。即係 forward 主要防「方向反轉」，唔係證明有用。
- 回放判定器 sanity（舊 375 場、唔係 forward 窗口）：Gold +0.27pp、Good +0.27pp、NDCG +0.0005、排序改變 44 場。
