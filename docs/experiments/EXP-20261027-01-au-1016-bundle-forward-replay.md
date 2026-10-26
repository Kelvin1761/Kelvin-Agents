# EXP-20261027-01：10-16 改動整批 forward 回放（舊引擎 vs 現行引擎）

- **問題**：10-16 一日上咗十幾個 AU 評分改動（EXP-20261016-01／05／06／07／12／13／18／70／71／72／75／77／78），
  每個都係單獨測，冇做過合併嘅 forward 測試。10-17 之後表現跌（W43 Gold+Good 28.1%），係咪呢批改動搞成？
- **性質**：forward 回放評估（唔係新候選，冇改 code）。
- **baseline**：`6de9e625`（`c242b6c1` 之前最後一個 commit）。**candidate**：`c60bcb38`（現行 live main，
  包埋 10-16 之後嘅修正）。
- **輸入**：每個場次揀 reflector 用嗰份賽前快照（`select_prerace_snapshot`），抄 Racecard／Formguide／Facts／
  Logic／Odds 去用場次名命名嘅資料夾，兩個引擎各自 `au_auto_orchestrator.py` 評一次，冇 `--going` 覆蓋
  （兩邊用同一個快照 going）。`build_au_logic.py` 兩個版本之間冇改，所以係純引擎 A/B。
- **忠實度檢查**：新引擎重評 2026-10-17 Randwick，10／10 場排名同 live 快照一模一樣；舊引擎 0／10 一樣。
- **賽果**：各場次 `Race_Results_Reflector.md`，用 `load_structured_results`（按馬號、剔退出馬）。
- **窗**：2026-10-17 → 10-26，10 個賽日、63 個有賽果場次、**473 場**（69 個場次入面 6 個冇賽果檔／少過 3 名）。
- **指標**：`eval_metrics.race_metrics`；Gold = capture-at-4；bootstrap 按**賽日**重抽（4,000 次，seed 20261027）。

## 結果

頭四名 409／473 場唔同，首選 173／473 場唔同 —— 呢批改動大幅改咗排名。

| 指標 | 舊 | 新 | 差 | 95% CI（賽日 cluster） | P(新>舊) |
|---|---:|---:|---:|---|---:|
| **Gold** | 16.70% | 18.18% | **+1.48pp** | [+0.30, +2.72] | 0.99 |
| **Good（Gold+Good）** | 27.27% | 27.91% | +0.63pp | [−1.46, +2.19] | 0.74 |
| Pass | 44.61% | 44.82% | +0.21pp | [−3.49, +3.36] | 0.51 |
| 首選上名 | 54.97% | 52.22% | −2.75pp | [−7.92, +1.33] | 0.11 |
| 首選勝出 | 22.41% | 22.62% | +0.21pp | [−3.33, +3.90] | 0.51 |
| capture@4 | 58.70% | 59.36% | +0.65pp | [−1.33, +2.20] | 0.74 |
| NDCG@5 | 0.56 | 0.55 | −0.01 | [−0.03, +0.01] | 0.30 |
| MRR | 0.44 | 0.44 | 0.00 | [−0.02, +0.02] | 0.54 |

逐日 Gold+Good：10 日入面新引擎 7 日高、1 日打和、2 日低（10-20 n=14、10-23 n=47）。

## 判讀

1. **W43 嘅下跌唔係 10-16 改動造成。** 同一批場次，舊引擎 Gold+Good 27.3%，新引擎 27.9% —— 兩個引擎都跌，
   係呢段時間嘅場次難，唔係新 code 整壞。
2. **Gold +1.48pp CI 全正**，同 EXP-20261016-06 fixed arm 預期（+1.62pp）一致。但只得 10 個 cluster，
   CI 偏樂觀，當「方向一致」唔當「證實」。
3. **首選上名 −2.75pp（P=0.11）係要盯住嘅方向**：新引擎頭四名包得好啲，但最頂嗰匹揀得差啲。CI 跨零，
   未成立；唔准據此改嘢。Everest（Joliestar 首選、Tempted 第三）係同一個形狀嘅個案。
4. 呢個係整批對整批；冇拆邊個改動貢獻 Gold、邊個拖低首選。要知就要逐項 ablation（同一套 harness，
   每次只還原一個 EXP）。

## 限制

- 只有 10 個賽日；功效低，首選上名要差 ~5pp 先量得到。
- 兩邊讀同一份**現行** data-root 資源（騎練 cache、J/T 表），對兩邊同樣有輕微前視，比較係相對嘅。
- candidate 包埋 10-16 之後其他 AU 改動（10-18 試閘顯示等），唔係淨 10-16。

## 下一步

- 等 ≥ 30 個賽日（約 2026-11 中）用同一 harness 再跑，睇首選上名 −2.75pp 係咪企得住。
- 如果企得住，再做逐項 ablation 搵出邊個改動拖低首選。

## 重跑

```bash
S="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/claude-au-1016-replay-ab-20261027"
git worktree add --detach <old_wt> 6de9e625; git worktree add --detach <new_wt> c60bcb38   # 再抄 .wongchoi_*root
python3 docs/experiments/EXP-20261027-01-evidence/replay_ab.py    # 改頂部 WT／S 路徑
python3 docs/experiments/EXP-20261027-01-evidence/eval_ab.py
```

證據：`EXP-20261027-01-evidence/`（`plan.json` 每場次用邊份快照、`paired_rows.json` 逐場配對結果、兩個腳本）。
