# EXP-20261101-33 結果：L600 純路面標準（SH）／冇場地項（G）—— 兩個都 REJECT

- **預先登記**：[protocol](EXP-20261101-33-au-l600-surface-standard-protocol.md)（`1644bc08`，量度之前）。
- **語料**：同 EXP-31（baseline `dump_shipped.json`，`1c7e1794` 引擎）；逐駒往績 96,844 匹次；v3 乾淨窗 3,246 場；
  §8 OOS 2,243 場／57 日，refit 程序 `f92c8377…` 兩邊一樣。replica 0 匹差；91.4% 往績行換咗新 delta。
- **sanity（2026-09-15 一日 fit）**：SH 之下城市場地仍然快過鄉郊約 0.7 秒（Flemington −1.25、Kilcoy −0.50），
  即係保留咗質素差；舊表兩者都約 0（抹走咗）。
- **決定**：SH、G 都 **REJECT**，冇上線。Good 點估計都係負，所以 Kelvin 嘅「Good 升、Gold 跌」取捨唔適用。

## leaf 層面

| | Δ AUC（baseline 0.60759） | 95% CI | 場內 ρ(速度分, 近績質素分) |
|---|---:|---|---:|
| 現行 | — | — | 0.306 |
| EXP-31 S（場地平均） | +0.0072 | [+0.0009, +0.0133] | 0.336 |
| **SH**（純路面） | +0.0086 | [+0.0020, +0.0153] | 0.359 |
| **G**（冇場地項） | **+0.0130** | [+0.0074, +0.0184] | 0.364 |

同 EXP-32 診斷完全一致：越少抹走場地質素，速度分越準 —— G（完全唔扣場地）最準。

## 判決

| arm | v3 Gold | v3 Good | top3@5 | §8 fixed Gold／Good | §8 refit Gold／Good | 備註 |
|---|---|---|---|---|---|---|
| SH | −0.37pp [−1.16, +0.38] | −0.46pp [−1.41, +0.38] | **+0.0043 [+0.0007, +0.0078]** | −0.67／−0.22 | −0.54／−0.36 | 首選 $1–3 Gold CI 全負 |
| G | −0.09pp [−0.79, +0.57] | −0.52pp [−1.28, +0.21] | **+0.0037 [+0.0005, +0.0070]** | −0.31／±0 | −0.45／−0.40 | 冇分層全負 |

v3 兩個都 `primary_regression`；§8 `both_arms_reject`，live guard primary_regression，Holm p 1.0。
後備表往績佔比高／低兩層都冇改善。

## 解讀

- **三次一樣**（EXP-30 R、EXP-31 S、今次 SH／G）：速度分本身準咗、top3 捕捉率仲顯著升，但 Gold／Good 冇升甚至跌。
  共同點係**速度分越準，越似近績質素分**（ρ 0.306 → 0.36）。速度分喺模型入面嘅價值主要來自佢同狀態「唔一樣」；
  佢變得更能反映能力，就同已經反映能力嘅狀態維度重疊。refit 權重（§8 B arm）都救唔返，即係唔係權重過時。
- 呢個同 memory `leaf-auc-gains-do-not-convert-to-ranking`、`au-feature-set-is-saturated` 一致：
  AU 排名嘅瓶頸唔係速度分夠唔夠準。
- 用戶嘅直覺（標準應該反映能力）喺量度層面係啱嘅 —— G、SH 都準過現行；只係喺現行模型入面換唔到 Gold／Good。

## 唔做嘅嘢

依登記唔改收縮／距離曲線、唔加類別、唔加 arm。

## 重跑

```bash
export PYTHONDONTWRITEBYTECODE=1 X=<外置碟 scratch>/EXP-20261101-33 Y=<外置碟 scratch>
python3 scratch/au_l600_surface_standard_eval_20261101.py --root "$(cat .wongchoi_au_data_root)" \
  --dump $Y/EXP-20261101-30/dump_shipped.json --races $Y/EXP-20261101-31/races.json --outdir $X/arms
python3 scratch/au_l600_pit_standard_judge_20261101.py $X/arms/base.json $X/arms/SH.json $X/v3/SH.json
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data $X/arms/SH.json --out $X/wf/SH.json
python3 scratch/au_paceperf_s8_20261016.py --base $X/wf/base.json --cand $X/wf/SH.json --label SH --out $X/s8/SH.json
```

證據：`EXP-20261101-33-evidence/`。
