# EXP-20261103-03 AU 濕地 overlay：截斷紀錄唔再當「0 上名」（USER-ACCEPTED）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`301a9189`（EXP-20261103-02 簡化，逐匹同 `ae49f30a` 一樣）。
- **用戶**：「i think the main aim is to have the wong choi reflects true ability of a horse. so i prefer fix.」
- **⚠️ 呢個冇通過表現閘，唔係一個已證實嘅改善。** 係用戶以「反映真實能力」為理由接受嘅數據正確性改動。

## 錯處（唔靠績效數字證明）

2026-08 嘅 Sportsbet 舊 Facts 有一批紀錄**截斷**：`going_stats_line = "12: | 軟地: 7: | 重地: 3:"`，同一匹馬
`career_record_line = "22"` —— 全部只有出賽數，冇贏／亞／季。即係**上名數唔知**，唔係零。

- 場地分（`parse_record_line`）一直當「冇紀錄」。
- 濕地 overlay（舊 `_parse_going_segment`）當「7 戰 0 上名」→ 收縮率跌向 0 → 最多 −5 分。

同一個字串兩個讀法，overlay 嗰個係錯：佢罰緊「濕地經驗多」嘅馬，而唔係「濕地跑得差」嘅馬。

## 改動

`track_going._wet_buckets`：`complete` 為 False 嘅紀錄當冇紀錄（同場地分一樣）。只有濕地日、只影響截斷紀錄。

## 量度（v3 fixed_rule，08-05 起 3,302 場，賽日 bootstrap 2000、seed 7）

影響：2,176 匹有截斷紀錄，其中 1,267 匹喺濕地日 overlay 由負變 0；130 場分數郁、99 場次序變、23 場頭 4 變。
**全部喺 2026-08**；2026-09 起 live 冇截斷紀錄，所以今日之後嘅預測完全唔郁。

| 指標 | Δ | 95% CI |
|---|---|---|
| Gold | −0.061pp | [−0.154, 0.000] |
| good_positional | **−0.121pp（約 4 場）** | [−0.251, −0.029] |
| top3_capture_at5 | −0.071 | [−0.201, +0.011] |
| ndcg_at5 | −0.067 | [−0.191, +0.008] |
| top5_pairwise_auc | −0.070 | [−0.181, +0.005] |

判決 `REJECT / primary_regression`；§7「零顯著退步」唔過（good_positional CI 全負）。預先聲明分層冇 CI 全負。

點解錯嘅規則反而「幫手」：截斷場次（鄉郊、整個場次一齊截斷）入面，罰則同濕地出賽數成正比，即係變相
扣「出賽多、老馬」—— 呢個係一個偶然有用嘅代理，唔係濕地能力。

## 決定

**USER-ACCEPTED，上線。** 理由係旺財應該反映真實能力，唔應該靠一個讀錯數據嘅副作用。
退回：revert 呢個 commit（一行）。

## 可重現

    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out fix.json
    python3 scratch/au_track_simplify_judge_20261103.py base.json fix.json judge.json

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/track-simplify/`（`base2.json` = `ae49f30a`、`fix.json`）。
