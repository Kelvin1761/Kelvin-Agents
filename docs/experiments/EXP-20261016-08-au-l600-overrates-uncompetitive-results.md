# EXP-20261016-08 結果：L600 環境分推高唔具競爭力嘅馬？

- **預先登記**：[protocol](EXP-20261016-08-au-l600-overrates-uncompetitive-protocol.md)（commit `e443209d`）
- **baseline**：分支 head（F6a + 班次 parser + 近績質素分）。8 個 refit verify 全部過，procedure hash 一樣。
- 研究診斷（來源 FLAG）。

**結論：6 個候選全部 REJECT；冇一個減少「頭兩名跑包尾」。L600 唔係跑包尾冷門嘅成因 ——
完全剷走 L600 反而多咗。** 冇改模型。

## 候選結果（1,482 場／41 日 OOS）

| 候選 | 對照 | §8 | 頭兩名跑尾三分一 | 頭兩名 $15+ 跑尾三分一 | 首選跑尾三分一 |
|---|---|---|---|---|---|
| P1 剷走 pace_perf | A0 | both_arms_reject（fixed Gold −0.61、Good −0.95pp；refit Gold −1.88pp） | +0.26pp [−0.30, +0.86] | **166 → 177** [−6, +28] | ±0 |
| P2 負距 ×2 | A0r | fixed primary_regression；refit too weak（Good +0.81pp） | −0.08pp [−0.34, +0.16] | 171 → 167 [−12, +3] | −0.20pp |
| P3 競爭力閘 | A0r | both regression | **+0.52pp [+0.09, +0.98]** | 171 → 177 | +0.56pp |
| P4 近績封頂 | A0 | both regression | +0.12pp | 166 → 167 | +0.28pp |
| P5 全程速度代替 | A0 | both regression | +0.46pp [−0.10, +1.00] | 166 → 173 | +0.28pp |
| P6 樣本收縮 | A0r | both regression | −0.04pp | 171 → 171 | +0.08pp |

（A0r = replica 重算 PF 嘅 baseline；同 engine A0 比：頭兩名跑包尾 +0.14pp，replica 本身有少少誤差，
所以 P2／P3／P6 一律同 A0r 比。）

## 解讀

1. **L600 有訊號，而且幫手壓低跑包尾。** 剷走佢（P1）Gold、Good 都跌，頭兩名大冷門跑包尾多 11 場。
2. **「唔具競爭力嘅往績唔准貢獻速度」（P3）令情況更差**：大敗場入面嘅速度環境係有資訊嘅
   （同 EXP-20261016-01 D2「封頂負距會蝕」一致）。
3. 用戶睇到嘅「速度考驗背景好高分」：dashboard 維度分（例如 85.1）係**未乘係數**嘅分數；
   入綜合分係 0.114 × (85 − 60) ≈ +2.9。跑包尾冷門嗰批平均靠 `pace_perf` 只係 +1.3（入位熱門 +1.6）。
4. **真正要追嘅線索**：
   - 跑包尾冷門平均靠 `stability` 推高最多（live 等價 +2.97、新版 +7.33），而騎練訊號偏低
     （+1.02～1.73 vs 入位熱門 +2.53～2.73）。
   - **近績質素分令頭兩名 $15+ 跑包尾由 130 增到 166**（Gold／Good 同時升）——
     新 leaf 揀到更多上名馬，但亦推多咗冷門上頭兩名。上線前要了解。

## 重跑

```bash
python3 scratch/au_l600_candidates_20261016.py build --dump $S/st/prod_fq_exact.json --asb $S/pp/asb.json --outdir $O
for a in A0 A0r P1 P2 P3 P4 P5 P6; do python3 scratch/au_paceperf_refit_20261016.py --variant f6a predict --data $O/$a.json --out $O/wf_$a.json; done
# 每個候選對預先登記嘅 baseline：
python3 scratch/au_paceperf_s8_20261016.py --base $O/wf_<base>.json --cand $O/wf_<cand>.json --label X --out $O/s8_X.json
python3 scratch/au_l600_candidates_20261016.py flops --base $O/<base>.json --cand $O/<cand>.json
```
