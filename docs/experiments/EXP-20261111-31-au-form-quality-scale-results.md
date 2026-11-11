# EXP-20261111-31 結果：近績質素分場內 SD 下限／固定尺 —— 兩個都 REJECT

- **預先登記**：[protocol](EXP-20261111-31-au-form-quality-scale-protocol.md)（分支 `claude-au-fq-scale-20261111` `3b6b3611`，量度之前 commit）。
- **baseline**：main `6bd4f6de`。輸出：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/fq-scale/`。
- **接線檢查**：F1 改咗 17,983 匹／2,266 場；F2 改咗 28,465 匹／3,469 場（全語料 dump）。
- **決定**：F1、F2 全部 **REJECT**。冇改動上線；研究碼留喺分支。

## v3 fixed_rule（3,694 場）

| arm | 改咗場數 | Gold | Good | top3@5 | ndcg@5 | AUC | 分層 CI 全負 |
|---|---:|---|---|---|---|---|---|
| F1 下限 | 2,265 | −0.11 [−0.57, +0.37] | −0.41 [−1.07, +0.20] | **+0.32 [+0.07, +0.59]** | +0.15 | +0.16 | 冇 |
| F2 固定尺 | 3,468 | −0.14 [−0.66, +0.40] | −0.41 [−1.12, +0.27] | +0.29 [+0.00, +0.60] | +0.06 | +0.12 | **>1600m Good** |

兩個都 `primary_regression`（Gold／Good 點估計 < 0）。

## §8（2,691 場、68 賽日）

| arm | fixed：Gold／Good | refit：Gold／Good | refit top3@5 | 判決 |
|---|---|---|---|---|
| F1 | +0.07／−0.30 | +0.11／−0.19 | **+0.37 [+0.06, +0.68]** | both_arms_reject（Holm p 1.0） |
| F2 | +0.07／−0.30 | −0.15／−0.33 | +0.29 [−0.05, +0.62] | both_arms_reject（Holm p 1.0） |

F1 refit 分層：首選 SP $3–6 Good CI 全負；F2 兩個 arm：軟地 7+ Good CI 全負。stale（B0 vs A0）REJECT —— 現行權重唔係過時。

## 描述（唔做判決）：細 SD 場次嘅首選係咪被高估？

模型 #1 入前三率，細 SD 場次（F1 有郁，即場內 SD < 0.3065）vs 一般場次，同一 SP 段（08-05 起，按賽日 bootstrap）：

| SP | 首選狀態與穩定性 | 細 SD | 一般 | 差 |
|---|---|---:|---:|---|
| $1–3 | ≥85 | 76.3%（367） | 81.8%（325） | −5.6 [−12.3, +0.6] |
| $3–6 | ≥85 | 55.2%（467） | 59.5%（269） | −4.2 [−11.7, +3.6] |
| $6–12 | ≥85 | 37.2%（261） | 41.3%（104） | −4.2 [−14.2, +6.0] |
| $1–3 | <85 | 81.8% | 75.5% | +6.3 [−0.5, +13.1] |

- 用戶嘅直覺**方向啱**：狀態與穩定性 ≥85 嘅首選，喺細 SD 場次跑少大約 4–6pp（三個價位段都係），但每個 CI 都跨零。
- 但修尺度換唔到 Gold／Good：改善落咗喺「頭 5 名入面捕捉前三」（top3@5 +0.3），首兩選反而輕微變差。
  即係壓低細 SD 場次嘅放大之後，被頂上嚟嘅馬唔見得好過。
- 94.6 本身唔係「馬王級」嘅意思：分數係場內相對，724 場有 392 場最高分 ≥ 90。報告層可以考慮講清楚呢點（未做）。

## 點解唔再試

- 同一個 08-05 窗嘅第七個近績質素分 family（EXP-20261016-06、-71、20261028-11、20261105-05／-06／-09、今次）。
- 唔會換第二個 SD_POOL 再試 —— 嗰個係用結果揀參數。
- 如果要再處理，方向係報告層（標明「場內相對分」同場內 SD），或者等更多 forward 數據，唔係再郁尺度。

## 重跑

```bash
git checkout 3b6b3611   # 分支 claude-au-fq-scale-20261111
"/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/fq-scale/run_all.sh"
```

（dump：`au_dump_engine_leaves.py`，`WC_AU_FQ_SCALE=floor|fixed`；v3：`scratch/au_track_simplify_judge_20261103.py`；
§8：`au_walkforward_refit.py predict` + `scratch/au_track_sp_s8_judge_20261103.py`。）
