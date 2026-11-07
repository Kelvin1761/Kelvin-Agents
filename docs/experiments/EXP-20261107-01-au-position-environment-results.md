# EXP-20261107-01：位置估算更準，但分離環境後仍未證明排名改善

- **日期／平台**：2026-11-07，AU。
- **授權**：Kelvin 要求測試更準的位置修正，採用以結果改善為條件；「go ahead」。
- **預先登記**：[protocol](EXP-20261107-01-au-position-environment-protocol.md)。揭盲後核對 hash 未變：`3f33c38dac6c6deb70f43e8b13020b6ec574990ceb20eae9063574ed5e3a82d2`。
- **baseline**：`bdf64d23c`，現行 C2、現行權重及全部 overlays；沒有改 production 模型。
- **搜索過**：EXP-20261101-40／41／42、EXP-20261013-10、評估合約 v3 + §6 + §8。
- **假設**：EXP-40 的位置修正移除了有用的賽事環境資訊；將本駒末段 P 與賽事環境 E 分開，固定各半 EP，可能改善最終排名。

## 資料與 A/A

現行引擎重新評分全 corpus（包含 Archive、沿用排除清單）：4,318 場、42,278 匹次。
判決輸入只用 2026-08-05 至 2026-11-06：**3,515 場、33,779 匹次、93 個賽日**。
30 個完整賽日 warmup 後，四 arm 共同 OOS 窗：**2026-09-05 至 2026-11-06，2,512 場、63 個賽日**。

- speed.py A/A：逐匹速度分 **0 差異**。
- exact_score 與引擎總分最大差 `0.0001`（既有 leaf dump 6dp 捨入容差）；**排名差異 0 場**。
- 三個候選都與 baseline 相同場次、相同馬號與賽果，沒有丟棄不利場次。
- 正式往績引用共 204,867 筆，800m/400m 位置都存在 194,129 筆（94.8%；同一往績可被不同目標賽事引用，非獨立樣本數）。
- 每筆往績日期 < 目標賽日；位置 OLS 每個目標日只用更早事件，最低訓練 8,560 筆，沒有低於 2,000 門檻的目標日 fallback。缺位置輸入仍照 EXP-40 的規則處理。

研究 dump 工具為適應現行引擎，移除兩個已退役 helper 的輔助 metadata 呼叫，保留欄名而寫 null；加入原來漏掉的 draw overlay。沒有改任何評分公式。
候選的常數池中性防護在揭盲前加入：三個相同 0.2 可因浮點加總出現假 SD；候選完全相同值一律為 60。生產 speed.py 未改。

## 估算時間準確度：確實改善

使用 EXP-40 已凍結 RQ 真值訓練表，2026 年起逐日只用更早事件訓練，**9,750 筆**可驗證記錄。

| 估算方法 | MAE（秒，越低越好） | RMSE（秒） |
|---|---:|---:|
| 現行：賽事 L600 + 輸距 × 0.17 | 0.8698 | 1.7440 |
| P：位置修正 | **0.5197** | **1.5123** |

這回答「時間估得準不準」，不是下一仗預測判決。真值只來自昆士蘭，不能宣稱其他州也有相同準確度。

## 固定候選與消融

- **P**：沿用 EXP-40 的逐日 OLS 位置修正，取代現行 own 估算。
- **E**：純賽事 L600 環境，沒有輸距項。
- **EP**：P 與 E 各自場內標準化、clip 後固定各佔一半；沒有搜索混合比例。
- 其餘近績、騎練、評分、場地、備戰與 full_time/wet/proven_class/draw 全部保持。

在三候選都有非中性證據的同一批馬（31,741 匹次、62,718 上名/落榜可比對）上，單 leaf 場內 AUC：

| BASE | P | E | EP |
|---:|---:|---:|---:|
| 0.60788 | 0.59154 | 0.54453 | 0.57111 |

這些是共同樣本的描述性點估計，不是 promotion 指標；中性 60 剔除口徑四邊相同。

## 功效前置（候選績效前已量）

按相同 OOS 窗，把整個速度 leaf 設為 60，以其 |delta| 作部件預算，賽日 bootstrap CI 半寬作 MDE：

| Ranking metric | 部件預算 | MDE | 可作 ranking 判決？ |
|---|---:|---:|---|
| top3_capture_at5 | 0.002521 | 0.003945 | 否 |
| ndcg_at5 | 0.001106 | 0.003308 | 否 |
| top5_pairwise_auc | 0.001567 | 0.002535 | 否 |

三個 ranking metric 都是非資訊性，沒有拿「CI 跨零」當作候選無效證據，也沒有拿某個偶然負 CI 單獨判死。
**本輪拒絕是 primary 點估計與時間塊未過，而非 ranking_evidence_too_weak。** 若 primary 過關但只剩這些不足功效的 ranking，應記 UNRESOLVABLE。

## 雙邊重訓結果（B1 vs B0）

每邊同一程序：30 日 warmup、7 賽日窗、256 draws、seed 7、place 目標、中位數共識、相同 fallback。
程序 hash：`7b81d61f1f2b3512575e793eca729244ce94c9f2803a33a249f592d78c69ee22`。
9 個窗口中 BASE 有 8 個、P 有 9 個、E 有 8 個、EP 有 4 個 fallback；fallback 是預先登記程序找不到合格共識，沒有因此增加搜索量。

| 配置 | Gold | Good 位 | Pass | 研究判決 |
|---|---:|---:|---:|---|
| BASE 自己重訓 B0 | 21.9745% | 28.1847% | 52.3885% | 基準 |
| P 自己重訓 B1 | 22.0143% | 27.8264% | 51.6720% | REJECT / primary_regression |
| E 自己重訓 B1 | 21.8949% | 27.9459% | 51.4331% | REJECT / primary_regression |
| EP 自己重訓 B1 | 21.4570% | 27.8662% | 51.5127% | REJECT / primary_regression |

Gold = 實際前三全部落在模型頭四；Good 位 = 模型首兩揀都上名。

配對賽日 bootstrap 2000 次、seed 7，差值以百分點報：

| 候選 | ΔGold [95% CI] | ΔGood 位 [95% CI] |
|---|---|---|
| P | +0.0398 [−0.390, +0.477] | −0.3583 [−0.911, +0.164] |
| E | −0.0796 [−0.847, +0.673] | −0.2389 [−1.014, +0.427] |
| EP | −0.5175 [−1.264, +0.158] | −0.3185 [−0.947, +0.338] |

固定現行權重 A1 vs A0 亦三邊 primary_regression；因此 §8 三候選都是 both_arms_reject。
arm 內 Holm 及跨 P/E/EP Holm 均沒有顯著勝出（調整 p 全 1.0）。A/A control 為 REJECT。
共享 §8 helper 將 A1/A0 一律標 fixed_rule；P/EP 的位置 leaf 實際逐日向前 fit，另用正確 walk_forward_oos mode 重判並斷言結果相同，沒有把 fitted 候選當成未學習的固定規則。

EP − P 的 B arm：Gold −0.5573pp、Good +0.0398pp，CI 均跨零。
EP − E 的 B arm：Gold −0.4379pp、Good −0.0796pp，CI 均跨零。
**沒有證明同時保留 E 與 P 的額外複雜性有收益。**

## 分層與限制

完整分層在外置碟 judgement.json：馬群四桶、首選 SP 五桶、路程、going、venue、首選跑法、初出與久休；全部以 baseline 首選定桶，沒有隨候選換樣本。
P 的 11–12 匹 Good 位 B arm −1.48pp，名義 95% CI [−2.56, −0.50]；後上首選 Gold B arm −1.11pp [−2.08, −0.16]。
這些是多個分層的未校正診斷，不作獨立顯著改善聲稱；只有一個賽日的小場地，其 bootstrap CI 是退化值，明確標示，不能拿來推論。

歷史資料的 source availability 仍然 **FLAG**（既有研究 harness 限制）。事件日期向前、樣本與評分隔離已查，但不能證明每筆回填資料在原下注時已可取得。
因此正式 source gate 是 **REJECT / leakage_audit_failed**；上面的績效判決是條件式 research diagnosis，不能當正式 WIN。
歷史窗口重用，**不是 untouched holdout**。本輪沒有候選達研究採用門檻，因此沒有新開 forward，也沒有打開其他既有 forward 的判決。

## 決定

**本輪 P / E / EP 全部 REJECT，不改現役模型。**
位置修正較準確地描述末段時間，這點獲得支持；但這三種使用方式沒有證明能改善下一仗排名。
不能推論「更準的 L600 永遠沒用」，也不能聲稱已證明必然有害（整體 primary CI 跨零）。
研究腳本及失敗證據保存到研究分支，不合併／部署失敗模型；沒有增加事後候選救結果。

## 重跑與證據

環境：`/Users/imac/Antigravity-repo/.venv/bin/python3`，`PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1`。
先確認外置碟掛載、內置碟 ≥10GB；令 `TMPDIR` 指向研究目錄。

```bash
S='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-position-environment-20261107'
T='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/speed-rebuild/training.json'
R="$S/replay"
AU_STUDY_PY='/Users/imac/Antigravity-repo/.venv/bin/python3'
mkdir -p "$R"
export TMPDIR="$R" PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
"$AU_STUDY_PY" scratch/au_position_environment_20261107.py build --dump "$S/baseline_dump.json" --training "$T" --outdir "$R"
for a in BASE P E EP; do
  "$AU_STUDY_PY" .agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py predict --data "$R/$a.json" --out "$R/wf_$a.json"
done
"$AU_STUDY_PY" scratch/au_position_environment_20261107.py judge --outdir "$R"
# 如需重新 dump 今日 corpus（另一份資料），另寫新檔，勿覆蓋凍結 baseline：
# "$AU_STUDY_PY" scratch/au_speed_rebuild_aa_20261101.py --out "$R/current_dump.json"
```

完整 baseline dump SHA256：`e9976b9cea8b1b83a7324d3ab15d9a4d929b5adc019462b7e28664bf73a7bfcb`。
凍結 training SHA256：`8e5195df9f05361b9e6a31e119230730e1677d90f2889799e5a99a19c97a3d58`。
外置碟保留 baseline dump、所有 arm、wf、完整 judgement 與執行 log；濃縮證據見 `EXP-20261107-01-evidence/`。
重跑 dump 會讀當時 corpus，若 hash 改變則是另一份資料；重現本輪須直接使用上述凍結 dump。

## 驗證

研究 invariant smoke checks、定向 ruff、quick check 通過；AU/HKJC golden 各 120 匹不變。
數據合約只有既有 AU trial 中性比例及 HKJC stale-baseline 警告；本研究沒有改評分，不重新校準掩蓋警告。

首次完整檢查使用系統 Python 3.9，在 sandbox 內有五個環境失敗：NBA relocation 四個測試無權執行 `ps`，APFS compression 一個未能壓縮。
相同 Python 在 sandbox 外重跑兩個測試檔：**17 passed**，無生產程式修改。
另試 Python 3.14 全閘，發現既有 `test_path_change_during_initial_open_fails_closed_and_does_not_cache_old_file` 的 `os.open` monkeypatch 與 `Path.touch()` 遞迴相容性問題，已以單檔重現並停止該次全閘；沒有修改這個無關測試。

最終以 `PYTHON_BIN=/Library/Developer/CommandLineTools/usr/bin/python3 PYTHONDONTWRITEBYTECODE=1 ./檢查.sh` 在 sandbox 外重跑：**exit 0，16 個 suite 全部 PASS，全部 gate 全綠**（1009 秒）。
沒有更改測試或略過失敗測試。濃縮 receipt 見 `EXP-20261107-01-evidence/verification.json`；原始 logs 保留在外置碟研究目錄的 `verification/`。
