# EXP-20261103-09 狀態與穩定性簡化：`stability.py` 唯一計算位置（分數零差）

- **日期**：2026-11-03；**平台**：AU；**baseline**：`cefaa88f`。
- **用戶**：「rebuild 狀態與穩定性 in simplest cleanest code and remove all bugs and dead code」。

## 改動

- 新 `au_racing_engine/stability.py`：近績質素分常數、每場 digest、場內 z、後備組合、增縮程扣分、
  冇代理時重算（forward 用）。引擎只負責攞數據同寫說明。
- 後備組合 `0.6 × 近績分 + 0.4 × 表現質素分` 原本有**三份複本**（engine、`matrix_mapper.with_form_quality`、
  `au_overseas_proxy_forward`），改為全部叫 `stability.composite`；forward 嘅成條重算改叫 `stability.score_without_proxy`。
- 剷：研究開關 `WC_DISABLE_AU_PERFORMANCE_QUALITY`（同佢個測試）、engine 頂嘅 `FORM_QUALITY_*` 常數。

## 零差證明

全語料 `au_dump_engine_leaves.py`：4,105 場、40,216 匹，feature 同 ability **0 匹有差**。

## 路徑實測（`scratch/au_stability_path_scan_20261103.py`，全語料）

| 路徑 | 匹數 |
|---|---|
| 場內 z（主路） | 25,330（63.0%） |
| 後備組合 | 14,794（36.8%；live 10–11 月約 10%） |
| 海外評分代理 | 92 |
| 增縮程 −5 | 2,510 |

- 後備組合入面嘅「表現質素分」live 全部係抄穩定性分（`consistency_fallback`），即係 live 後備 = 0.6 近績 + 0.4 穩定性。
- 表現質素分嘅 Sportsbet 歸檔恢復（α 0.10）只喺舊語料行（7,252 匹），live 10–11 月 0 匹；剷佢會改語料回放，所以保留。
- 兩條「−4」情境扣分（484／1,581 匹）只經後備組合入分 → EXP-20261103-10。
