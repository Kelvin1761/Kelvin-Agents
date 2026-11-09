# EXP-20261109-01 HKJC 引擎重建：結構重整、死碼清理、白話重點

- **日期**：2026-11-09
- **平台**：HKJC
- **假設**：引擎可以拆細、剷走死碼同過渡 shim，而排名同 Gold／Good／首選唔變；文字分析可以改由「對總分嘅影響」講原因。
- **搜索過嘅舊記錄**：EXP-20261029-21（clean-room logit REJECT，所以呢次唔換模型）、EXP-20261019-02/03/04（外層權重、內部份額、逐 leaf 移除全部 REJECT，所以唔 refit）、EXP-20261018-05/06/08（舊標籤 §7 修正）、EXP-20261029-02（晨操退出排名）
- **改到嘅檔案／組件**：`hkjc_wong_choi_auto/scripts/hkjc_racing_engine/*`、`hkjc_auto_orchestrator.py`、`hkjc_daily_auto/hkjc_win_tracking.py`、`Horse_Racing_Dashboard`（parser／model／template）、`shared_racing/scripts/golden_scoring.py`
- **審計報告**：[`docs/audits/hkjc-rebuild-20261109.md`](../audits/hkjc-rebuild-20261109.md)

## 配置
- **baseline**：`06c976aa`（origin/main，2026-11-09）
- **candidate**：branch `claude-hkjc-rebuild-20261109`，6 個 commit（見下）

## 數據
- **語料**：`HK_Racing` 全部有 Logic＋賽果嘅場次，2026-04-12 → 2026-11-08，441 場
- **方法**：`docs/experiments/patches/hkjc_rebuild/replay.py` 用真 orchestrator `score_race` 逐場評分（唔寫檔、唔上網），逐欄比對每匹馬嘅 `python_auto`、verdict、shadow verdict、Markdown 同 CSV。兩個模式：PIT（`pit_backtest.inject_as_of`，最接近 production）同 no-PIT。
- **重現**：`PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_rebuild/replay.py dump --out X.jsonl [--no-pit] --shadow <list>`，再 `replay.py diff A B --text-lines`

## 結果（逐步）

| 步驟 | commit | 排名 | 其他輸出 |
|---|---|---|---|
| 拆 god class 做 4 個 mixin、features 改 package import、剷 7 個 shadow／HV 回退開關 | `0751b10c` | 441/441 零差（拆分）；剷 shadow 後 434/434 排名同分數零差 | 只少咗剷走嘅 shadow、`legacy_score`、Markdown 4 行 Consistency Shadow、CSV 4 個空欄 |
| 合成公式直寫（剷三個 shim） | `d56bfc6f` | PIT：7 場相鄰兩匹打和對調，冇一場喺頭三；no-PIT：2 場，頭二變 1 場 | Gold 62／Good 104／首選頭馬 109 不變；原始分最大漂移 0.01（2 位小數捨入） |
| 退出馬唔再令成場拒評 | `96a89ed0` | 原本評到嘅 434 場零差 | 多咗 6 場評到（7 場入面），1 場仍然拒評（排位表有、Logic 冇） |
| 剷恒等／死 method、改名、刪 19 個冇入口嘅 script | `2a3b7fce` | 434/434 零差 | — |
| 白話重點（summary.py）＋顯示修正 | `5b2962b6` | 純顯示，排名唔郁 | Markdown 多「📝 重點」「📝 全場重點」；dashboard chips 加原因同「👀 留意」 |
| 頭馬追蹤（每週 review） | — | 唔郁模型 | 首選 vs 熱門頭馬率／上名率，由 2026-11-11 起 forward |

### 首選 vs 收市熱門（PIT 回放 434 場，供 win focus 決定）
| 指標 | 模型首選 | 市場熱門 | 差（95% CI） |
|---|---|---|---|
| 頭馬率 | 25.1% | 28.1% | −3.0pp [−7.6, +1.2] |
| 上名率 | 52.3% | 60.1% | −7.8pp [−13.1, −2.3] |
| Good | 24.0% | 28.1% | −4.2pp [−9.4, +1.2] |

首選同熱門分差：≥3 分嘅場首選上名 58%（199 場），<3 分 48%（232 場）。分期：上季（4–7 月）首選上名 55.0%（262 場）→ 今季 10 月起 48.7%（119 場）。真實賽前快照 10 月起 98 場：首選上名 42.9% vs 熱門 59.2%；PIT 回放同快照嘅首選 92/99 場一樣。

## 判決
**結構重建，已驗證等價（rank-neutral）**；唔聲稱任何改善。合成公式直寫嗰步有 7 場打和次序對調，Gold／Good／首選不變。白話重點係純顯示。Win focus：主 KPI 維持 Good，只加追蹤。

## 學到嘅嘢
- HKJC golden 一直冇抽 `derived_feature_scores`，靠 `race_shape→draw_score` fallback 頂住，量緊一個唔存在嘅模型；而家已經包埋 derived leaf。golden 仍然唔計同程（centred）同全場步驟，所以真正嘅等價證據係 replay.py，唔係 golden。
- 「最強一環」用原始尺排會永遠揀中位數高嘅維度（賽績線中位 80）；講原因一定要用 impact（權重 ×（原始 − 典型））。
- 舊 `engine_core` 將 `features/` 插上 `sys.path`，令同一個 class 有兩個身份（test_first_section 要特登用 `engine_core.SpeedScorer`）；改 package import 之後只有一個。
