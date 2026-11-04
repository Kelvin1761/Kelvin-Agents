# EXP-20261105-04 結果：前置習慣 ±K —— 全紀錄 4 個 arm 全部 REJECT；C（當晚開關）照舊 forward

- **協議**：[EXP-20261105-04-hkjc-front-habit-and-night-bias-protocol.md](EXP-20261105-04-hkjc-front-habit-and-night-bias-protocol.md)（登記 commit `19fd6b81`）
- **跑法**：`19fd6b81` detached worktree，`hkjc_eval_harness.py run --until 2026-10-10 --dump-matrix`，PIT priors；
  A4 refit 用 `hkjc_weight_study.py --arm wf_refit`。
- **語料**：351 場 replay → 配對 **286 場、29 個賽日**。1 場 ≈ 0.35pp。
- **判決**：全部 `REJECT / primary_regression`，冇 WIN，Holm 唔使做。**A 唔開 forward，live 冇改。**

## 結果

| Arm | 模式 | 排序有郁 | Gold Δpp [95% CI] | Good Δpp [95% CI] | top3_capture@5 | NDCG@5 | 前三平均名次 |
|---|---|---:|---|---|---|---|---|
| A2（±2） | fixed | 199 | +1.05 [−0.35, +2.49] | −1.40 [−3.73, +0.73] | +0.47 | −0.0000 | −0.026 |
| A4（±4） | fixed | 248 | **+1.75 [+0.33, +3.45]** | −0.35 [−2.83, +2.13] | +0.70 | −0.0027 | −0.052 |
| A6（±6） | fixed | 266 | +1.40 [−0.71, +3.82] | −2.45 [−5.12, +0.34] | +1.05 | −0.0012 | −0.062 |
| A4 | wf_refit | 251 | +0.35 [−2.13, +3.11] | −1.05 [−3.39, +1.07] | +0.82 | +0.0009 | **−0.049 [−0.100, −0.003]** |

（前三平均名次：細 = 好，即係實際前三喺模型排得前啲。）

### 場地分層（只報）

| Arm | 沙田（191 場）Gold／Good | 跑馬地（95 場）Gold／Good |
|---|---|---|
| A2 | +1.57／**−2.62** | 0.00／+1.05 |
| A4 | +2.09／−1.05 | +1.05／+1.05 |
| A6 | +1.05／−1.57 | +2.11／**−4.21** |

⚠️ 沙田 Good 三個 K 都係負，跟協議規則要標記。篩選時前置優勢喺沙田最大（+11.1pp），真引擎反而 Good 跌。

## 讀法

1. **前置習慣有用，但只係推高頭馬，唔係推高上名**：A4 Gold +1.75pp CI 全正（p 0.050，Holm 後唔顯著，亦細過 MDE ±1.96），
   前三平均名次三個 K 都改善，refit 版 CI 全正。但 Good（上名）一路細負，K 越大越差 → `primary_regression`。
2. **cohort 差距 ≠ 排名收益**（[[au-cohort-gap-is-not-a-gain]]）：篩選 +8.6pp 係同一排名區間嘅上名率差，但加分之後推上去嘅前置馬，
   擠走咗本身已經會上名嘅馬。同 EXP-20260927-04 一致：檔位與走位已經用咗歷史走位，再疊一層前置分大部分係重複。
3. **K 越大越蝕**：A6 Good −2.45pp、跑馬地 −4.21pp，即係唔係「加得唔夠」。

## C：當晚偏差開關（forward，照舊收集）

協議寫明 C 只可以喺 EXP-20261104-11 嘅即場資料（`captured_at`）上面判，同 A 全紀錄結果無關，所以**繼續收集**：
tracker `front_habit_night_gate`，60 個完整賽晚夠數 Telegram。篩選第 4 節（當晚前置唔著數 → 前置優勢消失 +0.3pp）
係事後研究；如果 forward C 都唔贏 base，就連「當晚開關」一齊放棄。

## 結論（交 Kelvin）

- **步速唔入分**（預測 ρ 0.125）；**前置習慣固定加分唔入分**（Good 跌）。
- 跑法資訊而家用喺兩個地方：dashboard「預計跑法」label（參考，唔入分）同 C 嘅 forward 測試。
- 下一個值得試嘅唔係再加前置分，而係 C：當晚偏差先決定前置有冇著數。

## 重現

```bash
git worktree add --detach /tmp/exp04 19fd6b81520ae135a3ae0bf535d2835c2fa39c2c   # 再 cp .wongchoi_*root
# 跟協議「量度」一節嘅命令
```
