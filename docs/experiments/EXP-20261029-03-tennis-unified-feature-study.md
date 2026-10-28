# EXP-20261029-03：統一歷史特徵研究（F04／05／06／08）

- 日期／平台：2026-10-29 Sydney；Tennis賽前勝負。事前方法段保留，已完成結果見末節。
- 目標：分開量C03場地收縮、C06 recency／point exposure／prior、C12對手強度、C15 H2H residual嘅增量；唔合併幾項改善冒充單一feature功勞。
- 舊證據：EXP-20261009-01；EXP-20261027-06／07／08／09；EXP-20261026-04／05。舊nudge-off、game-share、rank、opponent-adjusted online S/R及fresh WTA overlay維持原REJECT。本次serve係固定最近25場嘅加權率／prior，不是重試EXP09能力更新。
- 方法：[不可任意改動嘅候選協議](../../research/tennis_unified/protocol_f03_f09.json)、[runner](../../research/tennis_unified/study.py)、[歷史來源](../../research/tennis_unified/history.py)、[因果特徵](../../research/tennis_unified/features.py)。只作離線研究，沒有production import。

## 事前設定及語料

一份已驗證完整SQLite snapshot；只讀12份固定Sackmann ATP／WTA main-tour raw responses，2020–25。source response hashes、原始URL／擷取時間及逐行排除保存在外置`f03-f09/cohort-v2.json`。不經mutable player-history ordinal joins。canonical event／round／format／pair去重，矛盾留置，不把pair+date當完整身份。

30,879 raw rows → 1,156不完整／不支援比分及2,460範圍外排除 → 27,263完整賽事；27,131場有雙方有效服務分數。當場stats缺失不剔走預測，歷史缺值用事前fallback。首版`cohort.json`額外排除176個season/calendar年界紀錄；呢項不在原日期範圍規則，已於任何候選擬合前修正，原檔保留。新版只按2020–25實際tournament-start日期範圍資格。

所有結果／欄位只喺`tournament_start+21d < forecast_date`釋出，fit labels亦須早於fold start。**publication時鐘未證實：leakage FLAG，只可SEEN_DEV敏感度研究，不能promotion。** 原control係重建歷史Elo／簡單head，唔係今日完整B_live；無法驗證嘅現役來源及固定五fold價格記N/A。

2020暖身，2021起expanding train；dev固定2023H1、2023H2、2024H1、2024H2、2025H1。新ID／冷啟動照報，不以當場box-score完整性選人口。2025H2已看過，dev失敗不開確認；不讀2026充新holdout。

## 有限比較及停止

完整F03–F09比較清單喺第一個候選fit前鎖定：38個比較×LL／Brier=76個Holm檢定。早期未鎖草稿31比較沒有執行結果；現版事前補七個serve對B_simple比較，避免只贏弱profile控制。未執行／缺來源名額保留p=1，唔每批重設alpha。

- F04：`n_surface/(n_surface+20)`對相同K／更新／歷史資料嘅固定.65/.35 Elo，逐球員收縮；不改既有forward shadow。
- F05：000控制及R／E／S／RE／RS／ES／RES七arms；各對000及B_simple；RES另對三個leave-one-out。180日半衰、100 pseudo-points；E-off以固定暖身median exposure換算point-equivalent denominator，無S時仍係等match平均。Prior只讀2020且2021前已按協議可用資料。
- F06：共同Elo／滯後rank／opponent-bucket控制，只加最近10場對手同自己當時overall Elo差平均。
- F08：Elo-only、+raw H2H控制；候選`sum(y−p_then)/(n+5)`。每次meeting嘅p用當時forecast state，唔用今日Elo重算。

同cohort、無截距ridge1、training-only除尺度但不扣均值，最終probability共同clip[.02,.98]。A/B swap精度1e−10。配對match bootstrap4,000次、seed20260826、95% CI，gain=control−candidate。五fold兩項均不退步、pooled正增量及多重比較支持先可ADVANCE_DEV_ONLY；Holm-only未過而保留名額未結案時記pending；有fold退步REJECT_DEV。RES必須通過所有直接／邊際比較。固定方法／群體／測試log／feature hashes後先fit，改hash即停。

F03／C01缺完整固定fold價格，C14缺實際賽事／完結時間；停相應arms，不縮年份或捏造hours。F09／合併保留名額及未fit狀態，按前序結論再鎖輸入recipe，不因本次結果改尺。

## 驗證及結果

事前43項研究測試通過，包含當場／未來結果注入、嚴格21日界線、冷啟動、point denominator、missing window、H2H舊expectation、tour隔離、A/A、swap及feature/cohort對齊。Quick gate通過；結果已完成，最新完整16組gate亦全通過。**未有KEEP／未聲稱現役準確度改善。**

外置root：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/f03-f09/`。預定`features.json`、`study-lock.json`、`development/`各fold模型／逐場預測／bootstrap／summary／artifact manifest；精確hash及結果完成後補在下方，不覆寫舊artifact。

```bash
# Repo root；P採runtime manifest記錄嘅既有venv interpreter。
P=/Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python
RUN='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/f03-f09'
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 "$P" -m research.tennis_unified.study run --lock "$RUN/study-lock.json" --output "$RUN/development"
```

## 完成結果：全部候選REJECT_DEV

Lock時間`2026-10-28T21:31:41.788468Z`，SHA256 `a5eb5f8be49213ad7731adfd12e88198916c0b3fedc2075fe345719562c61b64`，早於首次候選fit。Feature SHA `326cce647765a4114988817f239f51e8aba79968bbff005419e99799617f2d4f`。共24,880個2021起feature rows，五段dev N依次2,937／2,162／2,944／2,315／2,916，合計**13,274個獨立match IDs**，所有arms同一群體；每個fit只用fold前已按協議可用labels。

| 候選／直接控制 | 控制LL → 候選LL | 控制Brier → 候選Brier | LL／Brier不退步folds | 判決原因 |
|---|---:|---:|---:|---|
| surface dynamic／fixed Elo | .62712707 → .62615767 | .21927751 → .21879892 | 4／4 | 2024H1退步，Holm亦不過；總數輕微改善不能救候選 |
| serve R／000 | .61748709 → .61687114 | .21481394 → .21451650 | 4／5 | LL CI跨零；2024H2對直接控制退步；對simple亦只有4段LL不退步 |
| serve E／000 | .61748709 → .61800100 | .21481394 → .21501288 | 1／1 | 按point exposure加權本設計整體較差 |
| serve S／000 | .61748709 → .61786009 | .21481394 → .21499818 | 0／0 | 100 pseudo-point prior喺五段均較差 |
| serve RE／000 | .61748709 → .61754773 | .21481394 → .21477314 | 3／3 | 指標方向不一致、時間段不穩定 |
| serve RS／000 | .61748709 → .61731849 | .21481394 → .21477991 | 3／2 | 對simple五段較好，但對同profile直接控制唔穩，唔取弱控制救結果 |
| serve ES／000 | .61748709 → .61841318 | .21481394 → .21522772 | 1／1 | 整體更差 |
| serve RES／000 | .61748709 → .61816049 | .21481394 → .21511878 | 2／2 | 合併差過000；對leave-one-outs亦未過，複雜度無支持 |
| opponent strength／simple | .62016007 → .62022298 | .21605694 → .21608647 | 2／2 | 整體及三段退步 |
| H2H residual／Elo-only fit | .62719328 → .62696730 | .21931143 → .21919965 | 4／4 | LL及Brier CI均跨零；對raw H2H亦只有3／3段不退步 |

另保存raw H2H控制LL .62706109／Brier .21923959。Residual對raw gain LL .00009380，95% CI[−.00004693,+.00024095]；Brier .00003994，CI[−.00002173,+.00010418]。不聲稱穩健增量。Serve000對simple嘅refit／既有profile增量不歸功R／E／S。

全部21個已執行配對比較、未執行名額、每fold係數／scaler、10-bin ECE／slope、tour／surface／level／format及歷史樣本／missing分層保存在`development/summary.json`及逐fold檔。全部判決都因事前fold／效應條件失敗，唔依賴之後未完成名額會否改變Holm排序；沒有合併候選入forward。2025H2未做新候選確認評估。

### 獨立重算

`independent-replay-source.py`不import研究runner：重算全24,880行Elo／dynamic特徵、全部13,274場／13個fitted arms嘅概率與loss；以固定seed另外抽100場，直接由原cohort重算全部serve profiles及歷史H2H expectation；核對4000 bootstrap均值／CI、p及完整76名額Holm。最大Elo誤差2.73e−15、profile誤差0、H2H誤差1.39e−16、概率誤差2.23e−16、loss誤差3.22e−15，PASS。原始結果及獨立source/report都保留；只證明計算，**PIT FLAG未清**。

**決定：REJECT_DEV全部本批特徵候選；不部署，不再掃半衰／prior／surface常數救結果。** 研究程式及失敗證據只保存non-main研究分支，正式評分code／golden／ruler／下注政策均未改。整個統一研究仍未完成。

報告交付：`report-export/development/`有exact round-trip Parquet、paired_metrics.json、subgroups.csv、calibration.csv、protocol.json及artifact_manifest.json；ROI輸出明示N/A。另有cohort_flow.csv、excluded_rows.csv、feature_availability.csv。formatter首版自引用manifest錯誤保留於舊export目錄，可信新版全部hash已核對；原模型結果未覆寫。

價格後續：本批完成後另追查到原publisher新公開目錄，已capture全12個ATP/WTA2020–25 workbook；舊MISSING_SOURCE審計及本批N/A判斷原樣保留。新資料須獨立identity／quote contract資格及事前price protocol後，先執行原預留C02／C01／C13名額，不能用嚟改判本批REJECT。
