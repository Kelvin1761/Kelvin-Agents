# EXP-20261016-53 — 最快第一段 K=4 上線（Kelvin 決定，未證實）＋ forward 退回條件

- **日期**：2026-10-16；平台：HKJC
- **性質**：**模型擁有人決定（owner decision）**。唔係 Stage 4 WIN，唔係 §7 正確性修正。

> **呢個冇通過表現閘，唔係一個已證實嘅改善。**
> 預先登記嘅 EXP-20261016-52 判決係 UNRESOLVABLE（Holm 後冇 WIN，全部 |Δ| < MDE）。
> Kelvin 2026-10-16 睇過結果同換馬分析之後決定上線，條件係下面嘅 forward 退回規則。

## 點解 Kelvin 決定上線（證據，唔係判決）

- 機制：被推上頭 2 嘅馬今仗第一沿途位中位 4，被踢出嘅係 8；換入上名 51.6%（31）vs 換出 23.3%（30），
  頭 2 淨多上名 +9 匹 [賽日 bootstrap +3, +15]（探索性，非預先登記指標）。
- 三個 K 嘅 Good 都偏正（+0.70／+1.40／+1.05pp）；冇 cohort CI 全負。
- 資訊同模型正交（ρ +0.07），閘門對呢個幅度冇功效（要 1,100–2,200 場）。
- K=4 係預先登記家族嘅**中位數**，唔係 argmax（argmax 會係 K=6）。

## 改動

- `hkjc_auto_orchestrator.py`：`_first_section_min_delta`（按表頭搵 Δ1，支援 12／14 欄）同
  `_load_first_section_deltas`；`score_race` 將 `first_section_min_delta` 寫入每匹馬 `_data`，
  隨 Logic 寫返落檔（Facts → Logic）。
- `features/speed.py`：`first_section_delta()` 分段；`SpeedScorer.compute` 喺所有返回路徑之後加，唔計 signals
  （同 A/B arm 一樣）。明細顯示「最快第一段」。
- `scoring.SPEED_MICRO_WEIGHTS`：`first_section_fast_bonus` +4（m < −0.3）、`first_section_quick_bonus` +2（−0.3～0）、
  0（0～0.3）、`first_section_slowish_pen` −1（0.3～0.6）、`first_section_slow_pen` −2（≥ 0.6）。m = 近 6 仗最細 Δ1，
  少過 2 仗唔加減。
- 測試：`tests/test_first_section.py`（12／14 欄解析、單仗冇證據、五個分段、冇欄位唔郁分）。

## 接線證明

真 code 經 harness（`--until 2026-10-10`）同 EXP-52 K=4 arm **逐場排名比較**：見下面「接線結果」。

## 預期影響（回放 286 場，K=4 arm 數字）

- 210／286 場排名有郁；Gold −0.35pp [−1.43, +0.71]、Good +1.40pp [−0.33, +3.12]；NDCG −0.0009。
- 每匹有剖面嘅馬段速分 −2 … +4（≈ 綜合分 −0.26 … +0.51）。冇剖面（初出、少過 2 仗）唔變。

## Forward 退回條件（預先登記，唔准改）

- **窗口**：`--since 2026-10-17`（上線後第一個 HKJC 賽日起）。2026-10-11、10-14 唔計（篩選時見過）。
- **比較**：live code vs `docs/experiments/patches/hkjc_arm_no_first_section.py`（四個權重 = 0），同一 harness。
- **判定器**：`docs/experiments/patches/hkjc_first_section_forward.py live.jsonl cf.jsonl`。
  - **< 60 場**：等。
  - **60–149 場（中期止蝕）**：頭 2 換馬淨上名 ≤ −3 → **即刻退回**。
  - **≥ 150 場（最終，只判一次）**：頭 2 換馬淨上名 ≤ 0、或 Good Δ < 0、或 Gold Δ < −1.0pp → **退回**；
    否則保留，但仍然記為「forward 同方向，未證實」。
- **退回做法**：四個 `first_section_*` 權重設 0（Facts → Logic 接線保留做資料），用 `保存.sh` 發佈，記錄寫低數字。
- 唔准換指標、換窗口、重開、或者改 K 救佢。

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
python3 $H run --since 2026-10-17 --out live.jsonl
python3 $H run --since 2026-10-17 --arm docs/experiments/patches/hkjc_arm_no_first_section.py --out cf.jsonl
python3 docs/experiments/patches/hkjc_first_section_forward.py live.jsonl cf.jsonl
```

## 接線結果

- harness `--until 2026-10-10`：真 code vs EXP-52 K=4 arm，351 行**排名 0 場唔同**。
- 端對端（2026-10-14 跑馬地 R6 複本，deploy 關閉）：Logic `_data.first_section_min_delta` 寫入 8／9 匹
  （4 號少過 2 仗有剖面 → 冇證據），報告「速度分」逐項顯示「最快第一段」。

## 2026-10-27 — Kelvin 決定提早退回（owner decision，唔係觸發退回條件）

- 當時 forward：**30 場**（10-19、10-21、10-25），頭2換馬淨上名 **−1**、Good Δ **−3.33pp**（= 1 場）、Gold Δ +0.00pp；
  判定器 `WAIT（未夠 60 場）`，**未觸發**預先登記嘅退回條件。數字係噪音級，唔係「證實有害」。
- 理由：前速由頭到尾都係「未證實」上線；Kelvin 選擇只用證實咗嘅嘢，等 forward 夠數先再上。
- 做法：四個 `first_section_*` 權重設 0（Facts → Logic 接線同「頭段速度」顯示保留）。
- 接線驗證：10-25 沙田 11 場，退回 vs 有前速 → **6 場**排名唔同。⚠️ HKJC 評分 golden 120 匹「全部一致」——
  golden fixture 冇 `first_section_min_delta`，**睇唔到呢個部件**，唔可以當「冇影響」。
- **Forward 照跑，判定規則唔變**（同一判定器、同一窗口由 2026-10-17 起、同一門檻）：
  退回後 live = 冇前速，所以每週改為 `--arm hkjc_arm_with_first_section.py`（4／2／−1／−2）量「有前速」，
  判定器第一個檔 = 有前速、第二個 = 冇前速，方向同之前一樣。
  - ≥150 場判 KEEP → 可以考慮重新上線（再用 `保存.sh`）；REVERT → 唔好重新上線。
