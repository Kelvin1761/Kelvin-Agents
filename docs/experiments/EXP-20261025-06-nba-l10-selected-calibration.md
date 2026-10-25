# EXP-20261025-06：80/80 基準、stats 消融及選中腿校準

## 決定

**NEEDS MORE TESTING；不取代現役模型。簡單 logit offset 校準未獲保留支持。** 80/80 是後續研究的固定候選基準，不能聲稱已證明新配方優於現役C或可盈利SGM。研究code只保存非main分支，沒有改正式C、EV、selector、報價、Dashboard或排程。

現役`nba_selection_policy.BANKER`本來就是L10≥80%、L5≥80%，另有CoV、分鐘、近期線位buffer等規則；組不到才進70/70 fallback。這次「加80/80」是補回EXP-04研究單腿診斷缺少的穩定條件，不是第一次加入正式穩膽。比較對象為C概率在同一簡化單腿selector下的診斷，不冒充完整production SGM重播。

## 證據與固定規則

Base `2429d0fa2c6a9a05f0bdda7e9fb9360b1074ce05`。先搜尋EXP-04、05、舊L10診斷及calibration研究。AU/HKJC評估合約的賽馬名次KPI不能套作NBA單腿promotion閘；本輪只作有時間隔離的開發診斷，不另定promotion把尺。

外置根`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-nba-l10-calibration-20261025`。Protocol.json SHA256 `1d316950099a71333c29ef89a2996e63b78e9c0b530dced1be87aa51255ef917`，先於本輪計算寫入。沿用EXP-04原OOF.csv，SHA256 `0ff2601f6eed31c1971f81546a0e3c144b9327a10939f43a1c953f96f941e0b0`；5,305列、32事件、15日期，**已觀察的開發集，非新holdout**。原保留尾5日期完全不開。沿用已核來源的OOF frozen artifact，不聲稱本輪重新查驗全歷史原始來源。完整來源契約見EXP-04。

固定L10≥80%、L5≥80%、n_history≥10；所有eligible原列均為10場。單腿原價1.15–3.5、正預測EV、每事件最高EV及固定身份tie，全部候選重新排序。不是只刪原32條。full/core與四個去block版本均來自先前同一套walk-forward模型，沒有本輪重訓／search。

1023列符合80/80；加入原價區間後同一eligible pool為428列、32事件。歷史缺少potential assists／rebound chances及完整對手容許統計，**full不是剛新增tracking全接入後的模型**，不倒填今天資料。

## 同一80/80規則下的單腿結果

| Probability model | 選中場數 | 命中 | 高估pp | 平均價 | 單腿flat ROI |
|---|---:|---:|---:|---:|---:|
| core，L10分布與平滑命中率 | 32 | 32中19 | 12.03 | 1.726 | −3.56% |
| full，既有分鐘／角色／對手／賽程 | 32 | 32中22 | 7.73 | 1.648 | +9.84% |
| full去分鐘 | 32 | 32中23 | 4.43 | 1.666 | +16.94% |
| full去角色 | 31 | 31中19 | 14.68 | 1.681 | −0.77% |
| full去對手 | 32 | 32中23 | 1.85 | 1.680 | +17.56% |
| full去賽程 | 32 | 32中22 | 6.10 | 1.657 | +10.06% |
| 現役C概率，同一單腿規則 | 6 | 6中4 | −7.12 | 1.718 | +13.83% |

不能看「去對手」1.85pp或ROI最大就採用它。去分鐘／去對手與full的同eligible pool Brier差異CI跨零，且這些是已看過結果的多個消融。對手資料缺失亦不代表對手防守沒有用。保持所有失敗／不確定結果，不組合刪特徵救候選。

full相對core同場配對命中+9.375pp，日期cluster描述95%CI約[−2.94,+23.53]pp；flat ROI差+13.41pp，CI[−5.33,+36.08]pp。點估計有方向，但沒有確定勝出。與C共有的6事件，full為6中3、C為6中4，不可以拿full的32中22同C的6中4直接判勝。

在**相同428列**，full Brier .214350、core .215006、C .206181（較低較好）；full−C +.008169，描述CI[+.001194,+.014995]。C擬合／檢視過部分歷史，**不是獨立C確認試驗**，不能反過來宣布C已證明較好。至少目前沒有證據取代C。

## 只用過去選中腿的校準

預登記共享單調變換`p'=sigmoid(logit(p)+b)`；b只fit較早日期raw-full已選中一腿／事件，Bernoulli log-loss＋4*b²/2收縮；不fit slope、不分stat細調，不使用市場價作概率輸入。價格僅用於固定EV選擇。至少6個訓練日期、12事件，US日期留2日label embargo。這是保守日曆隔離，非歷史結算可用時間逐筆證明，仍屬研究限制。

只有2026-05-04至05-15的8日期／15事件有足夠前置樣本。不得將以下15場同之前32場混比。

| 同一固定raw-full選中15腿 | 原概率 | 歷史offset校準後 |
|---|---:|---:|
| 實際命中（不改腿） | 15中11 | 15中11 |
| 平均概率 | 73.98% | 65.81% |
| 高估pp | +0.65 | −7.53 |
| Brier | .206563 | .210807 |

校準−raw Brier +.004244，95%日期CI[−.042050,+.045131]。同229列eligible pool由.205194變.213917；不是改善。過去偏高不代表未來偏高同幅；不能直接手扣7.7pp。

校準後重新依EV選擇，剩11場、11中8、平均p70.89%、低估1.84pp、單腿ROI+12.18%。不同cohort／覆蓋率，不能拿這個小gap覆蓋固定集合上較差的結果或宣稱校準成功。這個offset候選不部署，也不改ridge／窗口補救。

## 下一步與保存

固定80/80研究候選與現役C並行，保留完整eligible pool及先於結果凍結的選中腿／模型ID／原生價格。新tracking資料已由EXP-05接日常immutable snapshot；要等有真賽前資料及Final labels後，逐prop分開測機會量／效率／分鐘及校準，不能用今天資料回填四月。新候選在未見資料確認前不替換C；SGM另驗聯合概率、相關性及原生報價，單腿ROI不是SGM ROI。

可重現（本研究分支）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/nba_ml/nba_l10_selected_study.py \
  --protocol <外置根/Protocol.json> --output <全新輸出目錄>
python3 -m pytest .agents/scripts/tests/test_nba_l10_selected_study.py -q
```

五項針對測試驗證完整池重排、EV維持、樣本不足、單類別收縮、單調性、未來label改動不影響先前概率及日期embargo。完整檢查、研究分支SHA、保存結果見外置根Final_Verification.json。本輪不會進main或啟用新公式。
