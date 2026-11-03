---
name: NBA Wong Choi
description: This skill should be used when the user wants to "analyse NBA", "NBA 過關分析", "NBA Wong Choi", "分析今晚 NBA", "幫我睇 NBA", or needs to run the NBA player-prop banker pipeline (Sportsbet odds + ESPN data -> banker SGM).
version: 4.0.0
---

# NBA Wong Choi — nba_engine（2026-11-03 重寫）

全 Python，冇 LLM、冇 ML、冇 Monte Carlo。數據來源只有 ESPN；賠率同 SGM 報價來自 Sportsbet。

## 點跑

```bash
python3 .agents/skills/nba/nba_orchestrator.py --date 2026-11-05            # 全日
python3 .agents/skills/nba/nba_orchestrator.py --date 2026-11-05 --game BOS_LAL
python3 .agents/skills/nba/nba_orchestrator.py --date 2026-11-05 --status
```

單場（已有 odds + ESPN package）：

```bash
cd .agents/skills/nba && python3 -m nba_engine.run \
  --sportsbet "<dir>/Sportsbet_Odds_BOS_LAL.json" --extractor "<dir>/nba_game_data_BOS_LAL.json" \
  --output "<dir>/Game_BOS_LAL_Full_Analysis.md"
```

排程（launchd，悉尼時間）：19:00 warmup、21:00／21:45 正式發佈、06:30–13:00 賽前刷新、18:30／21:30 賽後。
詳見 `nba_daily_auto/README.md`。

## 流程

1. `claw_sportsbet_odds.py` → `Sportsbet_Odds_<tag>.json`（milestone 線、SGM 報價 ID）
2. `nba_extractor.py` → `nba_game_data_<tag>.json`（ESPN 賽績、季度 log、對手表、傷停、陣容）
3. `nba_engine/run.py` → `Game_<tag>_Full_Analysis.md` + `.market_legs.json`
4. `nba_engine/publish.py`（經 `validate_nba_output.py`）→ 過唔到就唔發佈
5. `generate_nba_sgm_reports.py` → `NBA_Banker_Report.txt`、`NBA_All_SGM_Report.txt`

## 模型（`nba_engine/config.json`）

- **p_final = MS** = `a_stat + 0.926·logit(1/價) + 0.110·logit(S)`；S 計唔到就用 C
- **S**：預計分鐘 × 每分鐘產出 × 對手因子，NB 分佈；上季比賽季初降權
- **C**：`a_stat + 0.755·logit(1/價) + 0.140·logit(L10 命中率)`
- 證據：EXP-20261103-15（唔睇價嘅 S 單獨用會輸市場，所以只做修正項）

## 正式穩膽（`nba_engine/banker.py`）

steady B2：L10／L5 命中 ≥80%、價 ≥1.20、CoV ≤0.65、L3 ≥ 線、L10 平均 ≥ 線×1.15、唔係後備／DTD／季初旗標；
砌唔到就用 70% fallback。2–4 腿，單腿價乘積目標 2.0–3.5（fallback 4.0）。**真 SGM 報價 ≥2.0 先出注**，
固定 $1，模型預期 EV 為負（命中率產品線）；累計 −10u 自動暫停（`nba_steady_policy.py`）。季前賽一律 NO BET。

## 改模型之前

改 `config.json` 或 `banker.py` = 改模型 → 先跑 `model-regression-gate`，用
`docs/experiments/patches/nba_rebuild/evaluate.py` 同一把尺量。
