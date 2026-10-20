# EXP-20261020-02 — 官方傷患記錄頁入馬匹健康分：預先登記

- **登記日期**：2026-10-20，喺跑任何 arm **之前** commit 同 push
- **平台**：HKJC；**Stage 4 v3 `fixed_rule`**（冇 fit）
- **觸發**：Kelvin 2026-10-20 —— 10-21 跑馬地 R5 超強六十（07-16 左前球節關節鏡手術、10-06 先通過檢驗）模型排第 2，
  Logic 寫「✅ 無醫療事故記錄」。查明 `medical_flags` 只掃賽事短評關鍵字（`create_hkjc_logic_skeleton.parse_medical_flags`），
  兩仗之間嘅手術／受傷永遠捉唔到，搵唔到就當清白 +2。賽會「全日出賽馬匹資料」PDF 有一頁官方「傷患記錄」，由來冇讀。
- **事前描述（未判決，唔係證據）**：43 份 PDF、5,204 匹：有記錄馬上名 ÷ 期望 0.82 [0.64, 1.00]；
  控制模型排名後 0.93 [0.72, 1.12]，骨骼／腳＋手術 0.83 [0.55, 1.08]。即係方向偏負但模型已經捉到大部分。

## 接線（兩邊共用）

- parser `hkjc_wong_choi_auto/scripts/hkjc_official_injury.py`：讀「傷患記錄」同「其他傷患記錄」兩節；處理場次沿用、
  後備馬、詳情斷行、同一匹馬多條記錄；去重。
- orchestrator `_load_official_injury_records` → `_data["official_injury_records"]`；live 同 harness 回放都經 `score_race`。
- **淨「表現」覆檢唔計分**：詳情有「表現令人失望／難以接受／欠佳」「試閘時表現」「並無出賽」**而且冇**醫療字眼
  （血、傷、跛、不良於行、手術、心律、絞痛、骨、肌腱、蹄、呼吸、喉、發燒、感染、不適、腫、獸醫）。
- 只影響「賽事短評冇事故（`✅ 無醫療事故記錄`）但有官方醫療記錄」嘅馬；短評已經有事故嘅馬兩邊一樣。
- 顯示（健康解讀、健康維度敘述、報告「賽會傷患記錄」一行）**兩邊都有**，唔入分，另外證明排名 bit-identical。

## Baseline 同候選

- **A0 baseline**：`scoring.OFFICIAL_INJURY_SCORING = "off"`（現行 live 行為）。
- **B1 `issue`**：當作醫療事故 → 行現有 `medical_issue_pen` −12，有康復證據（近 3 仗有前三、步速修正「仍具競爭力／持續快於標準」或
  L400 ≤ 23.4）再 +6。對比 A0 淨變化 −14 或 −8（risk_score leaf）。
- **B2 `no_clear`**：唔再俾 `medical_clear_bonus` +2。淨變化 −2。
- **家族**：B1、B2 兩個 arm；Holm（2 × 6 指標）。B1 係主候選（Kelvin 要求「接入 medical_flags」= 沿用現有醫療事故邏輯）。
- 冇新數值：−12／+6／+2 全部係現有常數，冇因為呢個實驗調。

## 量度

```bash
export PYTHONDONTWRITEBYTECODE=1
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py
P=docs/experiments/patches
python3 $H run --out a0.jsonl
python3 $H run --arm $P/hkjc_arm_official_injury_issue.py --out b1.jsonl
python3 $H run --arm $P/hkjc_arm_official_injury_no_clear.py --out b2.jsonl
python3 $H compare a0.jsonl b1.jsonl --stage4 fixed_rule --leakage-audit-passed
python3 $H compare a0.jsonl b2.jsonl --stage4 fixed_rule --leakage-audit-passed
```

全紀錄（harness 預設剔死日）。冇 PDF 嘅賽日兩邊一模一樣。分層照報：馬匹數 ×4、首選 SP ×5、有受影響馬嘅場次。
接通檢查：先數受影響 runner 數；B1／B2 同 A0 完全一樣 = 冇接通，唔准報「冇效果」。

## §6 功效

閘門 MDE（EXP-20261016-14 同語料 CI 半寬）：Gold ±1.96pp、Good ±1.76pp、NDCG ±0.0101。
受影響馬預計只係每場 ~0.5 匹，而 B2 只係 −2 leaf 分（×0.611×0.0404 ≈ 綜合分 −0.05）—— **預計 B2 冇功效**，照跑做對照。
全部 arm |Δ| < MDE → UNRESOLVABLE。

## Leakage

- PDF 係賽會**賽前**發佈嘅出賽馬匹資料；43 份入面 2 份檔案 mtime 遲過賽日，但內容係固定文件，只列賽前事故。
- 再加 point-in-time 守衛：只收事故日期 < 賽日、通過日期（如有）≤ 賽日。實測 576 條記錄全部符合。
- 只用事故日期、詳情、通過日期；唔用賽果。PASS。

## 判決後

- **B1 WIN（Holm 後）** → 2026-10-21 起 forward ≥ 60 場一次性確認（Gold、Good、NDCG@5 Δ ≥ 0）先將預設改做 `issue`。
- **REJECT** → 維持 `off`；顯示照留。
- 冇 WIN 但冇顯著退步 → 交 Kelvin。

## 結果

見 `EXP-20261020-02-hkjc-official-injury-results.md`。
