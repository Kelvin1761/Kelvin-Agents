# EXP-20261113-30 結果：十二仗狀態／穩定性與同場同程

- **決定：不改 live。** 四個候選都未證實令分析表現改善。
- 協議：[預先登記](EXP-20261113-30-hkjc-long-history-protocol.md)。先寫協議、重跑 baseline 同功效診斷，先開候選。
- Baseline：`e6e45aa1d`；production `score_race`、PIT 騎練先驗、禁 profile network enrichment、禁寫 archive／deploy。
- 語料：351 場 replay；1 場 baseline/candidate 同樣有 runner-set mismatch，60 場 speed_score 全場死欄位；
  最終每個 arm **同樣 290 場、29 賽日、3,652 匹馬**，2026-05-03 至 2026-10-07。
- 現行 Gold **42/290 = 14.48%**；Good（頭二選都上名）**69/290 = 23.79%**；頭二選至少一匹上名 **210/290 = 72.41%**。
- 只開發段；**冇開 2026-10-11 起 forward 結果做確認、冇開新 shadow／forward 測試**。

## 現行權重（候選 − baseline，pp）

Gold = 實際前三全部在模型頭四選內；Good = 模型頭二選都上名。CI 按賽日配對 bootstrap 2,000 次、seed7。

| Arm | 排名變動場數 | Gold Δ [95% CI] | Good Δ [95% CI] | capture@5 Δ | 頭二選至少一中 Δ | 結果 |
|---|---:|---|---|---:|---:|---|
| F12 只延長名次窗 | 123 | +0.34 [0.00, +1.06] | −0.34 [−1.76, +1.05] | +0.11 | 0.00 | primary_regression |
| S12 只延長輸距穩定性窗 | 89 | +0.34 [0.00, +1.05] | −0.34 [−1.07, 0.00] | +0.11 | +0.34 | primary_regression |
| FS12 兩者合用 | 160 | 0.00 [−1.39, +1.37] | 0.00 [−1.45, +1.71] | +0.23 | +0.69 | 未調整 RANKING_WIN；Holm 後不成立 |
| CD 同程調整改同場同程 | 128 | −0.34 [−1.06, 0.00] | −1.03 [−2.80, +0.70] | +0.34 | 0.00 | primary_regression |

分數確實接通：F12 改變 2,276 匹 `form_score`；S12 改變 2,259 匹 `consistency_score`；
FS12 改變 2,361 匹 stability 矩陣分；CD 改變 699 匹 distance_fit 矩陣分。唔係死 key／未接 caller。

### FS12 嘅微弱排序訊號

| 排序指標 | 差 | 95% CI | 原始 p |
|---|---:|---|---:|
| capture@5 | +0.23pp | [−0.58, +1.11]pp | 0.665 |
| NDCG@5 | +0.00492 | [−0.00258, +0.01289] | 0.211 |
| competitive recall@5 | +0.16pp | [−0.56, +0.89]pp | 0.673 |
| 實際前三平均模型名次（低較好） | −0.02069 | [−0.04057, 約0] | **0.048** |
| 頭二選至少一中 | +0.69pp | [−0.69, +2.07]pp | 0.463 |

FS12 Gold／Good 點估計都冇跌，各有 4/6 時間塊非負；改善依賴平均模型名次 CI 邊界接近零。
表內 RANKING_WIN 係判決器未套 §6 功效篩選嘅機械輸出：預先量到有資訊嘅 NDCG 只有3/6時間塊非負，
其餘符合時間塊嘅第二指標全部功效不足，所以 **§6 本身亦唔支持一個合資格 RANKING_WIN**。
§8 fixed/refit 兩個機會做 Holm，p **0.096**；四個候選共八個機會 family Holm，p **0.384**。
**唔可以將未調整 RANKING_WIN 當成功。**

## §8 對稱 walk-forward refit

B0/B1 都用 `hkjc_weight_study.py --arm wf_refit`：之前所有賽日、首10 meetings 用現行權重、tau3、L2=2、
production prior、L-BFGS-B maxiter300。擬合雙方都排除同一批死欄位日，同日唔跨入訓練。
程序 SHA256 `053af2d3d2dcfbdd594a7322fea70e050681d88b703b694c95262be82df60777`。

下表係 **B1 − B0**，唔係將重估權重嘅功勞算落候選：

| Arm | Gold Δpp [95% CI] | Good Δpp [95% CI] | capture@5 Δpp | 結果 |
|---|---|---|---:|---|
| F12 | +0.69 [0.00, +1.73] | −0.34 [−2.02, +1.41] | +0.57 | primary_regression |
| S12 | 0.00 [0.00, 0.00] | +0.69 [0.00, +2.08] | +0.46 | ranking_evidence_too_weak |
| FS12 | +0.34 [−0.70, +1.42] | 0.00 [−1.72, +2.03] | +0.92 | ranking_evidence_too_weak |
| CD | +0.69 [0.00, +1.78] | 0.00 [−1.36, +1.39] | +0.57 | ranking_evidence_too_weak |

零作 CI 下界唔等於顯著正面。四個 B1 對 live A0 嘅 live guard 都係 primary_regression；
B0 對 A0 亦未判 WIN。唔可以靠新權重夾帶上線。

## 分層（現行權重，Gold／Good Δpp）

固定用 baseline 首選 SP 分桶，避免候選換首選時改埋樣本。SP／賽後 going **只作評估分層**，永不入候選。

| Cohort | 場數 | F12 | S12 | FS12 | CD |
|---|---:|---|---|---|---|
| 沙田草地 | 186 | +0.54 / 0.00 | +0.54 / 0.00 | +0.54 / 0.00 | 0.00 / −1.08 |
| 跑馬地 | 97 | 0.00 / −1.03 | 0.00 / −1.03 | −1.03 / 0.00 | −1.03 / −1.03 |
| 沙田泥地 | **7** | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| ≤8 匹 | 8 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 9–10 匹 | 15 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 11–12 匹 | 136 | +0.74 / −0.74 | 0.00 / −0.74 | 0 / 0 | −0.74 / −1.47 |
| 13+ 匹 | 131 | 0 / 0 | +0.76 / 0.00 | 0 / 0 | 0.00 / −0.76 |
| 首選 SP≤3 | 68 | 0 / 0 | +1.47 / −1.47 | +1.47 / +1.47 | 0 / 0 |
| SP 3–6 | 130 | +0.77 / 0.00 | 0 / 0 | +0.77 / 0.00 | −0.77 / −1.54 |
| SP 6–10 | 63 | 0.00 / −1.59 | 0 / 0 | −3.17 / −1.59 | 0.00 / −1.59 |
| SP 10–20 | 25 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| SP>20 | **3** | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 首選休賽>75日 | 35 | 0 / 0 | 0 / 0 | 0 / 0 | 0.00 / +2.86 |
| 含初出馬 | 87 | 0.00 / +1.15 | 0 / 0 | 0.00 / +1.15 | 0.00 / −1.15 |
| 新季 | 87 | 0.00 / −1.15 | 0.00 / −1.15 | −1.15 / −1.15 | 0.00 / −1.15 |

另有1場首選 SP 缺值，唔硬填入任何 SP 桶。班次採當場排位表，唔信舊 Logic 嘅 C4 預設；4場班次缺值。
FS12 第三班79場 Good +1.27pp、第二班16場 Good −6.25pp、第五班45場 Gold +2.22pp、第四班136場 Gold −0.74pp。
FS12 好地106場 Gold／Good 各 −1.89pp，好快地115場 Good +0.87pp，好黏地23場各 +4.35pp；31場 going 缺值。
其餘 going 分桶封地5、濕快2、濕慢2、黏地6；不得將極細桶當作安全證據。
分層冇 Gold／Good CI 全負，但唔代表各桶已證明安全，亦唔支持事後只揀好嘅場地／賠率使用。

## 功效、洩漏與驗證

- 候選結果之前先量 production matrix 中性化預算（保留 non-matrix residual）。stability 嘅 NDCG／平均前三名次有資訊；
  capture／recall／頭二選命中嘅預算細過 CI 半寬。distance_fit 五個指標全部預算細過 CI 半寬。
  因此 **CD 排序證據不足屬功效不足，唔係證明同場同程冇資訊**；佢喺現行權重仍冇通過 primary。
- 額外做真 orchestrator 中性化交叉核對（包含重新觸發 SIP 門檻），stability 只有平均前三名次預算超過 CI 半寬，
  NDCG 預算0.01050略低於半寬0.01069；distance_fit 五個仍全部功效不足。
  結果見本機 `exact_power.json`；診斷進一步支持「排序層難判」，唔用嚟事後改 primary／Holm 判決。
- 日期／名次／輸距／場地／途程：只讀匹配馬號＋馬名嘅本地 Facts 正式歷史表，嚴格 `history_date < race_date`。
  不讀海外/PDF表、不讀總獎金、現時評分或今日累積統計；不讀當日結果做特徵。
- 延長窗要求前六仗日期及名次完全一致；缺歷史／輸距／身份不符 → 原計法。全351場有4個馬匹區塊身份不符，已拒絕使用。
  Audit 次數可能包含說明器重算，唔當 unique runner coverage；以上 coverage 用真正 paired leaf/matrix diff。
- A/A 必須 REJECT：PASS。現行 matrix 重建 production picks **290/290 一致**。
- 本機研究腳本4個輸入安全／公式測試通過；`./檢查.sh --quick` 通過，production AU/HKJC golden 各120匹完全一致。
- 數據合約有 baseline 本身已存在嘅 stale-baseline 警告，冇當成候選新增問題，亦冇為呢次研究覆寫基準。
- 完整 `./檢查.sh` 已跑：14套通過，NBA及Agent scripts因沙盒 `ps`／APFS壓縮權限失敗。
  以正常主機權限重跑**整套**NBA（517 passed）及Agent scripts（170 passed、2 expected failures）後全部通過，
  無需改任何產品／測試code。原完整命令退出碼為1，唔將佢寫成一次全綠；失敗原因已由上述重跑清除。
- 最終1,088個輸入檔SHA256逐一重核，全部未變；所有產品code及golden未改。

## 解讀與下一步

1. 六仗唔係已證明最優；今次只否定「呢四種固定改法已證實改善」，未搜索其他窗去救結果。
2. 單獨加舊名次或舊輸距有輕微 primary 代價；合併後只見很弱排序訊號，過唔到多重比較修正，refit 亦未確認。
3. 同場同程值得作人睇嘅背景證據；呢次用佢**取代**現有同程調整唔成功，唔等於額外資訊一概冇用。
4. 泥地只7場，唔可以泛化到泥地馬。應先擴充乾淨獨立樣本；本次唔開測試、唔改權重、唔改模型。

純輸入診斷（唔用賽果擇參）：F12 真正改分嘅2,276匹馬共新增12,015條第7–12仗歷史，
距目標賽日年齡中位數 **273日**，**24.3% 超過365日**。
較長窗確實帶入更舊狀態；呢個只提供解讀背景，唔係已證明未過閘嘅因果原因，亦唔據此追加年齡窗候選。

## 可重現資料

研究程式、每場 dump、完整分層 CI、audit、weights trail 同 input manifest 留本機：
`/private/tmp/hkjc-long-form-study-20261113/`；研究程式喺其 `scripts/`。
按失敗實驗規則，**候選評分程式唔自動 commit**；本次只保存研究記錄，production scoring 無改。

協議 SHA256：`6738d35a2d17cb720e9e1ac8be843d947a160645493ebd4a738c9122ebb3538d`。
資料清單1,088個 Logic／Facts／排位表／結果檔（評分與評估用途分離），SHA256：
`b0a98d9316fd74b285c00262dec9b06cea436f89881a92fa4984dafa18c59849`。
來源檔案已核對未變；這是研究當日資料快照指紋，唔係預測時已凍結嘅 manifest。
本機研究腳本 SHA256：

- `hkjc_long_history_study.py`：`dc2e6df8b6de8ea7cb57c41b1bbbfc7fa9ebe56f836c56dee04dba464a8c6c5b`
- `hkjc_long_history_report.py`：`113da03203a013b6571268a116cfeb81c1de6dca18077faad558684eb5a96127`
- `test_hkjc_long_history_study.py`：`90e4606a6cd441e7571a12dc43465be75576aa58ceaa2c6b6079beae7d4f0601`

```bash
# 在 baseline e6e45aa1d checkout，抄 .wongchoi_*root，所有輸出只寫 scratch。
export PYTHONDONTWRITEBYTECODE=1
export HKJC_RESEARCH_REPO="$PWD"
S=/private/tmp/hkjc-long-form-study-20261113
H=.agents/skills/hkjc_racing/hkjc_reflector/scripts
python3 "$H/hkjc_eval_harness.py" run --until 2026-10-10 --dump-matrix --out "$S/base.jsonl"
python3 "$S/scripts/hkjc_long_history_report.py" baseline "$S"
for A in F12 S12 FS12 CD; do
  HKJC_HISTORY_ARM="$A" HKJC_HISTORY_AUDIT="$S/$A.audit.json" \
    python3 "$H/hkjc_eval_harness.py" run --arm "$S/scripts/hkjc_long_history_study.py" \
    --until 2026-10-10 --dump-matrix --out "$S/$A.jsonl"
done
python3 "$S/scripts/hkjc_long_history_report.py" prepare "$S"
for A in base F12 S12 FS12 CD; do
  python3 "$H/hkjc_weight_study.py" "$S/${A}_clean.jsonl" --arm wf_refit --out "$S/${A}_wf.jsonl"
done
python3 "$S/scripts/hkjc_long_history_report.py" report "$S"
python3 "$S/scripts/test_hkjc_long_history_study.py"
```

臨時研究程式唔係永久 repo 工具；如 scratch 被清走，以協議完整固定公式重建，唔准藉重建調窗／門檻。
