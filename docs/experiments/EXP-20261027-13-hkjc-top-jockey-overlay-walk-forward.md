# EXP-20261027-13 — HKJC 頂級騎師 overlay（walk-forward 幅度）＋換騎方向 ablation：預先登記

- **日期**：2026-10-27
- **平台**：HKJC
- **狀態**：**四個 arm 全部 REJECT；overlay registry 交付（全部 shadow，排名 bit-identical）**
- **起因**：EXP-20261027-12 P1「換上頂級騎師」對模型 +5.5pp [+1.7,+9.2]（Holm p 0.025）；事後拆解似係
  「今仗頂級騎師」被低估（up vs none +6.08、stay vs none +3.93），而且引擎「換騎 −1.5」唔分方向。
- **同時交付**：overlay registry（`hkjc_racing_engine/overlays.py`）—— 所有情境 overlay 一個地方定義、
  一個 dict（`OVERLAY_WEIGHTS`）開關，預設 0 = shadow；每匹馬 `python_auto.overlays` 記錄、harness
  `--dump-matrix` 匯出 `o` 欄，refit／ML 可以直接當獨立欄位。shadow 狀態下排名 bit-identical（10-25：11/11）。

## ⚠️ 獨立性聲明（量度前寫）

P1 係喺 2026-04-12 → 10-25 呢段（模型鏡頭 M）發現嘅。今次 walk-forward 用同一段，所以**唔係獨立證據**：
就算 Stage 4 v3 判 WIN，都只係「幅度揀咗、冇傷害」，**唔可以直接上線**。上線要喺 2026-10-28 之後未睇過嘅
賽事做 forward 確認（規則見下）。

## 語料同把尺

- `hkjc_eval_harness.py run --since 2026-04-12 --until 2026-10-25 --dump-matrix`，頭段速度關咗
  （`hkjc_arm_no_first_section.py`，= 2026-10-27 之後嘅 live）。
- Stage 4 v3（`compare --stage4 …`），bootstrap 以賽日做單位。

## Arms（凍結）

| Arm | 改咩 | mode |
|---|---|---|
| A1 | overlay `top_jockey_today`（今仗騎師屬賽日前 365 日勝出頭 6）加 w raw 分 | `walk_forward_oos` |
| A2 | overlay `top_jockey_upgrade`（A1 而且上仗騎師唔係頭 6）加 w raw 分 | `walk_forward_oos` |
| B | `JOCKEY_CHANGE_SKIP_TOP_UPGRADE = True`：換上頭 6 騎師唔扣換騎 −1.5 | `fixed_rule` |
| A1+B | B 開住，再加 A1 walk-forward | `walk_forward_oos` |

Walk-forward（A1／A2／A1+B）：
- 網格 w ∈ {0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0} raw 分（場內 raw SD 中位 3.49；第 3／4 名差距中位 0.72 —— 只睇分數尺度，冇睇賽果）。
- 每個賽日 d 用 **d 之前全部賽日** 揀 w：目標 = Σ(gold + good_positional)；打和揀細嘅 w。
- 頭 10 個賽日係 burn-in（w = 0，同 baseline 一樣）。
- 因為 overlay 係加喺最終 raw 分（排名就係 raw），離線 `raw + w × o` 同引擎計法完全一樣；
  會用一個固定 w 經真引擎 arm 跑一次做忠實度檢查（排名要 100% 一致）。

## 判決（凍結）

1. 忠實度檢查唔過 → 無效。
2. 四個 arm 一個家族，Holm。Stage 4 v3 判 WIN（Holm 後）先算「通過」。
3. A1 同 B 都通過 → 睇 A1+B 有冇再好過 A1（邊際貢獻）；分唔開就只留較簡單嗰個（B 冇參數、優先）。
4. **通過都唔即刻上線**：揀出嚟嘅 w（最後一日 walk-forward 選擇）凍結做 shadow，forward 由 2026-10-28 起：
   - 判定：overlay 開 vs 關，同一 harness；≥ 60 場先睇；**≥ 150 場**一次過判：Good Δ ≥ 0 而且 Gold Δ ≥ −1.0pp
     而且頭2換馬淨上名 > 0 → 可以上線；否則唔上。
   - B（fixed_rule）如果通過 v3：同一 forward 規則。
5. 唔通過 → 記錄數字，overlay 留 shadow（registry 照計照匯出，畀日後 refit／ML 用）。

## 結果

### 可重現

```bash
# baseline（頭段速度關，= 10-27 之後 live；overlay 全部 shadow）同 arm B，兩個都 --dump-matrix
hkjc_eval_harness.py run --since 2026-04-12 --until 2026-10-25 --arm <no_first_section> --dump-matrix --out base.jsonl
hkjc_eval_harness.py run --since 2026-04-12 --until 2026-10-25 --arm <no_first_section + hkjc_arm_jockey_change_direction_aware> --dump-matrix --out b.jsonl
python3 docs/experiments/patches/hkjc_overlay_walk_forward.py base.jsonl --overlay top_jockey_today   --out wf_A1.jsonl
python3 docs/experiments/patches/hkjc_overlay_walk_forward.py base.jsonl --overlay top_jockey_upgrade --out wf_A2.jsonl
python3 docs/experiments/patches/hkjc_overlay_walk_forward.py b.jsonl    --overlay top_jockey_today   --out wf_A1B.jsonl
hkjc_eval_harness.py compare base.jsonl <arm>.jsonl --stage4 <mode> --leakage-audit-passed
```

### 檢查

| 檢查 | 結果 |
|---|---|
| registry 接線（shadow）vs 之前 model.jsonl | 395/395 場排名一樣 ✅ |
| 忠實度：A2 w=1.5 真引擎 vs 離線 `raw + w×o`（10-11 → 10-25） | **50/50** 一樣（23 場排名有郁）✅ |
| overlay 覆蓋（4,948 匹） | top_jockey_today 1,607；top_jockey_upgrade 435 |
| 配對 | 336 場／34 賽日（死欄位同 error 剔走） |

⚠️ upgrade 只得 435 匹，EXP-12 掃描喺同一段有 914：引擎「上仗騎師」讀 Logic 嘅 `jockey_combo_block`，
掃描讀賽果庫逐仗紀錄；兩者對「上仗」定義唔同步，係覆蓋差異，唔影響今次判決（arm 用嘅就係引擎定義）。

### Walk-forward 揀出嚟嘅 w（burn-in 10 日之後，30 日）

| Arm | 每日 w |
|---|---|
| A1 | 30 日全部 0（全期 Σ目標：w=0 153 → w=2.0 143，單調向下） |
| A2 | 0 同 1.5 之間跳（0×7、0.25×7、0.5×1、1.5×15）—— 唔穩定 |
| A1+B | 26 日 0、最後 4 日 0.25 |

### Stage 4 v3（全紀錄，336 場，bootstrap 以賽日）

| Arm | mode | 判決 | Gold Δ | Good位 Δ | 排名改變 |
|---|---|---|---|---|---:|
| A1 | walk_forward_oos | REJECT `ranking_evidence_too_weak` | 0 | 0 | 0 |
| A2 | walk_forward_oos | **REJECT `primary_regression`** | 0.00 [−1.22,+1.17] | **−1.19 [−2.35,−0.29]** p 0.034 | 93 |
| B | fixed_rule | REJECT `primary_regression` | +0.60 [0.00,+1.50] | −0.30 [−1.22,+0.62] | 47 |
| A1+B | walk_forward_oos | REJECT `primary_regression` | +0.60 [0.00,+1.50] | −0.30 [−1.22,+0.62] | 63 |

冇一個過；Holm 唔使做。

### 點解掃描嘅 +5.5pp 落唔到排名

EXP-12 量嘅係「入位率」（每匹馬），而且按三個粗排名組分層；Gold／Good 係「頭四揀中幾多」（每場）。
頂級騎師 1,607 匹入面 49% 已經喺模型頭 4（全部馬只係 32%）、16% 喺 5–6、36% 喺 7+
（騎師分本身係最重要 leaf，剷走 Good −4.35pp，見 EXP-20261019-04）。加分主要係喺頭 4 入面調次序，
或者將 5–6 名推入頭 4 而擠走另一匹 —— 量到嘅結果係擠走嘅唔係更差嘅馬（A2 Good 顯著跌）。
即係又一次「cohort 差距 ≠ 可上線收益」（`au-cohort-gap-is-not-a-gain`）。

### 決定

- 四個 arm 全部唔上線；`OVERLAY_WEIGHTS` 全部 0、`JOCKEY_CHANGE_SKIP_TOP_UPGRADE = False`。
- **overlay registry 保留交付**：所有 overlay 照計、照記錄（`python_auto.overlays`）、照匯出（harness `--dump-matrix` 嘅 `o` 欄），
  shadow 排名 bit-identical。日後 refit／ML 可以直接將 `o` 當獨立欄位；新 overlay 加入 `OVERLAYS` 就自動有同一套記錄同匯出。
- 唔做 forward：冇 arm 過 v3，冇嘢可以 forward 確認。
