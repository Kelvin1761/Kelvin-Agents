# EXP-20261015-02 — AU 停用試閘表現門檻與重新配權

- 用戶確認：接受 EXP-20261015-01 嘅細微影響，偏向移除試閘表現，並要求重新配權及比較更低門檻。
- baseline：origin/main `b4373427`。之前全紀錄結果只作已知背景，唔當新 holdout。
- 先前記錄：EXP-20261015-01、EXP-20261012-31、EXP-20260904-01、EXP-20261012-32；判決用 v3。
- 呢個係用戶接受嘅簡化取捨，**唔係已證實改善**。新 refit 唔會因為用戶接受移除而豁免證據要求。

## 預先登記（睇較低門檻／refit 結果之前）

1. 固定比較 career_race_starts >= **2、4、6**；未知總場數保留原行為。
   三個 performance 路徑同時停用：trial_score 中性60、PF 移除已標示 trial run、
   maiden trial-time form proxy 停用。保留 preparation、fitness、rider continuity。
2. 每個門檻用現役引擎同同一份 archive 重算；全紀錄只報固定規則診斷。
3. Fit **只用 2026-08-05 起**嘅 capture-era 賽事，按完整日期排序。
   第一批30個賽日做 warmup；之後每7個賽日一個驗證窗（尾窗亦保留）。
   每窗只用窗之前日期 fit，唔丟棄冇共識嘅窗：fallback 到該門檻現行權重。
4. 每窗每門檻固定256個 Dirichlet draws，seed7，一半 broad、一半現行權重附近。
   沿用 `au_matrix_refit` place objective（Gold、Good positional、Pass、Top3 precision）。
   候選 training Gold/Good 各不得低過同門檻固定權重；objective 要正；
   五個完整日期時間塊至少四塊 objective 不負。合格 draws 逐維度中位數再正規化；
   中位數本身再檢查 primary/塊，唔過就fallback。**唔取 argmax**。
5. 報每個門檻 fixed vs refit，隔離刪訊號同配權嘅邊際。另有一條預先固定門檻選擇規則：
   每窗訓練資料上，候選 Gold/Good 均不低過六場固定版本、五塊至少四塊各 primary 不負，
   objective不負，就由 2、4、6 取最細合格門檻；冇合格用6場固定權重。
   呢條整體 policy 用之後窗口評估，**唔用 OOS 結果揀門檻**。
6. 用 v3 day bootstrap 2000／seed7／六塊，primary Gold/Good，ranking
   Top3 capture@5／NDCG@5／Top5 pairwise AUC；多候選 Holm；field-size、going、
   first-up、首選SP cohort 報診斷。簡化後六場 fixed 係 refit 比較基準，另報原模型。
7. 確認現役 numpy replica 與 production mapping 一致；搜索只作提案，最終共識預測
   以原生 production mapper／ordered arithmetic／4dp scores 重算。固定 draws同尺度預算。
8. 歷史 source/PIT FLAG 保留；日序 OOS只證明 fit 唔睇之後日期，**唔會偽造來源 availability
   或 results_available_at 去通過 au_oos_predictions intake**。輸出標成研究診斷，
   未 source-certify／forward-confirm 嘅 refit 權重唔上線。
9. 暫存係小型 leaf dump，唔抄完整語料；已量內置碟>10GB。任何>1GB暫存先確認外置掛載。

## 結果

**決定：六場固定簡化已完成並保存，正式啟用未開始；兩場／四場及全部 refit 保留研究，唔套用新權重。**
唔聲稱六場係統計證實嘅最優門檻，亦唔聲稱刪除提升準確度。

### 固定門檻（同一份 3,297 場／32,572 runner appearances）

| 設定 | Gold | Good positional | Pass | 相對六場版 |
|---|---:|---:|---:|---|
| 原模型 | 627 | 825 | 1,578 | 已知 baseline |
| 2 場起停用 | 623 | 819 | 1,562 | Gold一樣、Good少6、Pass少6 |
| 4 場起停用 | 622 | 824 | 1,564 | Gold少1、Good少1、Pass少4 |
| **6 場起停用** | **623** | **825** | **1,568** | 用戶確認接受嘅方案 |

語料：2025-08-02→2026-10-14，共138個日期；原 dump 3,299 場，兩場冇完整 podium/winner labels，
故同前次研究一致排除。三個門檻均由 production engine 重評。
六場實作對 EXP-20261015-01 ABC 實驗 **32,584 個原始 runner records ability 差異為0**，
證實用戶確認嘅修改同實作一致。Preparation／JH fit leaf逐匹不變。

### 重新配權（只用 capture era，逐窗向前）

2026-08-05→10-14 共2,496場／71日。前30日1,003場 warmup；之後 **1,493場／41日**，
六個未來日期窗，每窗7日、最後6日，冇跳過任何窗。4,608個固定預算 proposals，
每窗同一seed7，五個日期塊檢查後取逐維度中位數，再以production arithmetic驗證。

| 門檻 | 固定權重 Gold／Good／Pass | Refit Gold／Good／Pass | Refit邊際 | 統計診斷 |
|---|---|---|---|---|
| 2 | 289／388／745 | 288／390／737 | −1／+2／−8 | REJECT，Gold回歸 |
| 4 | 288／391／746 | 294／391／735 | +6／0／−11 | REJECT，Good時間塊不足4/6不負 |
| 6 | 288／393／749 | 291／390／747 | +3／−3／−2 | REJECT，Good回歸 |

六場refit邊際：Gold +0.201pp、95% day CI [−0.391,+0.744]；Good −0.201pp、
CI [−0.888,+0.498]。四場refit嘅Gold +0.402pp、CI [−0.237,+1.012]，亦未確立增益。
**唔可以為咗Gold多幾場就忽略Good／Pass同時間穩定性。**

預先固定嘅training-only門檻policy按次序選 **2、4、6、4、6(fallback)、6(fallback)**。
對六場固定版本：Gold +1、Good −4、Pass −13，v3 REJECT / primary_regression。
冇喺OOS結果揀兩場／四場／某組權重補救個結果。四條OOS候選×五個endpoint嘅Holm p全部1.0。
呢輪有限、預先鎖定嘅refit未搵到可靠收益；唔代表其他未測假設永遠冇用。

Policy嘅描述性分層（相對六場fixed；非獨立顯著結論）：

| Cohort | 場數 | Gold delta | Good delta | Pass delta |
|---|---:|---:|---:|---:|
| <=8匹 | 452 | +0.442pp | +0.664pp | −0.442pp |
| 9–10匹 | 514 | −0.195pp | −0.584pp | −0.195pp |
| 11–12匹 | 373 | +0.268pp | −1.340pp | −1.609pp |
| 13+匹 | 154 | −0.649pp | +0.649pp | −2.597pp |
| 首選SP $1–3 | 547 | −0.366pp | −1.097pp | 0.000pp |
| 首選first-up | 280 | 0.000pp | −1.071pp | −2.500pp |

Going／其餘SP／prep stage合共27個strata記喺摘要JSON；SP只作賽後診斷標籤，冇入評分。
Refit已失敗，唔會靠cohort改參救返，亦冇再追加搜索預算。

### 證據限制

- 歷史source／capture／label availability未逐筆獨立認證，**PIT FLAG仍在**。
  上述OOS只證明每窗fit只收之前日期；唔係`au_oos_predictions` source-certified production intake。
- 統計函數嘅leakage=True只係計算研究診斷，summary明文FLAG、promotion_authorized=false。
  無人製造results_available_at或來源PASS。所有refit均唔獲上線。
- 固定六場移除係用戶已明確接受嘅簡化決策，唔係改判原本REJECT或者改評估把尺。
- 固定門檻嘅mode應係fixed_rule；首輪輸出標籤一度寫walk_forward_oos，已改正metadata同研究程式
  嘅mode參數；數字、CI、sample及判決完全不變。Refit仍標walk_forward_oos研究診斷。

## 實作及驗證

- 共用`trial_performance_applies`判斷已知career total，default6；未知保留。
- `performance_pf_metrics`俾whole-field摘要同runner scorer共用；只filter已標示trial runs，
  原始PF／Facts／Formguide唔刪，未分類legacy行唔會冒充已認證正式賽。
- `_trial_score` neutral60，有明確停用說明；唔再用差試閘掛弱表現risk。
- maiden trial-time form proxy同一門檻停用；prep／fitness／rider continuity保留。
- Model generator讀實際cutoff並記engine_core fingerprint；唔手改生成嘅模型說明。
- golden原120個feature-vector mapping一致。執行`--record`只會因資料抽樣轉換改咗120個case，
  唔係此次leaf邏輯嘅回歸基準，所以preview存/tmp、保留舊golden作known-good；新邊界同
  raw-data filtering用20個針對測試及全語料逐馬比較驗證。
- Data contract由六場candidate新鮮dump嘅2,000場／19,347匹重建，日期08-18→10-14，
  fingerprint `8216c4f70dda`；用最小暫存scored Logic，**冇改live archive**。
  唔用舊live分數配新fingerprint冒充calibration。quick及完整`./檢查.sh`均PASS，20項針對測試PASS。

## 發佈狀態

Central exact-scope dry-run：risk=model、full gate、automatic activation。
雖然scope只有AU code／相關文件，標準流程會同步AU、HKJC、NBA、tennis四條線嘅production checkout。
自動批准審查因此拒絕實際`./保存.sh`發佈：用戶今次只授權AU，未明確授權四線production同步。
未繞過、未merge、未activate。完整改動與研究證據保存到非main分支
`codex-au-trial-cutoff-20261015`，等擴大同步scope嘅批准。正式各domain模型／排程未被修改。

## 重現與保存

Base commit `b4373427`；前次研究及baseline hash記錄喺研究分支
`codex-au-trial-experience-20261015` commit `d1170960`（EXP-20261015-01）。
今次dump／refit／calibration研究程式保留喺本次研究分支；未fit過嘅正式權重保持原樣。

```bash
export PYTHONDONTWRITEBYTECODE=1
# 同base commit嘅原模型baseline：
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_dump_engine_leaves.py \
  --out /private/tmp/au-trial-experience-baseline.json
# 在六場production patch上，研究wrapper只改該process嘅預先登記門檻：
python3 scratch/au_trial_cutoff_dump_20261015.py 2 /private/tmp/au-trial-cutoff-2.json
python3 scratch/au_trial_cutoff_dump_20261015.py 4 /private/tmp/au-trial-cutoff-4.json
python3 scratch/au_trial_cutoff_dump_20261015.py 6 /private/tmp/au-trial-cutoff-6.json
OPENBLAS_NUM_THREADS=1 python3 scratch/au_trial_cutoff_refit_20261015.py \
  --baseline /private/tmp/au-trial-experience-baseline.json \
  --out /private/tmp/au-trial-cutoff-refit-results.json
python3 scratch/au_trial_cutoff_calibrate_20261015.py
./檢查.sh --quick
./檢查.sh
```

原始dump每份約26MB，診斷prediction/result同summary留`/private/tmp/au-trial-cutoff-*`。
研究summary會保留數據SHA256、每窗cutoff／權重／accepted draws、cohort同CI；
完整prediction大檔唔放入repo。無重抄完整語料、無>1GB暫存。
