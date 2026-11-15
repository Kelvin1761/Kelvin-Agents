# EXP-20261115-03 — HKJC 19 組訊號重建第一批：階梯式 leaf 改連續（REJECT，holdout 未開）

- 日期：2026-11-15｜平台：HKJC｜判法：`docs/model-evaluation-contract.md`「HKJC 歷史回放尺 v4」
- 起因：Kelvin 2026-11-15「19 組訊號睇下有冇得改／精煉／重建公式，抽多啲訊號出嚟」。
- 假設：現行三個 leaf 用階梯（查表／分級）—— 同一級內嘅資訊被丟走；改成喺**現行錨點之間線性插值**（fixed_rule，冇由數據 fit）應該抽返嗰部分。

## 候選（預先登記，arm：`docs/experiments/patches/hkjc_arm_leaf_continuous.py`，`WC_LEAF_ARM`）
| arm | 改咩 |
|---|---|
| form | 近績名次先換算做 14 匹等效名次 r14 = 1 + (名次−1)/(出賽數−1)×13（出賽數由 formguide「名次: P / F」），再喺 1→100、2→85、3→75、4.5→60、6→40 之間插值；有海外往績嘅馬照現行 |
| l400 | L400 絕對值五級 → 連續（錨點 22.4/+8.62 … 24.6/−5.64，兩端平） |
| finish | 完成時間「近 N 仗修正平均」→ 連續（錨點 0.15/+6.52 … 1.55/−8.0，兩端平） |

## 方法
- baseline：現行 main（S 版權重＋段速 FT＋L400 實測係數）重新回放全部 6,047 場 → `hkjc-history/analysis/replay_all/v2/base.jsonl`（外置碟）。
- 候選：`hkjc_history_replay_prun.py --arm … --out v2/leaf_{form,l400,finish}.jsonl`。
- wiring test（2023-10-01，10 場）：form 87 匹分數變、8 場排名變；l400 82／4；finish 92／5 —— 有接通。
- 判：`hkjc_replay_compare_v4.py v2/base.jsonl v2/leaf_X.jsonl --window dev`（2,488 場、264 日；walk-forward 校準）。

## 結果（dev）
| arm | Δlog-loss（每匹） | 好過 null | Δ場內 AUC | Gold | Good | 判決 |
|---|---|---|---|---|---|---|
| form | +0.00012 [−0.00020,+0.00044] | 91% | −0.0004 | +0.12 [−0.48,+0.68] | +0.16 [−0.48,+0.76] | REJECT |
| l400 | −0.00002 [−0.00015,+0.00012] | 87% | +0.0004 | +0.28 [−0.08,+0.64] | −0.16 [−0.53,+0.24] | REJECT |
| finish | −0.00003 [−0.00017,+0.00011] | 90% | +0.0008 [−0.0000,+0.0015] | +0.04 [−0.40,+0.44] | −0.36 [−0.82,+0.08] | REJECT |

三個都 REJECT（log-loss CI 跨零、過唔到 null）。**holdout 冇開**（登記簿唔使記）。

## 點解失敗（學到咩）
- 階梯量化損失好細：同一級內嘅差距喺排名入面幾乎冇額外資訊。form 連續化甚至略差（出賽數換算對細場次嘅頭馬／包尾馬放大咗噪音）。
- finish 場內 AUC 最接近（下界 −0.0000），但幅度 +0.0008，log-loss 冇郁 —— 唔值得再調錨點（調錨點 = 由 dev fit，要另開候選並交 walk-forward）。
- 結論：**19 組訊號嘅缺口唔喺「leaf 形狀」**。之前 EXP-20261114-12（剷噪音）、EXP-20261115-01（固定加分／校準加分）、而家（連續化）三條路都話：喺 S 版權重下，現有 leaf 已經差唔多抽乾。再要升就要新資訊（新欄位／新來源）或者結構改動（例如互動項：段速 × 場地、近績 × 班次變化），唔係再磨現有公式。

## 可重現
worktree `claude-hkjc-leaf-rebuild-20261115`；`PYTHONDONTWRITEBYTECODE=1`；命令見上；baseline commit = main @ 39e13cc1 之前嘅 d702b14e 引擎（評分 code 冇變）。
