# EXP-20261029-30 — HKJC 負磅分輸入：由「實際負磅」改為讓磅官意見：預先登記

- **登記日期**：2026-10-29，喺跑任何 arm **之前** commit
- **平台**：HKJC；Stage 4 v3（`fixed_rule` ＋ §8 兩邊 refit）
- **搜索過嘅舊記錄**：EXP-20260904-03（官方評分混入 `class_score`，9 個 arm，193 場，全 REJECT）、
  EXP-20260904-09（負磅方向調轉，已上線）、EXP-20261010-04（負磅分只計讓磅）、
  EXP-20261010-05（剷 SIP +1：Gold／Good 0.00，判唔到）、EXP-20261018-06（見習減磅扣兩次，§7）、
  EXP-20261019-04（剷走 `weight_score` Good −2.61pp，Holm 後顯著 → leaf 有用）
- **改到嘅組件**：`engine_core._weight_score`、`hkjc_auto_orchestrator._apply_sip_enhancements`

## 問題

09-04 之後，`weight_score` 嘅定義係「讓磅官對匹馬嘅意見」（頂磅＝全場公認最好）。
但實際做法同呢個定義有三處唔一致：

1. **輸入係實際負磅**（已扣見習減磅）。見習減磅係騎師嘅減磅，唔係讓磅官嘅意見。
   10-18 修「扣兩次」時揀咗實際負磅，即係靜靜用返「負磅＝負擔」嘅語義。
2. **負磅只係官方評分嘅代理**，而且有底磅壓縮（低評分嘅馬全部擠喺底磅）。
   官方評分本身喺排位表有（`current_rating`），係直接量。
3. **SIP-C**（`_apply_sip_enhancements`）：原始分 64–68、負磅 ≤ 場內中位數、檔位 ≤ 5 → +1.0。
   前提係「輕磅有利」，但同場比較實測係**相反**（18,828 匹：重過全場 8 磅上名率 29.5% vs
   輕 8 磅 21.8%，單調；EXP-20260904-03）。今季 live 觸發 122／1,822 匹、85 場。

## 功效前置（只數有幾多匹郁，冇睇賽果）

411 場有排位表＋Logic，5,134 匹：

| arm | 郁咗負磅分嘅馬 |
|---|---:|
| A 宣佈負磅 | 389（7.6%） |
| B 評分差距 | 958（18.7%） |

平磅／定磅賽只有 10 場（2.4%），B 直接用評分已經處理，唔另開 arm。

## Arms（三個，一個 family）

| arm | 類別 | 改動 | patch |
|---|---|---|---|
| **A** `weight_declared` | §7 正確性 | 負磅分用**宣佈負磅**（實際＋減磅），門檻不變（≤120 → 54、≥132 → 70、其餘 64） | `patches/hkjc_arm_weight_declared.py` |
| **B** `weight_rating_gap` | 候選（`fixed_rule` ＋ §8） | 負磅分用**場內官方評分差距** gap ＝ 全場最高評分 − 本駒評分：gap ≤ 1 → 70、gap ≥ 13 → 54、其餘 64（等同頂磅 133 時嘅現行門檻）；冇評分 → 用 A | `patches/hkjc_arm_weight_rating_gap.py` |
| **D** `no_sip` | §7 正確性 | 剷走 SIP-C（前提「輕磅有利」同實測相反） | `patches/hkjc_arm_no_sip.py`（EXP-20261010-05 原檔） |

數值全部預先固定，冇 fit。

## 判決規則（跑之前鎖定）

**A、D（§7）**：錯處唔靠績效數字證明（A：見習減磅唔係讓磅官嘅意見；D：前提同 18,828 匹場內
實測相反）。上線條件：Gold／Good 冇顯著負（CI 唔可以全負）、預先聲明嘅 cohort（馬群大細 ×4、
首選 SP ×5）冇一個 CI 全負、leakage PASS。記錄要寫明「冇通過表現閘，唔係已證實嘅改善」。

**B（§8 四個 arm）**：
- A0 ＝ production（main），A1 ＝ B arm，兩者用現行權重 → `compare --stage4 fixed_rule`
- B0 ＝ `hkjc_weight_study.py --arm wf_refit` on A0 dump，B1 ＝ 同一程序 on A1 dump → `walk_forward_oos`
- live guard ＝ B1 vs A0（`walk_forward_oos`）；stale ＝ B0 vs A0（只報告）
- fixed arm 同 refit arm 做 Holm；fixed arm WIN → 用現行權重上線；否則 refit arm WIN 而 live guard
  唔係 `primary_regression`／`ranking_metric_harm` → 連 refit 權重上線；其他一律 REJECT。
- **唔准**因為 B 輸而改門檻、改成連續函數或者換指標再試；嗰啲係新實驗。

**組合**：如果 A、D 都過 §7 而 B REJECT → 上線 A ＋ D。如果 B WIN → B 已經包含 A 嘅 fallback，
上線 B ＋ D。上線前用組合 arm 再跑一次 §7 條件（冇顯著退步）。

**語料**：`hkjc_eval_harness.py run --dump-matrix`，main `b00df3b1`，PIT priors，剔死日。
Sanity：`current` 重排要同 production 0 場唔同。

## 重跑

```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
W=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_weight_study.py
P=docs/experiments/patches
export PYTHONDONTWRITEBYTECODE=1
python3 $H run --dump-matrix --out base.jsonl
python3 $H run --dump-matrix --arm $P/hkjc_arm_weight_declared.py --out a.jsonl
python3 $H run --dump-matrix --arm $P/hkjc_arm_weight_rating_gap.py --out b.jsonl
python3 $H run --arm $P/hkjc_arm_no_sip.py --out d.jsonl
python3 $W base.jsonl --arm wf_refit --out base_wf.jsonl
python3 $W b.jsonl --arm wf_refit --out b_wf.jsonl
python3 $H compare base.jsonl a.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare base.jsonl d.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare base.jsonl b.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare base_wf.jsonl b_wf.jsonl --stage4 walk_forward_oos --leakage-audit-passed
python3 $H compare base.jsonl b_wf.jsonl --stage4 walk_forward_oos --leakage-audit-passed
```

## 洩漏檢查（跑之前）

- 宣佈負磅、見習減磅、官方評分全部嚟自**排位表**（賽前公佈），唔係賽果。PASS。
- 「全場最高評分」只用同場出賽馬嘅賽前評分。PASS。
