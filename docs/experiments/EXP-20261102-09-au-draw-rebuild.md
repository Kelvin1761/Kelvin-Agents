# EXP-20261102-09 檔位重建：draw.py 做唯一檔位計算，剷舊逐場地矩陣（排名零變化）

- **日期**：2026-11-02；**平台**：AU；**類型**：結構／顯示（唔改排名）。
- **用戶**：「do we need to rebuild the code for 檔位 in most simple way like what we did earlier?」→「ok go ahead」。
- **前因**：EXP-20261102-08 將大場次檔位分（`draw.py`，overlay `draw_feature`）以用戶接受嘅實驗性上線入綜合分。
  同時舊「檔位分」`pace_map_score`（逐場地 × 距離檔位勝率矩陣，`race_shape` 係數 None，唔入排名）仲喺報告顯示 ——
  即係報告「檔位形勢」講緊一個唔計分嘅舊數，真正入分嘅檔位喺另一度。

## 改咗乜

| | 之前 | 之後 |
|---|---|---|
| `pace_map_score` | 60 + 逐場地矩陣勝率差（EB 收縮、不對稱封頂、pool 基準、as-of 重砌） | **60 + draw.py 檔位分**（同入綜合分嗰個一樣）；8 匹以下 = 60 並寫明「少過 8 匹，檔位唔計分」 |
| 報告 | 「排 N 檔據場地統計係著數位」 | 「檔位 1：10 匹入面第 1 內（場內 z +1.57）→ 檔位分 +2.24（直接加落綜合分）」 |
| 剷走 | `au_draw_bias_calculator.py`、`au_draw_bias_matrix.json`、`au_draw_bias_races.json`（共約 1MB）、`_load_draw_bias_matrix(_as_of)`、`_draw_pool_baseline`、`_DRAW_MIN_*`、`PACE_MICRO_WEIGHTS`、`_pace_bias_adjustment`（`WC_PACE_BIAS` 預設關、A/B 已判唔過）、`au_draw_walkforward_audit.py`（研究已結案） | |
| 測試 | `test_draw_bias_shrinkage`、`test_draw_rebuild_baseline_guard`、PIT 測試嘅檔位矩陣 case（新檔位只用今場檔位，冇未來資訊可以漏） | 新 `draw.explain` 由 `test_draw_forward` 同 display-scale 測試覆蓋 |

## 驗證

- **全語料重評**（`au_dump_engine_leaves.py`，4,086 場／40,080 匹）對 `5091f008`：`ability`、全部其他欄位 0 差；
  只有 `pace_map_score` 郁（39,975 匹），而且 **40,080 匹全部 = 60 + draw_feature**。
- golden 120 匹一致；AU tests 1,223 passed；實際渲染 2026-11-02 Ballarat 複本：細場次寫明唔計，大場次逐匹「第幾內／z／分」。
- data contract 重新 calibrate（`pace_map_score` 而家 ~30% 中性 = 細場次；全細場次場次只會出稀疏警告，唔會攔發佈）。

## 「加咗檔位要唔要 refit？」

量咗：08-05 起 ≥8 匹 2,709 場，檔位分同「綜合分減檔位」場內 Spearman 中位 **+0.000**（平均 +0.001）；
同 pace_figure +0.000、騎師 +0.000、評分 −0.009。檔位同模型其餘部分完全正交，refit 其他權重唔會因為加咗檔位而改變
（refit 嘅收益嚟自重疊）。而且喺 forward 監察期間改權重會令 EXP-08 結果分唔開係檔位定 refit 嘅功勞。**唔需要，亦唔應該而家做。**
