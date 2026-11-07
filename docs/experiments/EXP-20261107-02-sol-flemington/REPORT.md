# Sol 獨立分析與旺財對照：2026-11-07 Flemington 全日九場

**結論：這天 Sol 的頭四覆蓋較好，旺財的首選頭馬較好；找到一個可重現的重複賽績問題，以及幾項已知設計取捨，沒有證明應改模型權重。**

## 做了甚麼

用戶指定 `Sol LLM`，使用 configured model **gpt-6.1-sol** 的獨立 fresh-context agent，先讀賽前資料、完成排序，再揭盲比較。
完整逐駒理由、支持、反證、步速情境、信心及證據引用在 [Sol_Analysis.md](Sol_Analysis.md)；機器可讀版本在 [Sol_Predictions.json](Sol_Predictions.json)。
這些是可審核的分析摘要，不是逐字私有內部思考過程。

- **9 場、105 匹 active runner** 全部分析，核對 466 個 runner evidence 引用均指向正確輸入檔案的存在行號。
- 使用最後一份全日開跑前快照：**2026-11-07 10:48:00 悉尼時間**，第一場 **12:40**。
- 18 個 Racecard/Formguide 檔案逐一匹配 manifest SHA256；往績日期全部早於目標日。移除目前及歷史賠率、ROI、Fav；保留獎金與正式往績。
- Sol 沒有收到父對話、旺財排序、Logic、Facts、CSV、賽果或網頁。父 agent 檢查 manifest 時已見過旺財推薦，這點在 [protocol](protocol.md) 預先披露；獨立初選由 fresh Sol 完成。
- 九場 JSON/Markdown 完成並 hash-lock 後，才讀賽果。Sol 自報沒有認出既有結果；**無法排除預訓練記憶，也不是當時發出的預測**。這是 retrospective input-blind diagnostic。
- 同一份快照的旺財原排序，沒有用賽後重評替代。全部 105 匹賽果身份匹配輸入，無缺漏或晚退，兩方分母相同。

鎖定 SHA256：JSON `50c061150afdca6c5f555dd9564656a93e7b52d2eeb5af3da3f476145d7af0a4`；Markdown `1b936331fa8033ccbd25370978d2f8c6ea01a628969dfc74cfd06b0d834dbb1b`。
揭盲後 Sol 另寫 [Sol_Postreview.md](Sol_Postreview.md)，沒有修改初選或信心；父 agent 再核對原 SHA256 不變。

## 結果

| 指標 | Sol | Wong Choi |
|---|---:|---:|
| Gold：實際前三全部在頭四 | **4/9** | 1/9 |
| Good：首兩揀都上名 | **3/9** | 2/9 |
| Pass：首三揀至少兩匹上名 | **4/9** | 3/9 |
| 首選頭馬 | 2/9 | **3/9** |
| 頭四捕捉實際前三 | **16/27** | 13/27 |
| 頭馬在頭四 | **6/9** | 5/9 |

指標使用 repo canonical `shared_racing/eval_metrics.py::race_metrics`。不另創「Good」定義，不報未預先定義投注法的 ROI。

| 場 | Sol 頭四（馬號，固定原次序） | 旺財頭四 | 實際前三 | 頭四捕捉 Sol / 旺財 |
|---|---|---|---|---:|
| R1 | 4 / 5 / 7 / 13 | 4 / 5 / 3 / 1 | 4 / 7 / 5 | **3 / 2** |
| R2 | 2 / 13 / 1 / 3 | 2 / 1 / 13 / 11 | 13 / 4 / 7 | 1 / 1 |
| R3 | 5 / 4 / 3 / 8 | 4 / 5 / 8 / 1 | 4 / 9 / 6 | 1 / 1 |
| R4 | 6 / 8 / 1 / 5 | 2 / 6 / 9 / 12 | 4 / 6 / 11 | 1 / 1 |
| R5 | 5 / 4 / 8 / 15 | 4 / 5 / 15 / 7 | 12 / 5 / 13 | 1 / 1 |
| R6 | 6 / 7 / 4 / 3 | 7 / 6 / 3 / 8 | 11 / 12 / 9 | **0 / 0** |
| R7 | 8 / 2 / 1 / 3 | 8 / 2 / 1 / 5 | 8 / 2 / 3 | **3 / 2** |
| R8 | 1 / 5 / 10 / 3 | 1 / 10 / 5 / 3 | 5 / 1 / 3 | 3 / 3 |
| R9 | 6 / 10 / 2 / 19 | 5 / 10 / 6 / 2 | 19 / 10 / 2 | **3 / 2** |

完整馬名、頭馬模型名次及原始指標在 [comparison.md](comparison.md) / [comparison.json](comparison.json)。
差距主要是 R1 Goddess Kay、R7 Buckaroo、R9 Lawborough 三匹進入 Sol 頭四；R8 兩方頭四集合相同，不能冒認為額外獨立成功。

## 先分清：哪些是資料問題，哪些是模型取捨

### 1. 已確認：場地贊助名前綴造成同一仗重複進入評分資料

R9 Torsheen 與 Royal Rendezvous 各有兩行 **2026-01-21、R6、1300m**：

- `Sportsbet Sandown Hillside` 與 `Sandown Hillside`。
- 同馬、同日期、同場次、同路程、同騎師、同名次、同輸距、同時間；只是場地贊助名前綴及價格欄不同。
- Torsheen：凍結輸入 R9.md **F0185 / F0190**；兩行都在 snapshot `pf_metrics.pf_runs`，同為 `own_l600_delta=1.3325`。
- Royal Rendezvous：**F0625 / F0630**；兩行都在 PF，亦佔用了 `form_quality.runs` 第五、第六項（同日 5/7、各有序列權重 0.3/0.2）。

這不只是顯示重複，已到評分輸入。`data_prep._parse_formguide_pf_metrics` 逐行 append、`refresh_form_quality` 從完整往績順序取證據；本快照顯示重複未被隔離。
Torsheen 的這兩筆不在最近六場 form-quality 內，**不能說其 +11.01 狀態貢獻由這個重複造成**；PF 仍重複。沒有量度去重後排名，也沒有修生產資料。

**優先處理方向：資料身份與去重審核。** 先核對原始事件 ID、場地別名及全語料影響，再按資料修正 gate 評估；不能只因這天失手就調權重。

另有 Soldi 同日試閘疑似重複、Rusty Pearl `finish:4/1`、部分試閘 L600 可疑值；詳見 [input_anomalies.json](input_anomalies.json) / [duplicate_audit.json](duplicate_audit.json)。
試閘時間離群只是篩查旗號，未逐個查上游前不稱確證錯值。Nation's Call、Litzdeel、Attrition 等已跑足六場，現役 `trial_performance_applies` 會隔離其試閘速度；**不能用這些異常解釋它們的正式速度分失手**。

### 2. 已確認：受阻／走位文字是兩方共同缺失

同一份輸入有 963 條歷史賽績，963 個 Stewards、963 個 Video、963 個 Note **全部空白**。
抽取器 `claw_sportsbet_form.py:1311` 寫空欄；Facts `_format_notes` 即使收到 stewards 亦沒有列出該內容。
因此 Sol 也不能知道具體受阻。空白不等於沒有受阻，不能靠 LLM 自行補故事。

這是來源／資料傳遞缺口；本輪沒有接入新 Stewards 來源，也沒有用當日賽後評語改回初選。

### 3. R1 / R7 / R9：正面證據已有，合成之後沒有佔先

| 個案 | Sol / 旺財 / 實際名次 | 旺財已知的證據與分數 | 可下的結論 |
|---|---|---|---|
| R1 Goddess Kay | 3 / 6 / 2 | trial_score 82、preparation_score 64.38；備戰 +0.41，但騎練 +1.86，The Chancer 騎練 +6.35 | 不是漏讀試閘；新馬大量中性欄位下，騎練差異可左右排序 |
| R7 Buckaroo | 4 / 6 / 3 | 最新一哩 2/11 已在近績；狀態 −2.62、速度 −1.48，track +0.86 | 近期專項回勇與較長窗口的取捨；不是沒讀到亞軍 |
| R9 Lawborough | 4 / 7 / 1 | 最新1100m勝已入近績；狀態 +2.74、速度 +1.41，騎練 −2.00 | 同程近勝沒有漏抽，但其他項與競爭馬舊分數影響前四位置 |

R9 Torsheen 第一的總分 79.7231，狀態貢獻 **+11.01**；六場 form-quality 都在二至四月，最新仍有序列權重 1.0。
系統其實已標示 **196 日久休後首仗、狀態尚未獲本輪正式賽驗證**；Sol 沿用了來源 Days 欄的 195 日說法，精確日期差應用系統 196 日，原稿照保留。
這是「風險已知但沒有在這些分數內作日曆時效折減」，不是模型忘記久休。`stability.py` 固定按近六次賽事序列加權，不按過去幾個日曆月衰減；health 是 report-only。

**上述是本日有利差異，未證明新的權重或時效公式會 OOS 改善。** Sol 首選 Educated 只第十一，而旺財首選 Torsheen 第六，Sol 不能把 R9 Gold 當成首選判斷也較好。

### 4. 已確認的排名通路與設計限制

現役 `dimensions.py` 的六個有效維度只讀 form_quality、pace_figure、騎練組合、rating/class、track、preparation/trial_speed。

- `trial_score`、`formline_score`、`distance_score`、`health_score` 本身不是直接排名 leaf；試閘、距離、對手強弱仍可有其他間接路徑。不能說完全沒有這些資訊。
- `race_shape` / `form_line` 維度沒有 ranking coefficient。draw overlay 是檔位項，不能當成已建模前領／後上步速互動。
- 對有官方評分的馬，`class_weight` 以評分為主；`weight_score` 顯示用。缺官方評分的讓磅代理可用分配負磅，**不是負磅全面沒作用**。對手彼此的「上次及今次相對磅差」沒有直接專用通路。
- R6 / R7 高班實績 overlay 的 field_count 都只有 2，門檻為 ≥3，故整場該 overlay 中性；班次仍透過官方評分和獎金近績等其他項表示。這個 sparse fallback 不是已證實的 bug。
- `pace_perf` 的 `basis=own` 是 Sportsbet 賽事 L600 加輸距推算，不是實測個別馬末段。這是已知限制，前輪研究已測，不重包裝成新發現。

這些部分過去有消融／退役證據：見 EXP-20261013-11（步速）、EXP-20261014-01/02（減磅與實負磅）、EXP-20261016-71（轉程）、EXP-20261102-04（班次重建）。
**沒有直接通路不等於應補一條。** 本輪不推翻歷史實驗、不把九場當成擇參樣本。

## Sol 自己的失手，同樣要保留

- **R3：** Sol 用兩次直接對賽將 King Pedro 升首，實際第七；旺財首選 Pinhole 勝。
- **R4：** 兩方都將頭馬 Watchme Win 排第十；Sol 升 Grand Impact 至第二，實際第十三。不能拿一場對賽先後作穩定能力等式。
- **R5：** 兩方都將 Sun Gift 排第十五，它勝出；Sol 同樣看重三日再出疲勞及前仗重地落敗，低估了本場／2000m既有表現。Sol 第三 Vivy Air 實際第十五、第四 Ocean Bay 第十二。
- **R6：** 兩方頭四全失。Sol 排 Point Barrow 第六、Plaintiff 最後、Skybird 第七；旺財第七、第十、第九。Sol 原信心 medium 不改成 low。近期同程連勝與本場適性有記錄，但兩方都偏向較高班的既有對手。

R5 的相對磅位取捨（Too Darn Discreet 相對 Soverato 改善7kg）令 Sol 首選亞、旺財首選包尾，但它不能遮掩兩方漏頭馬，更不能證明固定 kg-to-length 公式。
R3、R4 正是直接對賽推論失手的反例。沒有把 Sol 有利的敘述一律搬進模型。

## 賽果與外部核對（全部在鎖檔後）

本機 `Race_Results_Reflector.md` 提供全部 105 匹的完整名次，與快照身份一一匹配。
VRC 官方[全日賽事回顧](https://www.vrc.com.au/latest-news/tab-champions-stakes-day-racing-and-highlights/)亦對應九場頭馬，並確認 R6 Point Barrow／Plaintiff／Skybird。
VRC 的 Sun Gift 段落轉述訓練員賽後解釋：前仗不適應變差地況，今次較乾場地較合適；**此說法只作賽後核對，未證明下注前已有同一資訊**。
不能把這段解釋當成 Sol 本應知道、或模型新增修正一定有效的證據。

## 下一步及保存

1. 優先做已證實的同一事件別名重複、矛盾試閘與缺失／零值語意的全語料資料審核。
2. 若再研究模型，先讀已有實驗，再預先登記多場次、相同資訊與固定指標的比較；研究相對分／日曆時效／轉地況交互，不用本九場定門檻或權重。
3. 若再比較 LLM，記錄其全部失手，並使用真正未見的後續會議；本日只是假說來源，不是 promotion／forward test，也沒有新測試排程。

**沒有模型、權重、排程、原始賽事檔或 dashboard 改動。** 全部研究保存到獨立分支，不 merge／deploy。
研究輸入、完整 attribution、準備與比較 scripts、原始驗證 logs 另存於外置碟：
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-sol-flemington-20261107/`。
小型 source/hash receipts 與全部 Sol 分析、比較、覆盤保存在本 dossier。

驗證：`./檢查.sh --quick` 通過；完整 `PYTHON_BIN=/Library/Developer/CommandLineTools/usr/bin/python3 PYTHONDONTWRITEBYTECODE=1 ./檢查.sh` 在 sandbox 外 **exit 0、16 suite 全 PASS、805 秒**。沒有略過或修改測試。
母 repo source commit `6525f23eb`；預測鎖、輸入／賽果 hash 及方法在 receipts/protocol。此回顧沒有統計效力或 LLM 優越性宣稱。
