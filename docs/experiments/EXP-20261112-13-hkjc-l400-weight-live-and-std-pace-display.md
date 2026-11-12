# EXP-20261112-13 HKJC 上線：L400 按今仗負磅換算（§7）＋「輸頭馬差距」改名＋對馬會標準只顯示（forward shadow）

- **日期**：2026-11-12 ｜ **平台**：HKJC
- **觸發**：Kelvin：「1. 上線 L400 按路程負磅換算，當正確性修正，連 forward 登記同退回條件。
  2. 修好步速修正偏差嘅顯示：報告改返啱名，另外顯示新數值（對標準、步速修正、負磅換算），唔入排名，登記 forward shadow，夠數先判入唔入分。」
  「L400 按路程負磅換算 also need to be displayed properly」
- **搜索過嘅舊記錄**：EXP-20261112-01 至 -12
- **改到嘅檔案／組件**：
  - `hkjc_racing_engine/past_runs.py`（新）：讀賽績檔逐仗負磅／路程／分段時間 → `_data.formguide_today_weight`、`l400_last_run`、`std_pace`
  - `hkjc_auto_orchestrator.py`：`_formguide_path_for_logic`、`_attach_past_runs`（評分前叫一次）
  - `hkjc_racing_engine/scoring.py`：`L400_WEIGHT_ADJUST`、`L400_WEIGHT_SECONDS_PER_LB`
  - `hkjc_racing_engine/features/speed.py`：L400 門檻用換算後數值；「步速修正等級」顯示改名「輸頭馬差距」；顯示 helper
  - `hkjc_racing_engine/renderer.py`、`tags.py`：報告數據行（L400 負磅換算、輸頭馬差距、對馬會標準（未入分））
  - `Horse_Racing_Dashboard/static_template.html`：認新標題「輸頭馬差距」，L400 換算行唔當走勢串
  - `hkjc_daily_auto/hkjc_forward_tracker.py`：兩個 forward；arm `hkjc_arm_revert_l400_weight.py`、`hkjc_arm_std_pace_shadow.py`

## 1. L400 按今仗負磅換算（入分，§7 正確性修正，**未證實改善**）
- 規則（EXP-20261112-05 原 arm，冇改）：上仗 L400 ＋ 係數 ×（今仗實際負磅 − 上仗實際負磅），先過五級門檻；
  係數按上仗路程 0.007（≤1200m）／0.016（≤1799m）／0.021（≥1800m）秒／磅（EXP-04 同馬比較實測）。
  上仗 L400 要同 Logic `raw_l400` 相差 ≤0.02s 先換算。
- 證據：回放 389 場 Gold 0、Good +0.51pp [0, +1.30]、冇分層為負，`ranking_evidence_too_weak`。物理效應真
  （EXP-06：賽果庫 70,628 匹次每磅 0.0112 s/km）。Kelvin 決定當正確性修正上線。
- **wiring／一致性**：production code 回放 449 場，**picks 449／449 同 EXP-05 arm 一樣、段速分 0 匹唔同**；
  同上線前 baseline 73 場排名唔同（= EXP-05）。
- 顯示：段速分逐項「L400 絕對值（23.64s，上仗 23.27s 按負磅換算 +0.37s）」；數據行
  「L400 負磅換算: 上仗 23.27s（1650m 負 110 磅）；今仗負 133 磅，重 23 磅 × 0.016 秒 ＝ +0.37s；入分用 23.64s」。

## 2. 「步速修正」改名「輸頭馬差距」（純顯示）
`inject_hkjc_fact_anchors.py` V5.1：步速修正偏差 = 原始偏差 − (頭馬時間 − 標準) = 輸頭馬秒數（馬位 × 0.17）。
上游字串唔郁（入分用關鍵字），報告、段速逐項、dashboard 一律顯示「輸頭馬差距」：
「近 3 仗平均 0.55 秒｜輸頭馬中等（0.3–0.8 秒）」；走勢串去咗「+」號。舊報告（「步速修正」）dashboard 照認。

## 3. 對馬會標準（只顯示，唔入分）＋ forward shadow
- 數值（EXP-09 定義）：近 6 仗逐段對馬會標準分段（共同標準 = 今仗班次）→ 對標準；扣步速（ρ = 0.382）→ 扣步速；
  再換算到今仗負磅（0.01123 s/km／磅）→ 再換算今仗負磅。近 6 仗 1/k 加權，最少 2 仗。
- 報告：「對馬會標準（未入分）: 近 6 仗加權：對標準 +0.16s｜扣步速 −0.14s｜再換算今仗負磅 +0.15s（越細越快；未入分，forward 觀察中）」
- **發現**：EXP-09 個表用 Logic `race_class`，有 18% 場次（80／449）係預設「第四班」唔啱；live 改用排位表班次，
  所以 shadow 門檻喺 live 數值上重計（dev 半 2,050 匹，現行四級比例，冇用賽果）：−0.089／0.431／0.927 秒
  （EXP-09 係 −0.155／0.416／0.926）。85% 匹馬數值同 EXP-09 一樣，其餘全部係班次標準唔同。

## Forward（`hkjc_forward_tracker.py`）
| key | 類型 | 最少 | since | 判法 |
|---|---|---|---|---|
| `l400_weight_post_live` | 退回 | 60 場 | 2026-11-13 | 同一批 live 場次 arm 退返舊版；舊版 − live 嘅 Gold／Good／NDCG@5 全部 ≥ 0 → 問 Kelvin 退唔退 |
| `std_pace_shadow` | 入分 | 150 場 | 2026-11-13 | arm 用對馬會標準代替輸頭馬差距入分；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定） |

`std_pace_shadow` 用 150 場：EXP-10 隨機擾動 null 顯示呢個 leaf 任何改動喺細樣本都會跌 Gold，60 場冇得判。
兩個 arm 已經喺 449 場回放跑通（見下）。

## 檢查
- **leakage-audit**：PASS —— 賽績檔往績只用賽日之前；今仗負磅係排位表資料；ρ、β、係數全部喺評估窗之前估或者係物理量度；冇用賠率
- **golden_scoring**：HKJC 120 匹全部一致（golden 由已存 feature 分重算，L400 換算喺上游）
- **data_contract**：`--calibrate` 重建（基準原本已經 stale）
- **測試**：`test_l400_weight_and_std_pace.py` 9 個；HKJC auto 291 全過；forward tracker 16 過；dashboard node 152 過
- **退步**：冇主要指標為負；`REPORT_BANS` 冇觸發

**決定**：KEEP（§7，Kelvin 決定）＋ 顯示改名 ＋ shadow forward 登記
**commit**：見 `./保存.sh` release

## 重跑
```bash
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py; P=docs/experiments/patches
PYTHONDONTWRITEBYTECODE=1 python3 $H run --out live.jsonl                                        # 新 live
PYTHONDONTWRITEBYTECODE=1 python3 $H run --arm $P/hkjc_arm_revert_l400_weight.py --out revert.jsonl  # 舊版
PYTHONDONTWRITEBYTECODE=1 python3 $H run --arm $P/hkjc_arm_std_pace_shadow.py --out shadow.jsonl
python3 $H compare live.jsonl revert.jsonl --stage4 fixed_rule --leakage-audit-passed
```
