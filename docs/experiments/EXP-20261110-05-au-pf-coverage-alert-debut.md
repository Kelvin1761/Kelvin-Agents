# EXP-20261110-05 AU PF 覆蓋警報唔再將初出馬當缺數據（診斷修正，排名零差）

- **日期**：2026-11-10；**平台**：AU；**baseline**：`e1789a5d`（origin/main）。
- **編號**：第一次發佈（`51cd15eb`）用咗 `EXP-20261110-03`，同 tennis 一份記錄撞號；code 註解仲寫錯做 -02。全部改為 -05。
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

## 跟進（同日）

### 細場地 L600 缺口：來源本身冇，唔係管線問題

用 11-02 之後抽嘅 Formguide（`RaceL600:` 原始秒數由 11-01 起先有寫）數去重後嘅往績賽事：

- 13,451 場往績賽事：有原始 L600 87.4%、有 `L600 Delta` 87.3%。
- **有原始秒數但計唔到 delta（標準表缺口）只有 20 場（0.2%）** → 標準表唔係問題。
- 冇原始秒數嘅集中喺 18 個場地（共 547 場）：Port Lincoln 96/100、Mount Gambier 71/72、Port Augusta 47/47、
  Moree 40/40、Armidale 38/38、Naracoorte 35/35、Oakbank、Wellington、Bordertown、Penola、Goondiwindi、Richmond、
  Clare、Gladstone、Deniliquin，同海外（Ellerslie、Curragh、Leopardstown）。
- 睇 cache 入面嘅 Sportsbet 原始頁：Port Lincoln 10-25 R7、10-04 R3 有 `Winning Time`、走位、頭三名，
  **但成段冇 `Sectionals 600m`**；同一頁 Balaklava／Morphettville 嘅往績就有。即係 Sportsbet 冇公佈，唔係 regex 漏。

結論：呢啲場地嘅馬 L600 環境分中性 60 係啱嘅處理；要補就要新來源，唔喺今次範圍。警報照出係應該嘅。

### 失手體檢歷史重寫

- `miss_autopsy._current_pf_coverage`：舊 Logic（儲存嘅覆蓋冇 `debut_excluded`）用現行規則由同一份賽前快照重算；
  新 Logic 照用儲存值；HKJC 唔郁。規則只有一份（`renderer._pace_figure_coverage`）。
- **順手修咗一個 crash**：快照過咗 14 日搬咗去外置碟之後，`analysis_dir.relative_to(meeting_dir)` 拋 ValueError ——
  358 個場次有 260 個重跑唔到。每晚排程只跑新場次所以一直冇人見到。
- 唔寫入先比對全部 358 個場次（1,888 場失手）：199 場 `pace_figure_alert` 消失
  （48 場轉「模型判錯」、9 場轉「分數擠迫」、142 場因其他規則留喺「輸入有問題」）；2 場新增警報；
  其餘 4 場嘅差異係賽果後來修正過（`unscored_placegetter`），同今次無關，**嗰 4 個場次冇重寫**。
- 發佈之後用已發佈嘅 code 重寫 ledger；舊 ledger 備份喺資料根 `AU_Miss_Autopsy.jsonl.bak_20261110`。

## 未做

- 冇 600m 段速嘅場地冇替代來源。
- 4 個賽果後來修正過嘅場次（09-10 Warwick、09-12 Doomben、10-03 Flemington、10-03 Randwick）ledger 冇重寫。
