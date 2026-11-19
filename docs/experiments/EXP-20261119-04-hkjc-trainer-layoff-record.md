# EXP-20261119-04 — HKJC：練馬師長休後紀錄（賽前已知、收縮）入分 REJECT

- **日期**：2026-11-19
- **平台**：HKJC
- **起因**：Kelvin 2026-11-19 覆盤 11-18 R6 通情達理：「練馬師（葉楚航）長休後嘅紀錄唔好，排第 2 唔合理」。
- **假設**：練馬師喺之前季長休（≥90 日）馬嘅入頭三殘差（對現行 live）會延續；將收縮後嘅殘差入分可以改善入頭三 log-loss。
- **搜索過嘅舊記錄**：EXP-20261115-20（19 格練馬師 pattern 標籤，包括葉楚航休息 ≥90 日 −6.9pp n 157；格係用 2020/21–2025/26 全期揀，**唔係賽前已知**）、
  EXP-20261115-17（練馬師收縮分數，整體，dev REJECT）、EXP-20261115-10（通用「上仗熱門休息 ≥90 日」β 逐季 +3.2→−1.9 唔穩，REJECT）、EXP-20261027-12（長休情境 overlay）。
  未有人測過「逐個練馬師嘅長休紀錄、每季只用之前季」。
- **改到嘅檔案／組件**：冇（research only）。腳本 `patches/hkjc_trainer_layoff/build_trainer_layoff.py`。

## 配置
- **baseline**：`v4/cons/base_venue_age.jsonl`（現行 live，含 EXP-20261119-01）。
- **candidate**：長休馬（香港往績上仗距今 ≥90 日）加 β·f；f = 練馬師之前季所有長休馬殘差 Σres／(n + k)；β 逐季 walk-forward；場內置中。
  殘差用 `diag_full.calibrate`（每季只用之前季校準）。L1 k = 50、L2 k = 150（Holm 家族 2）。

## 數據
- 回放 6,047 場；長休馬次（有名次）4,674。dev 2,488 場（2020/21–2023/24）。holdout 冇開。

## 結果
| 候選 | β 逐季（raw／單位 f） | dev Δlog-loss | 好過 null | Gold | Good | 判 |
|---|---|---|---|---|---|---|
| L1 k=50 | 2021 −29.7、2022 −10.5、2023 +4.9、2024 +5.3、2025 +7.4、2026 +13.4 | +0.00003 [−0.00002,+0.00009] | 25% | +0.12 | +0.04 | **REJECT** |
| L2 k=150 | −71.4、−18.2、+14.8、+14.7、+16.9、+28.7 | +0.00004 [−0.00002,+0.00012] | 28% | +0.12 | +0.04 | **REJECT** |

2026/27 季（live）最差長休練馬師 f（L1）：蔡約翰 −4.9pp（n 266）、蘇保羅 −4.6、葉楚航 −4.5（n 189）、徐雨石 −4.5、韋達 −4.4；
葉楚航長休馬 L1 會扣 −0.61 raw、L2 −0.92 raw（通情達理 72.09 → ~71.2–71.5，仍然排第 2）。

## 檢查
- **leakage-audit**：PASS —— f 只用之前季；殘差校準只用之前季；往績日期嚴格早過今仗。
- **golden_scoring**：冇郁（冇改 code）。
- **退步**：log-loss 點估計變差；頭二選有中 −0.08／−0.12。

## 結論
早兩季 β 係**負**（練馬師長休紀錄唔延續，甚至反轉），2023 之後先轉正 —— 即係全期揀出嚟嘅 −6.9pp 格大部分係事後睇到嘅，
賽前已知版本預測唔到下一匹長休馬。維持 EXP-20261115-20 嘅做法：標籤顯示、唔入分。

**決定**：REJECT（L1、L2）
**commit**：未 commit 任何 model code（只有記錄同 research 腳本）。

## 重跑
```bash
O="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/EXP-20261119-04"
B="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/analysis/replay_all/v4/cons/base_venue_age.jsonl"
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_trainer_layoff/build_trainer_layoff.py "$B" "$O/cand"
for a in L1 L2; do PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v4.py "$B" "$O/cand_$a.jsonl" --window dev --null 200; done
```
