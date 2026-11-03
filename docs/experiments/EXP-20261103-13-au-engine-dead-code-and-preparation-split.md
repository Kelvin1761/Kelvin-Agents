# EXP-20261103-13 AU 引擎清理：死 code ＋ 試閘備戰直接分開計（分數零差）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`144d5ef6`。
- **用戶**：「rebuilding au wong choi in the simplest code and clean out all bugs and dead code」。

## 盤點（AST 掃全 repo 引用）

引擎 package 12,145 行（`engine_core.py` 7,190）。之前逐維度重建（班次、檔位、場地、騎練、狀態與穩定性）之後，
完全冇人叫嘅 function 只剩 2 個；研究開關剩 1 個（其餘 `WC_*` 係上線實驗嘅即時回退或者路徑／測試注入，保留）。

## 改動

1. **剷死 code**：`_tactical_position_text`、`_merge_if_missing`（0 引用）；`WC_DISABLE_AU_HEALTH_SCORE`（冇任何地方設）。
2. **試閘備戰直接分開計**：舊做法係 `jockey_trainer.fit_parts` 嘅兩項試閘密度（「試閘交代密度足夠」「備戰同騎練配置方向一致」）
   先加入人馬配搭分，`analyze_horse` 之後再減返出嚟、搬去 `preparation_score`、再用 regex 改寫說明入面嘅分數。
   而家人馬配搭分 leaf 一開始就分開兩份：配搭分只計配搭項，`preparation_parts` 交俾試閘備戰分。
   「冇任何證據 → 58」同證據標籤照舊將試閘項算入（行為不變）。

## 零差證明

- 全語料 `au_dump_engine_leaves.py`：4,105 場、40,216 匹，feature 同 ability **0 匹有差**。
- 報告文字（10-20..10-26，2,607 匹）：只有兩類差異，都係舊做法嘅顯示 bug：
  - 27 匹人馬配搭說明舊版係**空字串** —— 只有試閘項時，舊 regex 過濾連「人馬配搭分 X」嗰句一齊刪走；新版正常顯示。
  - 91 匹 `jt_fit_detail.final` 舊版有浮點尾數（61.99999999999999 → 62.0），係「加完再減」嘅副作用。

## 未做（留低嘅理由）

- `trial_score`（唔入排名、唔顯示）仲有 20+ 個研究腳本、golden 同 registry 引用；剷佢係大範圍改動而冇分數得益。
- 速度考驗背景（`pace_figure_score`）已經喺 `speed.py`，引擎淨係砌說明；冇再簡化空間。
