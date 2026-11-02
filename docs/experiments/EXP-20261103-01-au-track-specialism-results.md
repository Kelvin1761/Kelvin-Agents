# EXP-20261103-01 結果：場地與地況適性改為「相對生涯」專長 —— 三個 arm 全部 REJECT（SP 差少少）

- **預先登記**：[protocol](EXP-20261103-01-au-track-specialism-protocol.md)（`a18ae54e`，量度之前已入 main）。
- **baseline**：`a18ae54e`；語料 08-05 起 **3,302 場**；v3 `fixed_rule`，賽日 bootstrap 2000 次、seed 7；三個 arm Holm。
- **研究碼**：分支 `claude-track-specialism-exp-20261103`（`track_going.py` arm flag `WC_AU_TRACK_SPECIALISM_ARM`、
  `scratch/au_track_specialism_judge_20261103.py`）。**冇入 main，live 冇改。**
- dump：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/track-specialism/{BASE,SPG,SP,SPW}.json`，判決 `judge.json`。

## 結果

| arm | 郁咗場數 | Gold | Good | top3_capture@5 | NDCG@5 | 前五 AUC | verdict |
|---|---|---|---|---|---|---|---|
| SPG（好地日讀好地往績，現行規則） | 1,551 | +0.24pp [−0.03, +0.54] | 0.00 | +0.010 | −0.053 | +0.037 | REJECT（ranking 證據唔夠） |
| **SP（相對生涯專長）** | 3,115 | **+0.27pp [−0.21, +0.72]** | **−0.03pp [−0.63, +0.56]** | **+0.222 [+0.009, +0.429]** | +0.152 [−0.008, +0.312] | **+0.143 [+0.005, +0.266]** | REJECT（primary_regression：Good 點估計負） |
| SPW（SP ＋ 剷濕地 overlay） | 3,248 | −0.06pp | −0.39pp | +0.293 | +0.162 | +0.082 | REJECT（primary_regression） |

（ranking metric 單位：pp。Holm 調整後三個 arm p 都係 1.0，因為冇一個 verdict 係 WIN。）
冇任何預先聲明分層 CI 全負。

## 點讀

- **SP 係今次最接近過閘嘅**：兩個排序指標 CI 全正，Gold +0.27pp（約 +9 場），但 Good −0.03pp（約 1 場）令佢觸發 primary_regression。
  形態同 EXP-20261102-10 嘅 GO（剷地況往績 ②：排序 CI 全正、Good −1 場）一樣 —— 場地呢個維度喺 Gold／Good 層面嘅功效
  細過閘門解析度。照登記規則 **REJECT**；唔准睇完結果改 K／P0／S 或者 arm。
- **SPW 證實濕地 overlay 仲有用**：剷咗 overlay，Soft 5–6 Gold −0.88pp、Heavy Good −2.07pp（CI 都跨零但方向一致）。
  即係「今日地況專長」放入 track_score 唔夠代替 overlay；兩樣唔係重複。
- **SPG**：好地往績照現行規則入分，Gold +0.24pp、Good 0，排序指標冇改善。2026-08 Sportsbet 矩陣審計（`39155166d`）
  試過同一件事、過唔到 terminal 閘；今次喺 08-05 起乾淨語料再量，結論一樣：唔夠證據。
  **更正**：之前同用戶講「好地往績係抽取食咗標籤嘅 bug」唔啱 —— code 註釋寫明係刻意唔入分（舊 A/B 唔過），唔係 bug。
- **leaf AUC 升（+0.019）冇轉化成 Gold／Good**：同 [[leaf-auc-gains-do-not-convert-to-ranking]] 嘅改正版一致 ——
  排序指標有改善，但場數指標分唔出。

## 洩漏核對（預先登記承諾）

08-05 起 1,875 匹當日贏馬，下次出賽時 `career_record_line` 頭馬數**全部**多咗（0 匹冇多）→ 賽前生涯紀錄冇計入當日場。
相鄰出賽對入面得 3 對生涯出賽數冇增加（資料雜訊，量級可忽略）。

## 下一步（用戶決定）

- 照規則：REJECT，live 唔郁。
- 選項：SP 以 **USER-ACCEPTED EXPERIMENTAL LIVE** 上線 + forward 監察（同 EXP-20261102-08 檔位一樣做法）。呢個係用戶判斷，唔係閘門判決。
