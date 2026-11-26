# 自動覆盤＋自學循環（Kelvin 2026-11-26）

> 「review every race after the races, to see what does right what does wrong where to improve … done to au nba and tennis
> as well by itself so it can self learn, this is my goal」

## 0. 要解決嘅問題

11-18 跑馬地覆盤（人手，Opus session）做咗五件事：
1. 模型對市場：頭三命中、首選贏、頭馬喺 Top 5。
2. 失手分類：運氣／市場都估唔中、單晚現象、**重複出現嘅盲點**（只有呢類值得跟）。
3. 單晚 pattern 一定要攞返**之前幾個 live 賽日**核實（例：穩定性 <50 一晚好似被低估，5 日加埋反而相反）。
4. 順手查數據健康（晨操分全部 60 = 死欄位？）同 forward 測試進度（傷患 B1 已夠數）。
5. 逐場表：被低估／被高估嘅馬，對分數組成、標籤、走位、競賽報告 → 出可以回放驗證嘅假設。

而家呢五步散喺：`miss_autopsy.py`（2 嘅一半）、reflector（1）、`field_health.py`／`data_contract`（4）、forward tracker（4）。
**冇嘅**：3（自動跨日核實）、5（逐場解讀）、同埋「假設 → 之後嘅新賽日自動驗證 → 夠證據先叫 Kelvin」呢條鏈。
research-review（已暫停）之前想做類似嘢，但係設計上永遠唔改模型、證據搬咗一個月冇人知 —— 呢個設計要避開兩樣。

## 1. 硬規矩（唔變）

- **永遠唔自動改 live 模型。** 自學 = 自動*提出*、自動*驗證*、自動*報告*；上線係 Kelvin 一個掣。
  （例外：已存在嘅 Tier-1 練馬師殘差表 —— 版本化、shadow 對比、自動 rollback —— 照舊。）
- 失手結果**只出假設，唔准直接調**（EXP-20261013-01）。
- 假設喺 live 數據出世，**只准用出世之後嘅賽日判**（out-of-sample by time）；holdout 唔郁。
- 假設嘅分組條件只准用**賽前欄位**（白名單），賠率只做評估基準（HKJC 上仗賠率例外照合約）。
- 多重比較：同一時間開住嘅假設有上限，判決門檻按開住數目收緊（見 §4）。

## 2. 四層

### L1 每日覆盤報告（確定性 Python，四個 domain）
`shared_wong_choi/post_review.py --domain au|hkjc|nba|tennis --date D`
→ `<資料根>/WongChoiControl/reviews/<domain>/<D>.json`（＋`.md`）。

| 部分 | AU／HKJC | NBA（大細盤精選＋SGM 追蹤） | Tennis（精選） |
|---|---|---|---|
| 對市場 | 頭三入前三、首選贏、Gold／Good：模型 vs SP（HKJC 最終賠率） | 精選命中 vs 盤口隱含機率；CLV（21:00 價 vs 收盤） | 同左 |
| 失手分類 | `miss_autopsy` 四類（輸入有問題／擠迫／市場都錯／模型錯） | 腿：輸入有問題（傷停／上陣時間異常）／市場都錯（收盤機率 >60% 都輸）／模型錯 | 同左（退賽、傷停） |
| 逐場／逐注表 | 被低估（入前三但模型 ≥4）、被高估（模型頭三唔入）：分數組成前 3 個維度、標籤、跑位、SP | 每條腿：p_final、盤口機率、實際、上陣分鐘 | 每注：模型機率、價、結果 |
| 跨日核實 | 今日觸發嘅每個「候選 pattern」自動喺**之前 N 個 live 日**（AU 20、HKJC 10）重算殘差＋CI | 同左（30 日） | 同左 |
| 健康 | field_health 摘要、data_contract 警告、forward 進度（forward_board） | 同左 | 同左 |

「候選 pattern」由**固定 cohort 庫**（每晚只**記錄**，唔判；篩選見 L3）（`learning/cohorts.py`）產生，唔係即場作：每個 domain 一份預先寫好嘅賽前條件清單
（例：AU 試閘 z≥1、騎師 z≥1、休 ≥90 日、初出、外檔大場、穩定性 <50 …；NBA 背靠背、上陣分鐘跌 >20%、主客；Tennis 草地、
排名差 >50、上場相隔 ≤1 日）。每晚對每個 cohort 記「模型殘差」= 實際 − 賽前校準模型機率（`model_probability`），同一批馬嘅市場機率先去水
（AU power、HKJC 同法）。**分母 = 所有合資格場次**（唔係淨係失手場）。
「市場啱、模型錯」**唔用「市場殘差 CI 跨零」篩**（Astra：會偏向揀細組別，因為細組 CI 闊、易跨零）；
改用**同場 log-loss 差**（組別入面模型 vs 去水市場）。
**核數**（Astra【高】）：每日寫「應有場數／已配對場數」，缺快照、外置碟斷咗、補跑重複（按場去重）都要報警，
唔可以靜靜細咗樣本。

### L2 逐場解讀（LLM，唯讀，可選）
`claude -p --permission-mode plan`，只准 Read／Grep／Glob（同 self_repair `--allow-llm-diagnosis` 一樣嘅籠）。
輸入：L1 json＋上次假設帳。輸出：港式中文覆盤（11-18 嗰種逐場表＋三類讀法）同**最多 3 個新假設提案**（結構化 JSON：
cohort 條件用 cohort 庫語法、方向、機制解釋）。提案唔會直接入帳：要過 §3 嘅語法同白名單檢查。
- 頻率／額度：HKJC 每個賽日；AU／NBA／Tennis 每日一份合併 digest；用 Sonnet，每週一份 Opus 深度總結。
  Claude 本週 ≥85% 自動跳過 L2（L1／L3 照跑）。
- 覆盤文字 → Telegram `content`（Kelvin＋Heison）；假設／系統訊息 → `primary`。

### L3 假設帳（確定性）
`<WongChoiControl>/learning/hypotheses.jsonl`，每條：`id、domain、cohort（機器可讀）、direction、born（日期）、source
（cohort 庫自動／L2 提案／人手）、state`。
- **篩選唔係每晚**（Astra【高】：逐晚試 = 遲早試到中）：**每季一次**對 cohort 庫全部組別篩；重疊組別先去重，
  再連組合做 **Holm 校正（α = .05）**。
- **出世條件**：定向模型殘差嘅校正 CI 下限 **> 3pp**（同 Holm 一齊用），而且同場 log-loss 差顯示市場喺組別入面好過模型。
- **出世之後**：按賽日整組抽樣（cluster bootstrap），**預先定**達 80% 功效所需場數，兼最少 30 個有樣本賽日；
  只用 `born` 之後嘅賽日，**夠數判一次**：
  - CI 全部 > 3pp → `supported`（交 L4）；CI 全部 < 3pp → `rejected`；跨 3pp → `undecided`（唔延長、唔重判，下季可以重新出世但要新樣本）。
  - rejected 嘅 cohort 一年內唔准再出世。
- 未判之前每晚只報累積數量（盲），唔報殘差 —— 同 forward 一樣，防止睇住數提早停。
- 上限：每個 domain 同時最多 10 條；滿咗新嘅排隊。

### L4 升級做 forward 測試（半自動）
supported 嘅假設：
1. 自動跑 `power_precheck`（用 born 之後量到嘅 gap／覆蓋）；唔夠功效 → 留喺 supported，等多啲數據。
2. 夠功效 → 自動整 arm 提案：`learning/arm_proposals/<id>.json`（transform 用通用 shift 語法：`z(feature)`、`indicator(field op value)`），
   **一次過 fit β 喺 born 之前嘅數據**，寫 frozen.json＋sha。
3. Telegram primary：「H-xxx 有證據，建議開 forward arm（預計 N 日有答案）」。
4. **登記係一個 code 改動**（AU：`au_hypothesis_forward.ARMS` 加一行 sha）→ 經 Sol 覆核 → `./保存.sh`。即係由 agent（Claude session
   或者每週 learning session）做，唔係排程自己 commit。
5. forward 夠數自動判一次、凍結（現有機制）；PASS → Kelvin 一個掣上線（另一個改動＋model-regression-gate）。

AU 通用 forward 引擎（`au_hypothesis_forward.py`）喺今次同 H2／H3 一齊整，之後所有自動 arm 都用佢。HKJC 有
`hkjc_forward_tracker` harness_ab；NBA／Tennis 有 shadow arm 註冊（`featured_shadow.ARMS`），L4 對應寫落各自嗰度。

## 3. 防呆

- cohort 庫每個條件要標 `asof`（賽前點樣拎到）；新加條件要過 leakage-audit。
- L2 提案只可以組合 cohort 庫嘅原子條件（AND，最多 2 個），唔准自創欄位 → 唔會有「LLM 發明咗個賽後欄位」。
- 每晚 L1／L3 跑完寫 `forward_board` 類似嘅 `learning_board.json`；`健康.sh` 捉「覆盤冇出」「帳冇更新」（job_freshness 登記）。
- 盲：forward arm 未判之前照舊只報數量。L3 嘅 watching 假設會報殘差（佢唔係預先登記嘅判決，係篩選；真判決喺 L4 forward）。

## 4. 多重比較

每個 domain 大約 30 個 cohort → 純噪音都會有 cohort 跨過 95% CI。所以（Astra 覆核 2026-11-26）：
- 每季篩一次、重疊組別去重、Holm 校正；出世門檻係「效果 > 3pp」唔係「≠ 0」（細到冇用嘅效果唔出世）。
- supported 用 born 之後嘅獨立新數據、預先定樣本量、判一次。
- 真正嘅閘係 L4 forward（預先登記、一次判、把尺唔變、沿用 H1 判決鎖）。L3 只係決定「邊個值得開 forward」——
  揀錯嘅代價係浪費 forward 名額，唔係上錯線。

## 5. 分期

| 期 | 內容 | 驗收 |
|---|---|---|
| P0 ✅ | 已上線（EXP-20261126-01/02，Sol 覆核修咗 5 點） | |
| P1 ✅（2026-11-26） | L1 覆盤報告 AU＋HKJC（含每日核數）：`shared_racing/scripts/post_review.py`，AU 晚更 `step_post_review`、HKJC 賽後背景，content 摘要，`健康.sh`「自動覆盤」；dashboard 頁未做（重用 miss_autopsy）、cohort 庫、跨日核實；Telegram content 摘要；dashboard「覆盤」頁 | 對 11-18 跑馬地重現人手覆盤嘅主要結論（穩定性反例、模型獨家睇好冇 edge） |
| P2 | L3 假設帳＋每晚重驗＋learning_board＋健康.sh | 用 08-05→11-25 回放模擬：出世／rejected 數目合理（純噪音 cohort 唔會 supported） |
| P3（L1 ✅ 2026-11-26） | NBA＋Tennis 嘅 L1（`shared_wong_choi/post_review_sports.py`，NBA postgame／網球 18:00）／L3 | 同上 |
| P4（L2 ✅ 2026-11-26） | L2 AI 解讀（`shared_wong_choi/review_ai.py`：Gemini 寫、Python 核數字／名、Sonnet 審假設、假設帳；每週一 09:30 Opus 總結）、L4 arm 提案自動 fit（未做） | 一個提案走完全程到 Telegram（Astra：LLM 最後先做）|

## 6. 未決

- L2 用唔用 Opus：Kelvin Pro plan，每週額度有限 → 預設 Sonnet，HKJC 賽日可升 Opus。
- dashboard 覆盤頁同現有 reflector 報告點合併（一樣嘢一個標準）。

## 7. 覆核

- 2026-11-26 Astra（design）：7 點，全部採納 —— 殘差分母／去水／同場 log-loss（§2）、核數（§2、§3）、每季篩＋Holm（§4）、
  3pp 門檻＋預定功效＋判一次（L3）、先 L1 後 LLM（§5）。

## 8. 第一次跑（2026-11-25 數據）

- AU 43 場：模型頭三入前三 76/128 vs 市場 78/128；入頭三 log-loss 0.5239 vs 0.4722。核數冇缺。~2 分鐘。
- 跨日描述（之前 20 個 live 賽日）獨立重現咗兩個已登記假設嘅方向：「休 ≥90 日」−2.8pp [−5.1, −0.6]、市場 −0.5（= H3）；
  「休後第三仗」+3.1pp [+1.2, +5.8]、市場 +1.0。冇據此改任何嘢。
- HKJC 11-25 跑馬地 9 場：頭三入前三 12/27 vs 13/27；校準機率得 21 個賽日歷史，跨日比較暫時只有 1 日。
- H5 來源：`docs/audits/2026-11-26-stewards-report-sources.md`（QLD 最可行；NSW robots 禁止；商業用途要 Kelvin 問准）。
- **HKJC 賽後報告**（Kelvin 2026-11-26「應該要睇埋賽後報告」）：每場模型頭三嘅競賽事件報告、被低估／高估馬附分類
  （受阻／出閘慢／走外疊冇遮擋／醫療／騎法被查詢），每賽日報「被高估有幾多匹有賽中事件」。拆句用
  `hkjc_history_replay_build._incident_by_horse`、分類用 `incident_history.flags`（同入分同一份 regex）。賽後資訊，唔入組別、唔入模型。
  已知：標準 regex 漏「碰撞／收慢避開／出閘僅屬一般」等講法；嗰份 regex 用緊喺 forward shadow（EXP-20261117-05），
  今次唔郁，原文照顯示；要擴闊要另開一個改動（會改 shadow 輸入）。AU（Sportsbet）冇事件報告，見 H5 來源盤點。

## 9. NBA／網球 L1 第一次跑（2026-11-25 數據）

- 網球 200 注：模型（`model_prob_raw`）log-loss 0.6542 vs 去水市場 0.5549；精選 3/10、−4.17u。
  跨日（之前 29 日）：「模型高過市場 ≥10pp」−21.7pp [−24.8, −18.5]、市場殘差 −1.0 —— 同 EXP-20261125-10 `max_disagree20` 同一個方向（描述）。
  注意：`prop_tracker.model_prob` 係向市場收縮後，有啲盤口完全等於市場，唔可以當模型。
- NBA 624 條腿：實際中 38.1%、模型平均 35.0%；得 73 條有雙邊去水收盤價（模型 0.6721 vs 市場 0.6766）。
  跨日：「助攻」+2.0pp [+0.8, +3.1]、「模型 ≥80%」−3.1pp [−4.0, −2.0]（描述）。單邊 1/價含抽水，唔拎嚟比 log-loss。

## 10. AI 解讀（L2，Kelvin 2026-11-26「覆盤 there should be ai involved」）

分工（Kelvin 揀）：**Gemini 寫**（`codex_delegate.py run third`，唯讀、Google 訂閱、撞 429 自動停派、記帳）→
**Python 核事實**（每個小數／分數／≥10 嘅數字、每個「」名要喺當日覆盤 JSON 搵到，唔係就刪句）→
**Sonnet 審假設**（`claude -p --model sonnet`，空臨時目錄、只 `--add-dir docs/experiments`、plan mode、唯讀；
問洩漏、做過未、值唔值得）→ 假設帳 `<WongChoiControl>/learning/hypotheses.jsonl`（watching／covered）。
每週一 09:30 `central-wong-choi.review-weekly`：Opus 讀 7 日覆盤＋解讀＋帳，Telegram primary。冇用 Terra（Codex 預算留俾改模型）。
Claude 一定要喺 repo 以外嘅目錄跑：project Stop hook 會將「未保存」提醒蓋過答覆（第一次試就中）。

第一次（HKJC 11-25）：解讀分清賽中意外（引事件報告）、市場都錯、模型判錯；Sonnet 認出「內檔優勢高估」＝EXP-20261115-18、
「近績好高估」＝EXP-20261122-28（covered），「騎師此程弱被低估」入帳（watching）。

## 11. 每週健康巡查＋排程維修第二層（Kelvin 2026-11-26：「hydrogen 每一個欄位每一個分數都做一次健康檢查」「自動化有問題俾 hydrogen 試吓解決或者話俾 opus」）

**分工**：逐欄計數繼續 Python（field_health／data_contract／golden）。Hydrogen 做 Python 做唔到嘅大量人手對照：
- `shared_wong_choi/health_sweep.py`（每星期一 07:30，`central-wong-choi.health-sweep`）：抽上週 AU／HKJC 各 20 匹，「抓返嚟嘅原文」
  對「入分用欄位」；讀 8 週欄位健康表搵異常。Python 核實（引文要喺原文、值要係我哋嘅值、欄位存在、≥2 位小數嘅數字要喺數據入面）先報。
  Gemini 停派退 Luna。結果 Telegram primary，Opus 每週總結會排第一講。
- `.agents/scripts/self_repair_triage.py`（`self_repair --live --allow-llm-diagnosis`）：未知問題 → Hydrogen 唯讀診斷（detached worktree）
  → Python 核「檔案:行」（要全部對得上）→ 細修補＋高信心 =「Opus 收貨」，其他 =「升 Opus 處理」。AI 唔改檔、唔 merge。

**第一次試跑**：
- 原文抽查第一輪報咗 10 項「對唔上」，全部有合理解釋：AU 檔位係刻意密集排位（`data_prep`，退出馬後重排）、AU `age` 11-22 先開始寫入 Logic。
  已寫入巡查指示；第二輪 30 匹 0 項誤報。
- 欄位趨勢（要 Opus／Kelvin 判斷）：AU `Time`（賽果 CSV）連續 8 週 fill 0.0；`proven_class_feature` W46 由 100% 跌到 8%；
  `trial_score` 弱證據率 W42 由 0.19 升到 ~0.72；`jockey_horse_fit_score` 弱證據率慢升；`Margin` fill 1.0→0.93；
  HKJC `騎練組合` fill 0.93→0.80；`trackwork_trend_score` W44 起冇 leaf（EXP-20261029-02 刻意）。
- 維修診斷：拎 11-25 NBA warmup 撞鎖包試，Hydrogen 搵到同 e98f0fc3 一樣嘅成因同修法（有界等鎖），11 條證據全部核實 → opus_review。

## 12. NBA／網球欄位健康（Kelvin 2026-11-26：NBA 同網球完全冇欄位級別監察）

`shared_wong_choi/field_health_sports.py`：每晚（NBA postgame、網球 18:00 daily）攤平所有輸入欄（NBA ledger 賽前 model_obs／settlement／
availability；網球 prop_tracker＋pricing_evidence），記 n／填充率／唔同值／平均／SD 入 `<WongChoiControl>/field_health/<domain>.jsonl`；
同之前 14 日比捉「死咗／變常數（數值欄）／成批少咗／成日冇數據」，每個 domain 7 日冷卻、發送成功先記，Telegram primary。
每週健康巡查（Hydrogen）讀埋 NBA／網球按週彙總。Python 統計每日跑（幾秒、冇 AI 成本），AI 每週。

40 日回補：警報只喺 11 月頭兩次大改（NBA 引擎重寫 EXP-20261103-15、網球重建 11-06）同 NBA ledger 冇數據嘅 10-30／31、11-04；
11-13 之後兩邊零誤報。

**網球場地／資料質素（Kelvin 問點解 65、surface 空）**：唔係壞咗。場地唯一可靠來源 tennis-data.co.uk 只有 ATP／WTA，11 月下旬巡迴賽季完 →
0%；Challenger／ITF 一直冇場地來源（10–20%）。冇場地＋冇輪次令警告扣分頂到上限 35 → 低級別全部 65，啱啱過 `MIN_DATA_QUALITY` 0.65（門檻冇作用）。
改善方向：用往屆同一賽事／地點（`tennismylife_history`、`jeff_sackmann` 嘅 tournament_levels）補場地 —— 粗對應已可有把握補 42% 場次。
**會改定價**（場地 Elo），要重播＋model-regression-gate＋新數據驗證；未做。
