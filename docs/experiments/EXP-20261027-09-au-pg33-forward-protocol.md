# EXP-20261027-09 預先登記：pg33_N6 forward 測試（凍結）

> 凍結之前寫。凍結檔（`EXP-20261027-09-forward/freeze.json`）同結果檔（`result.json`）一經寫入就唔准改。

- **日期**：2026-10-27；**平台**：AU
- **用戶指示**：2026-10-27「將 EXP-20261016-10 嘅 pg33_N6 凍結做 forward 測試，預先登記判決規則，等夠 30 個新賽日先開。」
- **候選**：pg33_N6（[EXP-20261016-10](EXP-20261016-10-au-form-quality-placing-gate-results.md)）。近績質素分每場往績：
  p =（名次 − 1）/（出賽數 − 1）；
  每場值 =（z名次 + G）/ 2，**p ≤ 1/3 → G = z獎金，否則 G = min(0, z獎金)**。
  即係名次排喺前三分一嘅往績先計高班加分；低班扣分一律照計。
  其餘部分全部同 live eq2_N6 一樣：最近 6 場、權重 1.0／0.8／0.6／0.4／0.3／0.2、最少 2 場、引擎凍結常數、場內標準化。
- **baseline**：live eq2_N6（[EXP-20261016-06](EXP-20261016-06-au-merged-form-quality-results.md)）。
- **點解要 forward**：喺同一個 41 日窗口，同一條問題已經開過三個 family（EXP-06、09、10）。pg33_N6 嘅點估計全部向好，
  fixed arm Gold +0.13pp [−0.89, +1.12]，Good +0.61pp；頭兩名 $15+ 跑包尾 −9 [−21, +3]。但冇一項顯著，
  Holm p 0.795。合約 v3 規定：同一窗口唔可以再開第四個 family，只可以用未睇過嘅賽日開一次。
- **點解而家**：2026-10-27 早盤分歧診斷發現，大分歧場次（首選喺早盤排第 5 或以後）嘅首選，
  近績質素分優勢全部嚟自獎金項（+0.200），名次項係 −0.004。pg33 針對嘅正正係呢個機制。
  呢個診斷睇過 10-17 至 10-26 嘅結果，所以 forward 窗口由 **10-28** 開始，10-27 做緩衝。

## 凍結

| 項 | 值 |
|---|---|
| forward 窗口 | 2026-10-28 起，所有有賽前快照同賽果嘅 AU 場次 |
| 開箱時機 | 合資格賽日 ≥ **30**，之後**只開一次**（`result.json` 存在就拒絕再跑） |
| A arm | 凍結引擎原樣（eq2_N6）+ live 權重 |
| B arm | 同一個凍結引擎，只將 `engine_core._form_quality_digest` 每場值換成 pg33，權重同 A 一樣 |
| 模式 | `fixed_rule`：冇 fit 任何數值，門檻 1/3 係 EXP-10 預先登記嘅值 |
| code | 引擎目錄全部 `.py`、orchestrator、判決器、`eval_metrics`、`unified_reflector_core`，連評估腳本本身，逐個 sha256 寫入凍結檔。開箱嗰陣任何一個唔夾就拒絕跑，要 checkout 凍結 commit |

**點解只得 fixed arm**：§8 嘅 refit arm 要喺 forward 窗口自己 fit 權重，30 日唔夠。另外 EXP-10 入面 refit arm
本身係較弱嗰個（Gold −0.07pp）。今次要答嘅係「用現行權重直接上線得唔得」，即係 `candidate_with_live_weights`。
只得一個 arm，冇 arm 間多重比較。

## 輸入：只用賽前不可改快照

- 每個場次用 `select_prerace_snapshot(platform="au")` 揀賽前最後一個快照；冇快照嘅場次唔計。
- 兩個 arm 都用同一份快照嘅 Racecard／Formguide／Facts／Logic／Odds 重新評分，live 部署 hook 關閉。
- 賽果嚟自場次資料夾嘅 `Race_Results_Reflector.md`；少過 3 個名次嘅場次唔計，退出馬剔除。
- 洩漏：快照喺開跑前建立，Formguide 往績只會用 `date < 賽日` 嘅記錄（引擎原有規則），
  所以 `leakage_audit_passed=True` 有根據。

### 接通核對（凍結前做咗，冇讀任何賽果）

`selftest --date 2026-10-25`（Coonabarabran，8 場）：
- A arm 8/8 場排名同 production 快照完全一樣。
- B arm 改咗 38 匹馬嘅近績質素分，2 場頭四有變，即係 pg33 真係接通咗。
- 另外用 10-25、10-26 試行過一次 `evaluate` 成條路（2 個賽日，63 場，冇場次失敗），
  只核對咗場數同輸出格式，冇睇判決同指標。

## 判決（預先登記，唯一一次）

1. B vs A：`evaluate_full_record(domain="au", mode="fixed_rule")`。
   primary 係 Gold、Good 位置；ranking 係 `top3_capture_at5`、`ndcg_at5`、`competitive_recall_at5`、`mean_top3_model_rank`。
   按賽日 bootstrap 2000 次、seed 7、6 個時間塊。
2. 判 `PRIMARY_WIN` 或 `RANKING_WIN` → `ship_eligible`。可以準備上線改動，即係改 `engine_core._form_quality_digest`
   加上 golden／data_contract／模型說明三樣更新，但仍然要用戶批准。
3. 其他任何判決 → pg33_N6 結案 REJECT。**唔准**為同一個設計再開第二個 forward family，亦唔准用 pg50／pgw 等變體去救。
4. **次要，只報告**：頭兩名入面 $15+ 而跑尾三分一嘅匹次（A vs B）。佢唔影響判決。

## 功效（宣告）

EXP-10 嘅 41 日窗口有 1,482 場，Gold CI 半闊大約 ±1.0pp，而點估計只係 +0.13pp。30 個賽日嘅場數同佢差唔多。
所以除非真效應比 EXP-10 量到嘅大好多倍，否則最可能嘅結果係 `ranking_evidence_too_weak` 或 `primary_regression`，
然後 pg33 結案。呢個係預先接受嘅結果：forward 嘅作用係唔再喺同一窗口重複開，**唔係**保證會判得出改善。

## 唔准做嘅嘢

- 中途睇指標：`status` 只數賽日同場次，唔計任何指標。
- 改 code、門檻（1/3）、常數、權重、指標、開箱賽日數，或者揀日子。
- 開箱之後因為結果再調，然後重開。

## 指令

```bash
export PYTHONDONTWRITEBYTECODE=1
git worktree add --detach <路徑> <凍結 commit>     # code hash 一定要夾
cp .wongchoi_*root <路徑>/
cd <路徑>
python3 docs/experiments/EXP-20261027-09-forward/pg33_forward.py status
python3 docs/experiments/EXP-20261027-09-forward/pg33_forward.py evaluate   # 夠 30 個賽日之後，一次
```

`evaluate` 嘅暫存寫去外置碟 `WongChoi-Archive/scratch/EXP-20261027-09-pg33-forward/`。冇掛載就拒絕跑。
開箱之後喺同一個 worktree commit `result.json` 同結果記錄，然後推上 main。
