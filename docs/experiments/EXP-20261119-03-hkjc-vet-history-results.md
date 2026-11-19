# EXP-20261119-03 — HKJC 歷史傷患紀錄入分：結果 —— 三個 arm 全 REJECT；冇證據受傷馬（復出後）被高估

- **日期**：2026-11-20｜**平台**：HKJC｜**協議**：[EXP-20261119-03-hkjc-vet-history-protocol.md](EXP-20261119-03-hkjc-vet-history-protocol.md)（數據到之前寫、推咗 de38d104）
- **起因**：Kelvin 2026-11-19（11-18 R6 通情達理：一仗、韌帶受傷、休 220 日，排第 2）「查 HKJC 馬匹頁有冇歷史傷患紀錄，補落回放」。

## 數據
- `backfill_history.py run --kinds vet`：2,060 匹（2024-09 後有出賽）→ **現役 999（1,348 條紀錄、648 匹有紀錄）、退役 1,060（冇頁）**、1 頁解析失敗（退役轉頁）。
- 解析修正（同日）：現役冇紀錄嘅頁冇 `oveHorse_details` div（淨係 CSS 提到）→ 以前 351 頁當咗「解析失敗」，而家 = 0 條；退役轉頁有 CSS 都當退役。加兩個測試。
- 覆蓋率（有傷患頁嘅馬次）：2024/25 38%、2025/26 67%、2026/27 94%。

## 殘差（入頭三 − live 校準 p；只計有頁嘅馬）
| arm | 馬次 | 2024/25 | 2025/26 | 2026/27 |
|---|---|---|---|---|
| I1 365 日內嚴重傷患 | 1,637 | +7.2pp（n 444） | +1.2（n 890） | **−1.2**（n 303） |
| I2 365 日內任何醫療 | 2,797 | +6.1 | +1.6 | +0.9 |
| I3 嚴重傷患後第一仗 | 268 | +10.7（n 72） | −0.4（n 137） | +0.1（n 59） |
覆蓋越低（越多受傷後退役嘅馬唔喺度）正偏差越大 = 協議預先講嘅存活偏差；覆蓋 94% 嘅 2026/27 三個都 ≈ 0。

## 判決（`hkjc_replay_compare_v4.py`；β walk-forward：2024/25 fit → 2025/26，2024–25 fit → 2026/27）
| arm | β 2025／2026 | holdout Δlog-loss | terminal Δlog-loss（186 場） | 判 |
|---|---|---|---|---|
| I1 | +2.96／+1.55 | +0.00015 [−0.00023,+0.00054] | +0.00062 [−0.00036,+0.00162] | REJECT |
| I2 | +2.57／+1.54 | −0.00000 [−0.00048,+0.00049] | +0.00001 | REJECT |
| I3 | +4.08／+1.77 | +0.00012 [−0.00012,+0.00037] | +0.00004 | REJECT |
（候選檔只改 2024 之後；2024 之前場次用 base 補返，兩邊一樣，畀校準用。）

## 結論
- 傷患紀錄（類型、近期、傷後第一仗）喺模型之上**冇負面訊號**；β 正係存活偏差，唔係「受傷加分」。三個 arm 全 REJECT。
- 通情達理排第 2 唔係因為模型漏咗傷患：受過傷而仲出賽嘅馬（已經通過獸醫檢驗）整體冇跑差過預估。佢嘅問題係證據薄（EXP-20261119-05 收窄已實驗性上線）。
- **B1 forward（EXP-20261020-02，−12 健康分）**：73 場 CONFIRM 但 Δ 全 0；今次歷史數據亦冇負效應 → 建議維持 off（Kelvin 決定）。
- 傷患詳情照舊喺報告／dashboard 顯示（未入分）。

## 重跑
```bash
python3 .agents/skills/hkjc_racing/hkjc_race_extractor/scripts/backfill_history.py parse-vet
O="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/EXP-20261119-03"
B="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/replay_all/v4/cons/base_venue_age.jsonl"
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_vet_history/build_vet.py "$B" "$O/cand"
# 合併：2024 前場次用 base（見 session），之後
for w in holdout terminal; do for a in I1 I2 I3; do python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v4.py "$B" "$O/full_$a.jsonl" --window $w --null 200; done; done
```
