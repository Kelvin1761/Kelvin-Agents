# EXP-20261113-09 HKJC 引擎 A/B：歷史標準前段／全程對標準入段速維度

- **日期**：2026-11-13 ｜ **平台**：HKJC ｜ **決定**：**REJECT（三個 arm，fixed_rule）**；同隨機 null 分唔開
- **觸發**：EXP-20261113-08 概念 PASS（5,206 場）；Kelvin：「做引擎 A/B 先」
- **搜索過嘅舊記錄**：EXP-20261113-04／-05／-07、EXP-20261113-08
- **改到嘅檔案／組件**：冇 live 改動；`patches/hkjc_arm_hist_sectional.py`

## 方法（預先登記，寫喺腳本 docstring）
- 值：EXP-08 嘅 `first_v`（前段對 6 季 PIT 標準、扣當日快慢）同 `total_v`（全程），經分段頁 (日期, 場地, 場次, 馬號) → 烙號接入引擎語料；
  覆蓋 4,959／5,598 匹（88.6%）
- 標準化：mean／SD 只用引擎語料**之前**（< 2026-04-01）嘅歷史行 —— 評估場次冇學任何嘢
- 組件：`speed' = clip(speed + b × 9.45 × clip(z, ±2.5))`，MATRIX_WEIGHTS 唔郁（段速份量上升，冇維度被減）
- arm：主 FT = (z_first + z_total)/2，b = 0.5；副 F、T（b = 0.5），全報
- 計分：離線 `raw + 0.1285 × Δspeed` 重排（引擎 picks = raw 排序，EXP-05 已核對）；`compare --stage4 fixed_rule`（389 場）
- null：同一組 z 場內洗牌 200 次（同幅度、冇資訊）

## 結果（389 場，候選 − 現行，pp [95% CI]）
| arm | 郁咗 | Gold | Good | capture@5 | 競爭 recall@5 | 頭二選有中 | 判決 |
|---|---|---|---|---|---|---|---|
| **FT（主）** | 314 | −1.29 [−3.13,+0.26] | −1.03 [−3.08,+1.02] | **+1.03 [+0.09,+1.91]** | **+0.85 [+0.21,+1.49]** | −0.77 | REJECT |
| F | 343 | −1.54 [−3.99,+0.78] | −2.31 [−4.18,−0.51] | **+1.63 [+0.69,+2.62]** | **+0.90 [+0.22,+1.56]** | +1.80 [−0.50,+4.23] | REJECT |
| T | 309 | −1.29 [−2.47,−0.26] | −1.54 [−3.44,+0.26] | +0.77 | +0.53 | −0.26 | REJECT |

頭三平均模型名次三個都改善（−0.04 至 −0.05，CI 全負 = 好）。

**對 null**（場內洗牌，200 次）：
| arm | Gold（候選／null 均值／null 低過候選） | Good | capture@5 | 頭二 |
|---|---|---|---|---|
| FT | −1.29／−1.33／43% | −1.03／−1.75／75% | +1.03／+0.49／92% | −0.77／+0.52／7% |
| F | −1.54／−1.44／38% | −2.31／−2.16／40% | +1.63／+0.67／**97.5%** | +1.80／+0.38／88% |
| T | −1.29／−1.43／51% | −1.54／−1.80／56% | +0.77／+0.29／89% | −0.26／+0.56／18% |

## 點樣失敗
- **Gold／Good 跌嘅幅度 = 隨機改動嘅幅度**：喺呢 389 場，任何同幅度嘅改動（就算係冇資訊嘅洗牌）Gold 都平均跌 ~1.3–1.4pp、Good 跌 ~1.8–2.2pp。
  候選嘅 Gold 喺 null 中間（38–51 百分位）—— 即係呢個語料**判唔到**段速有冇幫 Gold。同 EXP-05 嘅「現行權重係呢批場次嘅 Gold 峰」一致。
- **廣義排序真係好咗**：capture@5、競爭 recall@5、頭三平均名次 CI 全正，F 嘅 capture@5 高過 97.5% null。
- **同 EXP-08 嘅矛盾**：5,206 場簡化模型 Gold／Good 冇跌；389 場引擎就跌。兩個都係真嘅量度，差別係樣本大細同 baseline 喺邊度調過。
  要喺引擎層面判，需要喺**引擎以外嘅歷史場次**跑真引擎（歷史回放，計劃第 3 步）或者 forward 新場次。

**leakage-audit**：PASS —— 特徵同 EXP-08（PIT）；標準化只用 2026-04 之前；冇賠率。
**commit**：冇 model code

## 重跑
```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_arm_hist_sectional.py \
  <labels_final.jsonl> <sect_features.pkl> <hkjc-history/parsed/sectionals.jsonl.gz> <outdir>
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_eval_harness.py compare --stage4 fixed_rule \
  --leakage-audit-passed <labels_final.jsonl> <outdir>/lab_hist_FT_b50.jsonl
```
