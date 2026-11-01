# EXP-20261101-31 結果：L600 point-in-time 情境標準 —— S、S0 REJECT（Gold、Good 都跌）

- **預先登記**：[protocol](EXP-20261101-31-au-l600-pit-standard-protocol.md)（`934d4697`，量度之前）。
- **語料**：baseline = EXP-20261101-30 上線版引擎 dump（`dump_shipped.json`，`1c7e1794`，引擎至 `49689be8` 冇變），
  4,049 場；v3 乾淨窗 3,246 場；§8 OOS 2,243 場／57 日，refit 程序 `f92c8377…` 兩邊一樣。
- **賽事表**：`scratch/au_l600_race_table_20261101.py`，24,871 場，可靠（最新來源 ≥ 08-24）22,829 場。
- **replica**：baseline 重算 `pace_figure_score` 同引擎 0 匹差 > 1e-3。
- **覆蓋**：202,169 條往績行，**91.4%** 換咗新 delta；7.5% 對唔到賽事（唯一配對失敗），1.1% 賽事唔可靠 → 保留原值。
- **決定**：S、S0 都 **REJECT**，冇上線。

## leaf 層面（只報告）

| | Δ AUC（baseline 0.60759） | 95% CI | p |
|---|---:|---|---:|
| S（有同日修正） | **+0.0072** | [+0.0009, +0.0133] | 0.027 |
| S0（冇同日修正） | **+0.0066** | [+0.0016, +0.0116] | 0.013 |

**新標準令速度分本身準咗**，同診斷一致（舊表偏差係真嘅）。

## 判決

| arm | v3 Gold | v3 Good | ranking | §8 fixed Gold／Good | §8 refit Gold／Good | 結果 |
|---|---|---|---|---|---|---|
| S | −0.31pp [−1.11, +0.44] | −0.52pp [−1.42, +0.33] | top3@5 +0.0030、NDCG +0.0022（CI 跨零） | −0.54／−0.22 | **−1.03 [−1.92, −0.16]**／−0.58 | primary_regression；both_arms_reject |
| S0 | −0.62pp [−1.37, +0.14] | −0.22pp [−0.86, +0.43] | 全部跨零 | −0.80／−0.05 | −0.62／−0.49 | primary_regression；**首選 $1–3 Gold CI 全負** |

Holm p 1.0／1.0；live guard 全部 primary_regression；`baseline_weights_stale = False`。
分層：今場往績多數喺後備表場地（`fallback_share` 高）嘅場次，即係理論上修正最有用嗰批，S Gold −0.06pp、Good −0.31pp —— 都冇改善。

## 解讀

- 同 EXP-20261101-30 R 一樣係「leaf 準咗、排名唔升」，但今次 **Gold 同 Good 兩個都跌**，refit arm Gold CI 全負，
  所以用戶接受嘅「Good 升 Gold 跌」取捨唔適用。
- 一個部分支持嘅解釋（未證實）：新標準之後速度分同其他 leaf 更重疊 —— 場內 ρ 對近績質素分 0.300 → 0.336、
  對場地適性 0.070 → 0.115。即係舊表嘅「偏差」有一部分其實係場地／班次資訊（例如鄉郊場地 L600 慢，嗰批馬亦較弱），
  修走之後速度分更「純」，但同模型已有嘅嘢更似。
- 舊表保留。診斷本身（59% 後備、大爛地 +1.98 秒）係真嘅，但喺現行模型入面修佢冇排名價值。

## 唔做嘅嘢

依登記唔改 penalty／分類／shrink、唔加 arm。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X=<外置碟 scratch>
python3 scratch/au_l600_race_table_20261101.py --root "$(cat .wongchoi_au_data_root)" --out $X/races.json
python3 scratch/au_l600_pit_standard_eval_20261101.py --dump <EXP-20261101-30>/dump_shipped.json --races $X/races.json --outdir $X/arms
python3 scratch/au_l600_pit_standard_judge_20261101.py $X/arms/base.json $X/arms/S.json $X/v3/S.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data $X/arms/S.json --out $X/wf/S.json
python3 scratch/au_paceperf_s8_20261016.py --base $X/wf/base.json --cand $X/wf/S.json --label S --out $X/s8/S.json
```

證據：`EXP-20261101-31-evidence/`。完整 arm 喺外置碟 `WongChoi-Archive/scratch/EXP-20261101-31/`。
