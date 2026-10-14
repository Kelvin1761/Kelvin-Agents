# HKJC 逐場權重診斷 — 2026-10-13

**主要發現：失手唔係全部靠權重修到。197 場重播失手中，有 45 場任何非負配重都達唔到 Gold 或 Good；44 場要反轉至少一個訊號方向先做到。呢個係事後診斷，未證明任何改動能改善賽前預測。**

## 樣本同 baseline

- 全庫對齊：362 場 / 4,500 匹；研究納入 272 場，日期 2026-04-12 至 2026-09-06。
- 原本早期日期274場，2場label invalid／不足5匹排除。2026-09-09起全部隔離；唔讀佢哋做權重搜索／KPI。
- baseline 係獨立現行 RacingEngine 重播，七維原始 matrix、顯示尺換算、固定 residual；初出馬分數鎖定。**未重施 meeting SIP，唔係完整 live orchestrator。**
- canonical Gold=實際前三全入模型Top4；Good=模型Top2都上名；miss=兩項都唔中。
- baseline Gold 38/272（13.97%）、Good 61/272（22.43%），兩項至少中一項75場，失手197場。
- 舊存檔271/272場完整排序同本次重播有差異；舊存檔失手206場，其中176場重播仍失手，30場重播達標；另有21場由存檔達標變重播失手。**唔可以把呢份baseline KPI當成舊published prediction KPI，亦唔可以叫重播改善。**
- 舊存檔曾重算，現行先驗亦未逐欄證明PIT；正式績效／promotion leakage判決係FLAG。

## 可救返幾多

| 權重範圍 | 197場失手：可達Gold或Good | 可同時Gold＋Good |
|---|---:|---:|
| 每維±5個百分點、非負、和1 | 54（27.41%） | 12 |
| 任意非負、和1 | 152（77.16%） | 77 |
| 容許[-1,1]負權重、和1，純診斷 | 196（99.49%） | 158 |

因此：54場只需有限改動有解；98場只有大幅配重先有解；45場非負配重無解。唔係「77.16%預測命中率」—— 每場都已經睇咗自己賽果。

每場另有local／positive全場排序logistic fit（temperature=6、L2=0.02），只係固定surrogate objective嘅解，唔聲稱係所有離散排名指標嘅最佳解；逐場CSV同JSON保留權重同排序。

只有5/272場可以用非負線性配重完整複製全場名次。賽果係一次隨機實現，呢個唔代表模型應該做到逐匹完美排序；只係界定現有表示嘅事後容量。

LP枚舉Top2上名pair同Top4容許嘅外圍馬，margin=0.01顯示分。joint witness取所有可行case嘅最小L1；單項witness有時重用joint解，只證可行唔聲稱單項最小。不可行只限本次線性範圍、固定residual同初出馬鎖定。

## 重複模式

### 1. 形勢高權重值得查，但直接減權未有成功證據

77場可用非負配重做到聯合Gold+Good嘅失手，56場（72.73%）最小改動witness需要減race_shape；中位減8.93個百分點。stability有40場要減，form_line有33場要加。好多維度中位改動係零，唔存在一組清晰通用最佳權重。

呢個方向同EXP-20260928-06舊refit相似；但當時減shape嘅候選未守住OOS Gold／Good。因此應先查shape輸入同跨venue／race-context語義，唔應直接部署全局減權。

### 2. 救唔返嘅45場，多個訊號同時唔識上名馬

以下係場內「實際前三 vs 其餘馬」配對AUC，平手算0.5、每場等權。0.5係冇方向；低過0.5係呢批賽果上方向相反。

| 維度 | 達標75場 | 失手197場 | 非負配重救唔返45場 |
|---|---:|---:|---:|
| sectional | 0.685 | 0.540 | 0.442 |
| trainer_signal | 0.713 | 0.625 | 0.512 |
| stability | 0.768 | 0.630 | 0.511 |
| race_shape | 0.723 | 0.527 | 0.476 |
| class_advantage | 0.710 | 0.590 | 0.460 |
| horse_health | 0.603 | 0.515 | 0.428 |
| form_line | 0.587 | 0.543 | 0.483 |

呢啲cohort係按賽果／模型失手選出，存在selection bias，唔可以當訊號本身無效嘅因果證據。佢哋用嚟揀raw-source核查case。

44場只有signed有解，選到嘅單項witness中，race_shape有17場負權重、stability14場、form_line14場；訊號唔係只壞一個維度，而且解可能唔唯一。

### 3. 分辨力空白係具體調查方向

段速在70/272場係全場常數（達標20/75、失手50/197），即失手比例唔比達標高。救唔返45場有15場段速常數、7場form_line常數、4場stability常數。單靠「冇段速」唔足以解釋整體失手；要分開本身冇歷史同抽取／轉換漏資料。

另外發現4場／9匹馬：last_6_finishes明文寫「初出」，但冇is_debut／debut_runner／DEBUT標記；其中3場失手，2場非負亦救唔返。引擎只睇後者，所以本次重播亦沿用佢嘅身份判斷。呢個係可核對嘅archive身份矛盾，需對原racecard／profile確認；未證實係live現役bug。詳見debut_source_flags.json。

例：2026-04-12沙田R1，段速、stability、form_line、class、health全部無場內分辨力。雙劍合璧實際第二，重播第六；主要剩trainer_signal同shape識分馬；6匹全部寫「初出」但冇正式初出標記，唔應把資料空白當成已有歷史馬嘅模型無效。呢場連signed聯合Gold+Good都無解，但signed單項可以達標，唔可以把兩種目標混埋。

唯一連signed都達唔到任何一項：2026-05-09沙田R1，10匹中6匹初出；本實驗刻意鎖定初出馬分數。呢個首先係初出馬模型／鎖定範圍調查case，唔可以當成「所有訊號都無用」。

## 場地分層

| 場地 | 場數 | 失手 | 失手中非負亦救唔返 |
| 沙田 AWT | 7 | 7 | 2 |
| 沙田 Turf | 176 | 123 | 24 |
| 跑馬地 Turf | 89 | 67 | 19 |

AWT只有7場，唔足以獨立調formula或斷定泥地模型問題。

## 修正嘅證據路徑

1. 先對45場逐個查馬匹身份、profile歷史date join、non-finish狀態、段速來源同中性fallback；尤其全場常數case。同時抽matched成功場，唔只查失手。
2. shape逐項拆出draw、PIT context、surface、distance／trip，核對賽前來源。現有版本曾經變更，需以原contract重播；唔可以由今天先驗填舊賽事當賽前證據。
3. 分開「訊號缺失／表示錯誤」同「配重錯誤」兩個假設；每個修改獨立ablation。初出馬另外處理。
4. PIT同原published ranking重播一致先進入時間fold；dev合格先開原鎖定terminal，完整Stage4 gate不變。

今次冇改模型、golden、data-contract baseline、dashboard、排程，冇commit／push／activate。研究工具同逐場witness已保存。

## 重現同檔案

- `results.json`：272場baseline、三個範圍可行性、各場權重witness、全場排序fit、podium、欄位健康、hash。
- `race_diagnostics.csv`：逐場可篩選表；所有失手場都保留，包含救唔返嘅場次。
- `patterns.json`：場地同訊號cohort統計。
- Frozen CSV在repo `scratch/hkjc_race_weight_oracle_20261013/dataset.csv`；SHA256見results.json。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_race_weight_oracle.py --dataset scratch/hkjc_race_weight_oracle_20261013/dataset.csv --output docs/audits/hkjc-race-weight-oracle-20261013/results.json
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_oracle_report.py --dataset scratch/hkjc_race_weight_oracle_20261013/dataset.csv --results docs/audits/hkjc-race-weight-oracle-20261013/results.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s docs/experiments/patches -p test_hkjc_race_weight_oracle.py -v
```

驗證：8個oracle soundness tests PASS；quick check PASS。完整repo檢查正常權限重跑exit0、14個suite全部PASS（首次sandbox排程日誌寫入失敗，未修改排程code）。
