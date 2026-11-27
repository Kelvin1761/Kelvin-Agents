# EXP-20261127-33 結果：AU 排名權重 walk-forward refit —— v3 REJECT，但同市場差距顯著收窄

- **日期**：2026-11-27 ・ **平台**：AU ・ **登記**：[EXP-20261127-33 protocol](EXP-20261127-33-au-weight-walkforward-protocol.md)（commit `b1e70718`，結果出現之前）
- **決定**：**REJECT（`primary_regression`）**，冇改 live 權重。新工具 `au_weight_walkforward.py` 保留（合約 §8 講嘅「AU walk-forward refit 預測產生器」）。
- **分工**：Terra 寫工具、跑判決同市場尺；Sol 覆核工具（冇時間洩漏）；Claude 判決。
- **證據**：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/followups-20261127/evidence/au-wf/`（`REPORT.md`、`verdict.json`、`windows.json`、`market-sp.json`、`market-bsp.json`）。

## 樣本

leaves dump 5,102 場 → 剔 2026-08-05 前 803 場 → 乾淨段 4,299 場／113 賽日 → 頭 20 賽日唔計分 → **3,581 場／93 賽日全部樣本外**。
兩 arm sample SHA256 相同（`9270ee21…`）。14 段 refit 全部有候選過閘（10–35 條），冇 fallback。

各段共識權重好穩定：pace_perf 0.155–0.198（現行 0.144）、jockey_trainer 0.86–1.02（0.842）、class_weight 0.28–0.36（0.376）、track 0.048–0.098（0.096）。

## 排名尺（v3 `evaluate_full_record`，`walk_forward_oos`，賽日 bootstrap 2,000，K = 6）

| 指標 | Δ | 95% CI | 時間塊 ≥ 0 |
|---|---:|---|---|
| Gold | +0.14pp | [−0.40, +0.64] | 4/6 |
| Good 位置 | **+0.00pp** | [−0.51, +0.50] | **3/6**（要 4） |
| top3_capture@5 | +0.21pp | [−0.05, +0.49] | 5/6 |
| NDCG@5 | +0.24pp | **[+0.005, +0.49]** | 5/6 |
| top5_pairwise_auc | +0.09pp | [−0.08, +0.27] | — |

**判決：REJECT / `primary_regression`**：Good 時間塊只有 3/6 唔負（頭三塊 −1.24、−0.32、−0.69pp，後三塊 +0.32、+0.82、+0.76pp）。
正式輸出寫 `leakage_audit_failed`，因為 CLI 冇傳 audit 旗；呢個候選只係重新加權現有維度、冇新特徵，leakage N/A。假設 audit 通過，判決仍然係 `primary_regression`。

## 市場尺（m3，正 gap = 市場較準）

| 價 | baseline 同市場差距 | candidate | **差距變化** | 95% CI | 市場尺 B |
|---|---:|---:|---:|---|---|
| SP（2,902 場／73 日） | +0.2227 | +0.2200 | **−0.0027** | **[−0.0043, −0.0011]** | FAIL |
| BSP（2,914 場／73 日） | +0.2393 | +0.2366 | **−0.0027** | **[−0.0043, −0.0011]** | FAIL |

**新權重明顯追近市場**（CI 完全喺零下面，SP、BSP 一致），但都未至於贏市場（B FAIL）。

## 判讀

- 按登記規則（KEEP 要排名尺 PASS **而且**差距唔變大），排名尺唔過 → **REJECT**，唔准用市場尺救。
- 但有一個實在嘅發現：「pace_perf↑、騎練↑、級數↓」呢個方向令模型機率更似市場（每場 nll 差距細 0.0027），而 Gold／Good 冇跌。
  Good 嘅時間塊前負後正，即係**最近兩個月**新權重好啲。呢個係睇完先見到嘅形狀，唔可以當證據。
- 同 [EXP-20261127-30](EXP-20261127-30-au-reeval-weights-and-draw-ladder.md) 工具版 walk-forward（Gold +0.25、Good −0.12）方向一致。

## 工具同覆核

- `au_weight_walkforward.py`＋`tests/test_au_weight_walkforward.py`（2 passed：時間洩漏守衛同 fallback、A/A REJECT）。
- Sol 覆核：**冇時間洩漏**（訓練嚴格早過預測日、同日整批、頭 20 日唔計分、每 7 日重 fit）。三點中等：
  (1) 合成分用 `exact_score` 捨入，同 `Dataset.ability` 差 0.0001，可能改同分次序。兩個 arm 用同一個函數，所以對比公平，但同 live 分數唔逐位一致；
  (2) 測試應補「同日多場」同真 fit 抽測；(3) baseline 跟 import 時嘅 `MATRIX_WEIGHTS`，應該鎖住 `c0e47dc2` 係數。以上列入改善空間，未修。
- `./檢查.sh` 完整版喺 Codex 沙盒入面 exit 1：NBA reflector 呼叫 `ps` 被沙盒拒絕、shared 組超時中斷、Agent scripts 兩項。全部同呢個改動無關，`--quick` 全綠。

## 改善空間

1. Good 前負後正：等多 6–8 星期新賽日，**照同一份登記**（工具＋設定不變）再判一次。要開新 EXP，唔係改今次判決。
2. 修 Sol 三點。
3. 判決器 CLI 加 `--leakage-audit-passed` 時要附 audit 記錄路徑，唔好淨係一個旗。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1
S=.agents/skills/au_racing/au_wong_choi_auto/scripts
python3 $S/au_dump_engine_leaves.py --out leaves.json        # 再按 date >= 2026-08-05 篩出 leaves-clean.json
python3 $S/au_weight_walkforward.py --data leaves-clean.json --out-dir out
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform au out/baseline.json out/candidate.json --price sp  --out out/market-sp.json
python3 .agents/skills/shared_racing/scripts/market_ruler.py --platform au out/baseline.json out/candidate.json --price bsp --out out/market-bsp.json
```
