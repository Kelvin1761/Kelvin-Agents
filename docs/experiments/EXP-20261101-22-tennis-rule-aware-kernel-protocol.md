# EXP-20261101-22：F02 明示規則 point kernel 協議及語義負例

狀態：研究 kernel 已實作，固定255個解析／獨立MC比較全部通過；沒有接入現役。tournament/year/draw resolver及整合影響驗收仍未完成，F02不能標全部完成。沒有改現役模型數學、正式判決規則或投注 family。

## 可重現的缺口

現役 `_play_set` 在 6–6 後用 hold ratio 作一個勝負抽樣並返回 7–6／6–7。控制十三次 RNG draw 為零、hold_a=hold_b=.8、A 先發：十二局均保發後，函式第十三次抽樣返回 7–6。這是普通 tie-break set 的終局，但不是明示 2019 Wimbledon adult singles deciding set 的終局（當屆要到12–12），亦不是 advantage set 的終局（需領先兩局）。這是函式適用規則的負例，不是某場真實比賽、估計誤差或對舊近似作盈利判決。

原 F02 的22個 MC/DP 比較是與同一 hold-ratio 近似相符，不能由此宣稱支持 tournament/year 規則。新工作重用已驗證的 point TB oracle，不把原22 case重跑當新實驗，也不把 hold probability 靜靜反推成已識別的 point skill。

## 官方來源與限制

- [ITF 2026 Rules of Tennis](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)：Rule5/6/7/14、Appendix VI，用於點／局／盤終止、1-2-2及跨盤發球；match tie-break替代盤與6–6後final-set tie-break須區分。
- [2026 Grand Slam Rule Book](https://www.itftennis.com/media/5986/grand-slam-rulebook-2026-f2.pdf)，Tournament Regulations I.K–L，PDF page12：區分成人男單正賽BO5及其他draw，規定final-set十分快搶十。
- [AO 2019公告](https://ausopen.com/articles/news/final-set-tiebreaks-australian-open-2019)，2018-12-21：成人單打決勝盤6–6後10分，其他draw另分。
- [WTA引述Wimbledon公告](https://www.wtatennis.com/news/1438560/wimbledon-announces-final-set-tiebreak-from-2019)，2018-10-19：2019起決勝盤12–12後7分。
- [AO scoring guide](https://ausopen.com/articles/news/guide-scoring-tennis)，2024-12-19：敘述AO2019及由Roland Garros2022起的統一改動。

官方2026 PDF 可經 web PDF reader核對，但直接擷取均收到212-byte非PDF回應，保存為failed，沒有宣稱保存原始PDF或取得其原文SHA。US Open2022直接頁有不可讀／簡化回應，不把HTTP200或body hash當全文已核對。AO guide另通過三個原文存在檢查並保存URL、hash及retrieval time。2025 rulebook原URL讀取失敗亦保留；不得以此默認補出已驗證2025資料。

固定歷史 registry 沿用 `f01-full/final-source/slam_rules.json`，只涵蓋2011–2024成人單打main draw。未知年／賽事／draw須明示unsupported；2026是分開明示的研究overlay，不自動改歷史registry。規則來源可讀不代表player資料的發布時計、exposure或serve model已合格。

## 新 kernel 的事前設計

獨立研究程式，現役預設不變。輸入明示 iid service-point p_A/p_B，普通盤7@6，決勝盤另傳7@6、10@6、7@12或advantage。不得由hold靜靜推斷point能力；第一發、BO3/BO5、決勝盤選取及跨盤service parity分開建模。

Advantage set需保存解析geometric tail及終局規律，不能截斷後假裝finite terminal mass=1；winner probability可解析收斂，joint props仍須F10另行證據。MC使用自己的score/service狀態轉移，不直接抽DP終局分佈。

| probability comparison | 固定case數 |
|---|---:|
| 標準game（p=.45/.60/.75） | 3 |
| TB（9對p × 7/10分 × 兩個首發） | 36 |
| set（9對p × 四規則 × 兩個首發） | 72 |
| match（上述 × BO3/BO5） | 144 |
| 合計 | 255 |

每case100,000 trials、seed20260826、batch10,000；exact Clopper–Pearson雙側interval，以255比較Bonferroni、family alpha=.01。另做mass／swap／終局／service-order等invariants，解析差≤1e−8；記每stage耗時、peak RSS及平台單位。不挑case、不換seed救失敗；unfinished/censored trial不能靜靜掉棄。輸入contract為非退化開區間概率，endpoint／nonfinite／unsupported rule明確拒絕，不能隱藏clamp。

## 證據及停止界線

目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。含source-lock／擷取失敗、AO confirmation、pinned reference source、事前協議及semantic-negative-control。reference固定commit `69f7674f3bd842e3871e3f98a183b10613e1d247`，不依賴可移動branch或整個外部引擎作oracle。

未實作／未驗完的新 kernel 不得接進正式pricing。即使全255 case正確，也只證明給定假設的數值／規則正確性，不證明真實player iid、訓練資料合格、LL/Brier提升或盈利；十五個REJECT_DEV、frozen tennis-v1、C09依賴與新forward起點均不改。

`source-lock.json` SHA-256：`71c7f8db6e178c125b065dd0fc39fdfaecc2a906f61d5f67bfaa3ff9c16df0d7`。

`ao-rule-confirmation.json` SHA-256：`1b31af44934d41985b3b67bfcc7860538a2a348121df59a2cf2a209acfd25f86`。

`point-rule-kernel-v1/protocol.json` SHA-256：`3b75b151e0e9ef981418fe215f2067b6feb5592f7432339642a5dc353eb168d2`。

`semantic-negative-control/protocol.json` SHA-256：`b8a590d25177c72cf46e309911d8b5e6ea600ff5c6a936fdbe9e4b02b4166807`。

`semantic-negative-control/result.json` SHA-256：`e0fa0f663df758155b27805b568390b6f14f5f6b3cb9011c206a0a4bc551cce0`。

## 執行結果（固定協議，非預測表現）

研究程式位於 `tennis-wong-choi/src/tennis_wc/research_kernel/`，獨立 runner 為 `scripts/validate_rule_kernel_research.py`。reference.py逐byte沿用上述pinned oracle；新核心明示point probability與set rule，沒有從hold反推point skill。長盤尾部保存解析geometric分佈，不截斷後重新正規化。正式pricing沒有import此package。

正式MC前另記RNG細節：單一NumPy default_rng seed20260826，按照runner固定case次序，每case順序十批10,000。事前細節、runner hash、Python／NumPy／SciPy版本、grid hash保存到metadata；此前只做DP檢查，未看MC結果。第一次DP探索結果保留於tmp，正式有metadata的DP v2及MC另外存檔。

| 驗證 | 結果 |
|---|---|
| 針對性單元測試 | 18 passed（0.24秒） |
| 解析DP固定grid | 255/255 invariants通過，source hash前後一致 |
| 獨立MC | 255/255 simultaneous intervals包含DP；每case100,000，共25,500,000 trials，無失敗／丟棄case |
| 耗時／peak RSS | DP各case計時合計0.038秒／102,449,152 bytes；MC20.090秒／98,385,920 bytes；RSS為各自process累積峰值，非每case獨立增量 |
| repo gate | 原基線quick通過，AU三項稀疏欄位警告保留；完整gate由Central發佈流程執行，成功與否及確切SHA以immutable release manifest為準 |

MC的game及tie-break使用自己的point/service轉移；set/match以局作抽樣單位，局勝率使用共同的解析hold公式，**不是整場逐point的完全獨立oracle**。game層另有三個point MC比較；這種有限獨立性不應寫成所有公式均獨立重建。未知年份、draw或賽事仍未有resolver可認證；本次測試只接受明示規則。

永久證據目錄為上述 `point-rule-kernel-v1/validation-20261101/`，含dp/mc的metadata、逐case JSONL、完整result、MC前紀錄及全部研究source快照（378,027 bytes，12個被manifest追蹤的檔案）。

- DP result SHA-256：`56f22dbeb55981136cea9a9a69c482033fbd4bd4f0cde6f24cce84ab56f50499`。
- MC result SHA-256：`64e4e0dfca02dbdd6038897ab1f8f3a536395212a1cbf4d975db3f059cf01b39`。
- artifact-manifest SHA-256：`a42c7ff12c389020c2d851f2ed0e49510b5a1d983c23c6711613d35f9065d72d`。

重跑方式（在tennis-wong-choi目錄、每次指定新輸出目錄）：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <venv-python> scripts/validate_rule_kernel_research.py --mode mc --output <new-directory>`；DP用`--mode dp`。本次interpreter為`/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python`。

結論維持`SYNTHETIC_CORRECTNESS_ONLY`。沒有LL/Brier／ROI比較，沒有新forward或model promotion，十五個REJECT_DEV均不變。

發佈準備期間main已有其他AU／NBA更新，原工作分支的完整gate已明示取消，不能當成功紀錄。現有分支由5edea8c9快進4163b0e5後恢復exact-scope改動（無衝突），研究source hash前後不變；發佈流程必須對同步後版本重新完整檢查。
