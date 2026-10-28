# Tennis：歷史研究與正式採用資格澄清

2026-10-29 Sydney，於任何F03–F09候選擬合／結果之前記錄。呢份只釐清[研究協議](tennis-research-protocol-20261028.md)第1–2節已有嘅dev／PIT分別；不修改tennis-v1、歷史fold、統計要求或promotion門檻。

## 原因及適用範圍

目前live保存預測可做部分parity，但canonical feature verifier有0份qualified projections；另外有已留置嘅fixture／label衝突。呢啲紀錄不能用嚟宣稱當前完整模型嘅可靠成績。另一方面，協議原本已容許來源隔離、以21日隔離處理tournament-start-only資料嘅SEEN_DEV敏感度研究。兩者唔應混成「全部資料已合格」，亦唔應因其中一條來源有問題而不經審計就判另一條獨立來源不可研究。

| 工作 | 必須先過嘅資格 | 不能聲稱嘅結果 |
|---|---|---|
| 來源／parser／數學核對 | 固定來源版本、完整排除記錄、相應schema／規則及獨立核對 | 不能由綠色tests推論準確度改善 |
| 隔離來源嘅歷史feature／head研究 | 自身canonical cohort、無爭議labels、原始輸入及每個欄位可用時間政策、相同cohort嘅直接控制、A/A／時間／swap／train-inference測試、事前arm及比較清單全部鎖定 | tournament-start+21日只係事前固定dev近似，不能稱已證明歷史PIT；贏B_simple不能稱贏B_live或市場 |
| 保存現役預測嘅完整比較 | 該場frozen identity／feature／raw-source及時鐘合格，最終概率parity≤1e−6；共同eligible IDs | 缺乏資格嘅B_live記N/A，不補當前Elo／假來源；部分群體不能外推全模型 |
| 多book／市場增量研究 | 相同逐場價格合約及來源；依協議標明有時鐘或unknown dev；同場book不重複當樣本 | 缺價格年份不能縮窗；無時鐘ROI不能稱可執行回報。依賴缺價格嘅arm保留未執行名額 |
| 新forward及promotion | 真實PIT、完整原始證據、Sportsbet-only inference、family-specific市場／settlement、凍結後新資料、樣本／power及全部既有guardrails | 研究近似、SEEN_DEV勝出或缺失門檻不能當正式採用證據 |

每批manifest須記`eligibility_scope`、`split_status`、`pit_verified`、控制群體及N/A原因。現有snapshot／舊feature artifacts保持原狀，不回填或消除warnings。F01某來源／某schema缺失只暫停依賴嗰份來源嘅arm；例如既有box-score研究不因另一套走地PBP入口404而改用另一parser。F02未完成歷史規則mapping，仍會阻止依賴相應賽制嘅props比較。

## Promotion執行語義

[Frozen tennis-v1](../../.agents/skills/shared_wong_choi/resources/evaluation_rulers/tennis-v1.json)嘅`decision_mode`係`promotion_gate`；[現有evaluator](../../.agents/skills/shared_wong_choi/research_evaluation.py)嘅`_family_scope`要求primary／guardrail相對基準不退步、對市場兩項gain及其證據、absolute ROI非負／downside、cohort、樣本及power等條件。呢份唔新增／刪減任何一項。

現有authority寫「calibration合格」，未提供獨立absolute ECE上限；不能自行創造一個數字再稱已批准。未解決嘅正式採用合約繼續列gap並阻止promotion；研究照報預定10-bin ECE及校準intercept／slope，唔把「無absolute上限」解讀成豁免現有相對guardrail。

本次唯讀核對嘅SHA256：ruler `3dc8575351716ec7fea68b3c9bab6c4031f9dfe9731ed18e41f8295078a19788`；evaluator `bbe9c2ae4ffaa5e783f325ad073da6e3cfb2596abf188f17589d77f071b6d506`；authority `70dfcffddf2395410869370ee5357e6ce340f370113b1bffde0eb00a9fa0480e`。三個原檔均未修改。

**判斷**：可繼續滿足自身前置閘嘅SEEN_DEV研究；現有live provenance缺口及未解決合約繼續阻止受影響比較／正式採用。呢份唔係任何候選嘅KEEP或release批准。
