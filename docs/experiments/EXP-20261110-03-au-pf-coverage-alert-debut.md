# EXP-20261110-03 AU PF 覆蓋警報唔再將初出馬當缺數據（診斷修正，排名零差）

- **日期**：2026-11-10；**平台**：AU；**baseline**：`e1789a5d`（origin/main）。
- **類別**：診斷／報告層修正。**唔係模型改動，唔聲稱任何準確度改善。**
- **來由**：全面掃描 AU 時，失手體檢嘅 `pace_figure_alert` 由每週約 13–27 場升到 38–50 場（W43 起）。

## 發現

`renderer._pace_figure_coverage` 將 provenance = `missing_neutral`／`no_spread` 嘅馬全部當「缺 PF」，覆蓋率 < 90% 就出警報。
但初出馬（`career_race_starts == 0`）冇正式往績，PF（L600 環境分）本來就冇得計。10 月中試閘速度搬去試閘備戰
（EXP-20261016-77）之後，初出馬缺 PF 比例由約 50% 變 100%：

| 週 | 初出馬缺 PF | 1–2 仗 | 3+ 仗 |
|---|---:|---:|---:|
| W39–W41 | 47–53% | 1.2–1.9% | 0.2–1.2% |
| W42 | 68% | 1.1% | 0.4% |
| W43–W45 | 100% | 3.8–6.0% | 0.3–1.5% |

所以警報升咗係設計改動嘅副作用，唔係數據壞咗；而佢令失手體檢嘅「輸入有問題」桶虛高。

## 改動

- `_pace_figure_coverage`：初出馬唔入分母（另報 `debut_excluded`）；「夠唔夠證據」門檻改用非初出馬數；
  全場初出 → `status = "all_debut"`（以前會寫成「舊檔未有 provenance」）。
- `career_race_starts` 缺失 = 唔知，**照計**，唔會靜靜收埋真缺失。
- 報告「PF 覆蓋」行加「初出 N 匹唔計」。`01_scoring_contract.md` 同步。
- 警報門檻（90%）冇郁。

## 核對

- 用儲存嘅 Logic 重算（2026-09-07 → 11-09，2,875 場，唔重評分）：

| 週 | 舊警報率 | 新警報率 |
|---|---:|---:|
| W37–W42 | 6.1–12.7% | 1.3–3.4% |
| W43 | 20.6% | 5.4% |
| W44 | 18.8% | 2.5% |
| W45 | 21.4% | 6.8% |

  舊有警報 402 場 → 新 92 場（312 場消失、2 場新增：剔走初出馬之後「夠證據」門檻先過）；`all_debut` 7 場。
- 10-19 起剩低嘅警報集中喺 Port Lincoln（14 場）、Muswellbrook（5）、Armidale（4）、Flemington（4）——
  缺 PF 嘅全部係「無往績賽事 L600 環境數據」，多數係 6+ 仗嘅馬。呢啲先係真覆蓋缺口，**今次冇修**。
- 排名：函數喺排名定咗之後先行，只寫 `python_auto_verdict.pace_figure_coverage`；`./檢查.sh`（golden 評分）通過。
- 測試：`test_confidence_radar.py` 加四條（初出唔計、career 唔知照計、初出旁邊嘅真缺失照警、全場初出標籤）。

## 命令

```bash
python3 -m pytest -q .agents/skills/au_racing/au_wong_choi_auto/tests/test_confidence_radar.py
./檢查.sh
```

## 未做

- 細場地（Port Lincoln 等）L600 環境數據缺口未查原因。
- 歷史 `AU_Miss_Autopsy.jsonl` 冇重寫；W43–W45 嘅 `pace_figure_alert` 數字仍然係舊口徑。
