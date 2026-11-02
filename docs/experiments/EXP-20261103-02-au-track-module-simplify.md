# EXP-20261103-02 AU 場地與地況適性：簡化 code（逐匹分數不變）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`origin/main` `ae49f30a`。
- **用戶**：「i mean simplest code, like what we did for other dimension earlier and cleaning the bugs and dead code」。
- **性質**：重構。**唔係改善，冇過表現閘嘅需要** —— 逐匹分數同 baseline 一模一樣。

## 改咗乜

`track_going.py` 變成場地分＋濕地 overlay 嘅唯一計算位置，入面只有一個紀錄 parser（`record`／`records`）。

| 剷走／合併 | 點解 |
|---|---|
| `TRACK_MICRO_WEIGHTS`（scoring.py）→ `track_going.WEIGHTS` | 常數同計法放埋一齊（同 `draw.py` 一樣）；`au_runtime_micro_ablation` 照樣逐 key 消融 |
| `going_poor_pen1_dry` −3.46、`going_poor_pen2_dry` −3.0 | **由來冇觸發過**：好地 bucket 永遠冇紀錄（Facts 第一段冇「好地:」標籤，38,191 匹 0 匹有），所以乾地扣分係死 code |
| `_same_track_stats`／`_going_stats`／`_parse_going_stats`（engine_core） | 換成 `_track_records()` 一個入口 |
| `_track_score` 入面再用 regex 讀一次紀錄嚟顯示 | 改為用同一份 `records` |
| `scoring._parse_going_segment`／`_parse_wet_record` | 濕地 overlay 改用同一個 parser；`scoring.wet_form_feature` 保留做舊入口（lazy import） |

另外修正一句報告：場地分啱啱 60、冇任何同場／今日地況往績嘅馬，以前會寫「場地適應有基礎，應付到今日地狀」，
而家寫「冇同場／今日地況往績，場地分維持中性」。純文字，唔入分。

## 驗證：逐匹一樣

`au_dump_engine_leaves.py` 全語料（4,105 場、40,216 匹），baseline（乾淨 `origin/main` worktree）對 candidate：
**全部 feature、overlay、ability 零差異**。baseline 自己跑兩次亦零差異（確定性）。golden 120 匹一致；AU 單元測試 1,243 個全過。

## 搵到但冇喺呢度改嘅嘢（改咗就會郁排名）

1. **截斷紀錄兩個 parser 讀法唔同**（2026-08 Sportsbet 舊 Facts，例如 `12: | 軟地: 7: | 重地: 3:`，連生涯都只係 `22`，
   冇贏亞季）。場地分當「冇紀錄」，濕地 overlay 卻當「7 戰 0 上名」→ 最多 −5 分。只影響 2026-08（2,176 匹，
   1,267 匹 overlay 唔同），2026-09 起 live 冇截斷紀錄。改正（兩邊都當冇紀錄）喺 3,302 場 v3：
   Gold −0.06pp [−0.15, 0.00]、**good_positional −0.12pp [−0.25, −0.03]**、排序指標 CI 跨零、分層冇 CI 全負
   → 過唔到 §7「零顯著退步」。依家 `record()` 加咗 `complete` 旗，保留舊讀法，等另一個 commit 處理。
2. **「同場同程: 1:」字串比對入分**：`_repeatability_brief` 喺 `track_record_line` 搵字串 `同場同程: 1:`，
   只認啱啱 1 戰（2 戰以上反而冇），唔理有冇上名，而佢會俾跑法穩定性 +2（「重複交代獎勵」）。
   試過改正，consistency 有 2,264 匹郁、156 場次序變 —— 係模型改動，未評估，冇改。

## 可重現

    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py --out <base|new>.json
    # 比較：每匹 features／wet／proven_class／full_time／draw／ability 差 > 1e-9 即報
    python3 scratch/au_track_simplify_judge_20261103.py BASE.json CAND.json OUT.json   # §7 判決（截斷紀錄改正）

Dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/track-simplify/`。
