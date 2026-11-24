# EXP-20261124-90 市場尺 m1：模型喺收市價以外有冇額外資訊（標準工具）

- 日期：2026-11-24　平台：AU（工具跨平台，HKJC 未接駁）　類型：評估工具／合約新增（唔郁模型、唔郁排名）
- 起因：Kelvin「做第 1 項：對市場嘅尺」。系統覆核（Claude＋Codex Sol 獨立意見）兩邊都將「把尺量排名，唔量對市場」排第一。
- 工具：`.agents/skills/shared_racing/scripts/market_ruler.py`；測試 `shared_racing/tests/test_market_ruler.py`（12 個）。
- 覆核：Codex Sol（唯讀，medium）搵到 4 點，全部改咗：配對要驗證同一場（馬名／名次／價）、入頭三剔 ≤3 匹、NLL 改穩定寫法＋收斂檢查（目標除以場數後 0 次未收斂）、判決要 ≥30 計分日兼三塊齊。改完結果數字不變。
- 合約：`docs/model-evaluation-contract.md`「市場尺 m1」。**排名尺判 KEEP 嘅規則冇改**。

## 方法
同 EXP-20261124-60 Q1 一樣（Benter 式），改做可重用工具，同埋改用 dump 本身嘅 `sp`（賽果 SP），咁任何 AU dump 都用得，
唔使另外配 BSP CSV：
- 獨贏：條件 logit s = α·log p_m + β·z vs 淨市場；入頭三：logistic，logit q_m（Harville）＋β·z vs 冇 β。
- walk-forward 每 7 日重 fit、頭 20 日唔計分、2026-08-05 起；賽日 bootstrap 2,000。

## 結果

| 測試 | 獨贏 Δll（每場） | 入頭三 | 判 |
|---|---|---|---|
| 現行 live BASE（`au-debut-trainer-20261124/BASE.json`，3,520 場／90 日） | −0.00043 [−0.00159, +0.00078] | −0.00044 [−0.00126, +0.00042] | 冇市場以外資訊 |
| 正對照：頭馬 ability +0.1 SD（配對） | +0.00755 [+0.00365, +0.01151] | — | PASS |
| 正對照：+0.2／0.4／0.7 SD | +0.030／+0.120／+0.348 | — | PASS |
| 負對照：場內洗牌 ability（配對） | +0.00035 [−0.00092, +0.00163] | +0.00022 | FAIL |
| F1 近績 SD 下限（已上線，排名尺 PASS）對 v2-rescreen BASE | −0.00002 [−0.00019, +0.00015] | +0.00019 [−0.00002, +0.00040] | FAIL |
| SPG 對 v2-rescreen BASE | +0.00000 [−0.00004, +0.00004] | +0.00001 [−0.00004, +0.00005] | FAIL |

最後一次 fit 嘅模型係數 β（獨贏）= −0.015，即係加入模型之後 fit 出嚟差唔多係零權重。

## 讀法
- 現行 AU 模型喺 Sportsbet SP 以外**冇可量度嘅資訊**，同 EXP-20261124-60 用 BSP 嘅結論一致（兩個唔同嘅收市價）。
- F1 喺排名尺係真改善，但係市場尺 ΔΔ ≈ 0：佢改善嘅資訊市場已經有。即係「分析改善」，唔係「投注改善」。
  入頭三 ΔΔ +0.00019（CI 下界 −0.00002）係全部候選入面最接近正數嘅，可以留意，但係未過。
- 功效：配對 CI 半寬約 0.0002–0.0004。
- 呢個唔係話排名尺冇用：dashboard 分析靠排名，而 Kelvin 睇排名。只係唔可以再用排名尺結果講「會贏錢」。

## 過程中發現
- `au_betfair_logger.py settle` 11-06 → 11-23 每晚 18 日、約 1.6 萬匹全部 `bsp: null`。記錄器只係打算記錄，冇嘢讀佢，
  所以冇報錯。原因未查實（推測收市後 `listMarketBook` 唔再回 SP）。修好之後市場尺可以加 BSP 版（較 sharp）。
- HKJC 回放語料（jsonl）冇當日最終賠率；要接駁就要先將賽果最終獨贏賠率配入回放 rows。

## 可重現
```bash
export PYTHONDONTWRITEBYTECODE=1
D="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch"
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform au "$D/au-debut-trainer-20261124/BASE.json"
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform au "$D/au-v2-rescreen-20261123/BASE.json" "$D/au-v2-rescreen-20261123/F1.json"
```
