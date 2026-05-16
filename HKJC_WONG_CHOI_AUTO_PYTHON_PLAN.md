# HKJC Wong Choi Auto 全 Python 化完整實作計劃

## 1. 目標摘要

建立一個獨立 parallel agent：`HKJC Wong Choi Auto`。

舊 `HKJC Wong Choi` 完全保留，唔改現有正常流程。Auto 版沿用現有 HKJC extraction、PDF、racecard、form guide、training / trackwork data、Facts.md、Analysis.md output template、QA gate、MC/report flow，但馬匹評分、排名、Grade、Top Pick、信心分、risk flags、core logic 全部由 Python deterministic engine 生成。

Auto 版核心原則：

- Python 負責所有分數、排名、Grade、Top Pick、信心分、risk flags。
- Python 生成自然語言 `core_logic`，只可用 deterministic template NLG / rule-based phrase bank。
- HKJC Wong Choi Auto 執行期間 **0% LLM involvement**：不准 LLM 生成、改寫、補充、審批或重排任何 Auto output。
- LLM 不可決定或參與分數、排名、Grade、Top Pick、Top 4、投注建議、信心分、risk flags、reason codes、core logic、verdict 或報告文字。
- 不用賠率、市場、value、fair odds、edge 做評分。
- 不用步速、pace prediction、leader count、on pace / backmarker 做評分；`race_shape` 只保留為舊 7D key，Auto 版改為檔位與走位分。
- 7D matrix 保留為 Wong Choi Auto 嘅正式 rating matrix，跟現有 Wong Choi V4.2 設計一致。
- 12 個分數改為 Python feature / sub-score layer，用嚟餵 7D matrix，不直接取代 7D。
- 所有評分必須可重跑、可測試、可審計，同一 input 必須得到同一 output。

## 2. Agent / Skill 邊界

新增 parallel agent：

```text
.agents/agents/hkjc-wong-choi-auto.md
.agents/skills/hkjc_racing/hkjc_wong_choi_auto/
```

Auto 入口：

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py <URL / meeting folder / Race_X_Logic.json>
```

第一階段可以做成 wrapper：

- 對既有 `Race_X_Logic.json` 或 meeting folder 內嘅 `Race_*_Logic.json` 做 deterministic scoring。
- 重用現有 extraction / Facts.md 產物。
- 不改舊 `hkjc_wong_choi/scripts/hkjc_orchestrator.py`。
- 後續再把 Auto wrapper 接入完整 extraction state machine。

Auto agent 必須明確聲明：

- 舊 Wong Choi 是 classic pipeline。
- Auto Wong Choi 是 Python-only scoring pipeline。
- 兩者 output template 可相似，但 scoring truth 不同。

## 3. 權責分工

Python owns all Auto output：

- 12 個 feature / sub-score 分數
- 7D matrix score
- `ability_score`
- `risk_score`
- `confidence_score`
- `grade`
- `rank`
- `model_pick_status`
- `reason_codes`
- `risk_flags`
- `score_breakdown`
- `core_logic`
- Top 2 / Top 4 ranking
- CSV scoring export
- validation / QA gates

LLM hard ban in Auto：

- 分數
- 排名
- Grade
- Top Pick
- Top 2
- Top 4
- 信心分
- 投注建議
- 任何 scoring override
- `core_logic`
- 7D reasoning text
- `reason_codes`
- `risk_flags`
- verdict / Top 4 report wording
- CSV remarks
- QA approval

Auto 版不設 `llm_commentary` 欄位。任何 LLM commentary、model-generated prose、人工智能二次改寫都不可進入 Auto pipeline。若將來想做人手閱讀版 commentary，必須另開非 Auto pipeline，並且不得覆寫或污染 Auto output。

### 3.1 Auto 顯示語言規則

Auto 版 internal JSON / Python schema 可以保留英文 key，方便測試、驗證同程式讀取。但所有 user-facing output 必須用香港中文：

- `Analysis.md`
- CSV remarks / report remarks
- `core_logic`
- 7D section `matrix_reasoning`
- Top 4 / verdict text
- QA / validation report 入面畀用戶閱讀嘅 summary

固定顯示 mapping：

| Internal key / status | User-facing display |
|---|---|
| `MODEL_TOP_PICK` | `模型首選` |
| `WATCH` | `觀望` |
| `NO_PICK` | `不選` |
| `ability_score` | `能力分` |
| `confidence_score` | `信心分` |
| `risk_score` | `風險分` |
| `draw_score` | `檔位分` |
| `HKJC draw stats` | `HKJC 檔位統計` |
| `reason_codes` | `原因代碼` |
| `risk_flags` | `風險標記` |

禁止在 user-facing Auto report 直接顯示：

- `MODEL_TOP_PICK / WATCH / NO_PICK`
- `risk_score`
- `confidence_score`
- `ability_score`
- `draw stats`
- 任何 LLM / model commentary 字眼

例外：CSV 欄位名可保留英文作機器讀取，但 CSV remark 文字必須香港中文。

## 4. 正式 Rating Matrix：保留 7D

Auto 版正式 rating matrix 必須沿用現有 Wong Choi V4.2 嘅 7D 設計。原因：

- 現有 `Race_X_Logic.json` schema 已固定為 7D：`stability`, `sectional`, `race_shape`, `trainer_signal`, `horse_health`, `form_line`, `class_advantage`。
- 現有 `Analysis.md` template、QA gate、Top 4 verdict 都係圍繞 7D 呈現。
- 用戶偏好保留 Wong Choi 產品語言，唔想因全 Python 化而改變 output 觀感。

7D canonical keys：

```text
stability          狀態與穩定性
sectional          段速質量
race_shape         檔位與走位（保留 key 名，但 Auto 不含步速評分）
trainer_signal     騎練訊號
horse_health       馬匹健康 / 新鮮感
form_line          賽績線
class_advantage    級數優勢
```

重要修正：

- 7D 是正式 rating matrix。
- 12 個分數不是新 matrix，而是 Python feature / sub-score layer。
- 舊 tick 欄位在 Auto 版停用；Python 不產生 tick，不顯示 tick，不用 tick count。
- `race_shape` key 為兼容舊 schema 而保留，但 Auto 版顯示名改為 `檔位與走位（不含步速）`。
- `race_shape` 只可以用 draw stats、預計走位可行性、上仗走位消耗、今日檔位改善等非步速因素，不可使用 pace prediction。
- Auto 版不再使用 tick。所有 ranking、Top 4、Grade、pick status 都以 numeric score 為準。
- Grade 只係由 score 派生出嚟嘅參考標籤，不參與排序。

## 5. 12 個 Feature / Sub-Score Layer

Python 仍然計 12 個 sub-scores，但用途係餵 7D，而唔係直接成為 output rating matrix。

```text
form_score
speed_score
class_score
jockey_score
trainer_score
draw_score
distance_score
track_going_score
weight_score
consistency_score
risk_score
confidence_score
```

通用規則：

- 所有 sub-score 為 0 至 100。
- 資料不足用中性分 60。
- 所有 sub-score 必須 clip 到 0 至 100。
- 每個 sub-score 必須有 `score_breakdown`，列出 raw inputs、rules、reason codes、risk flags。
- 每個 7D score 必須列出由哪些 sub-score 及 raw evidence 組成。
- 分數必須 deterministic，不可用 LLM 判斷。

12 sub-score 對應 7D：

| 7D Section | 主要 sub-scores | 備註 |
|---|---|---|
| `stability` 狀態與穩定性 | `form_score`, `consistency_score`, `risk_score` | 近績、頭馬距離、波動、可寬恕場次 |
| `sectional` 段速質量 | `speed_score`, `distance_score` | L400/L600、完成時間偏差、路程能量適性 |
| `race_shape` 檔位與走位（不含步速） | `draw_score`, `track_going_score`, `distance_score` | HKJC 檔位統計、檔位改善、場地彎位/直路特性；不含 pace |
| `trainer_signal` 騎練訊號 | `jockey_score`, `trainer_score` | 騎師、練馬師、人馬歷史、可驗證部署訊號；騎練 combo 只在 structured data 存在時使用 |
| `horse_health` 馬匹健康 / 新鮮感 | `risk_score`, `track_going_score`, `consistency_score` | 健康、休賽、體重、freshness、場地轉換風險 |
| `form_line` 賽績線 | `form_score`, `class_score` | Facts.md 對手後續、強弱組、賽績含金量 |
| `class_advantage` 級數優勢 | `class_score`, `weight_score`, `distance_score` | 升降班、official rating、負磅甜蜜點、路程級數 |

## 6. Data Source Availability Gate

Auto 版所有 scoring input 必須由以下本地 pipeline source 直接提供，或由 Python 從以下 source deterministic 計算：

```text
Racecard.md
Formguide / Speedpro 賽績.md
HKJC horse profile data merged into Facts.md
Training / trackwork JSON or markdown
Starter PDF extracted markdown
Facts.md
local static JSON resources，例如 hkjc_draw_stats.json / hkjc_standard_times.json / hkjc_reference_sectionals.json
```

硬性規則：

- 每一個 scoring feature 必須有 `source`, `raw_field`, `parser`, `availability_status`。
- 如果資料未能由上述 source 抽出，該 feature 不可用作加分。
- 缺資料預設中性 60，並加入 `missing_*` reason code / risk flag / confidence cap。
- 不准因 analyst resource 入面有概念，就用 Python 憑空推斷數值。
- 不准用 web search、LLM knowledge、主觀推斷、賠率、市場或步速預測補資料。
- `score_breakdown` 必須列明每個分數用咗邊個 source；無 provenance 即 validation fail。

### 6.1 已穩定可用資料

| Data | Source | 用途 |
|---|---|---|
| 場次、日期、地點、surface、course、distance、going、class、rating range | Racecard.md | race context、class、distance、track going |
| 馬號、馬名、烙號、負磅、騎師、檔位、練馬師、official rating、rating +/-、排位體重、馬齡、性別、上賽距今日數、配備、父系、母系 | Racecard.md | horse identity、weight、jockey/trainer base、gear、age、sire/dam names |
| 過往出賽日期、日數、跑道/路程/場地、檔位、馬重、負磅、騎師、名次/出馬、能量值、分段時間、賽事短評 | Formguide / Speedpro | form、speed、sectional、running style、trip comments、body weight trend |
| margin、trainer、class、rating、running positions、finish time、declared weight、gear、full race history | HKJC horse profile merged into Facts.md | form score、finish-time deviation、class score、rating trend、position/trip cost |
| L400/L600、全段速剖面、standard time deviation、finish-time deviation、energy trend、margin trend、rating trend、gear trend、position PI | Facts.md generated by `inject_hkjc_fact_anchors.py` | stability、sectional、form、risk、core_logic evidence |
| HKJC draw starts/wins/places/win%/place%/top4%/verdict | `hkjc_draw_stats.json` + Facts.md draw block | draw_score、race_shape |
| standard times / reference sectionals | `hkjc_standard_times.json`, `hkjc_reference_sectionals.json` | speed_score、sectional |
| jockey/trainer ranking、season wins、rides/starters、win/place rates、track split、近30日 raw table | Starter PDF extracted markdown, once structured parsed | jockey_score、trainer_score |
| Conghua / injury / overseas purchase / starter PDF special notes | Starter PDF extracted markdown | risk_score、horse_health、debut/import handling |
| trackwork / trial / gallop / rider involvement / readiness digest | trackwork extractor output | horse_health、debut fallback、trainer_signal support |
| 人馬組合歷史：同一騎師騎同一馬 starts/wins/places/average placing | Facts.md `人馬組合統計` | jockey_score、trainer_signal |

### 6.2 Conditional：有結構化資料先可以用

| Data | Current Status | Auto rule |
|---|---|---|
| 騎練 combo 季內 win/place rate | Starter PDF / HKJC site 可能有，但現有 extraction 未必穩定結構化 | 未有 `jockey_trainer_combo_starts/wins/places` structured field 前，不可加分；預設 60 |
| jockey_last30 / trainer_last30 | PDF raw text 有機會抽到，但需 parser 驗證欄位 | parser 未能穩定拆欄前只可 display/reference，不可入 score |
| trainer specific deployment signal | 可由 racecard/Facts 欄位觸發部分規則 | 只有觸發條件所需 raw fields 齊全先生效；缺一個必須跳過該 signal |
| jockey tactical fit | `07c_jockey_profiles.md` 是 static rule source；horse running style 可由 Facts/comments 派生 | 只可用已抽到嘅 running_style / position history；無 running_style 時 tactical fit 中性 |
| horse temperament | 現有 extractor無穩定欄位 | 禁止用作評分，除非日後 Facts.md 增加 deterministic temperament tag |
| Sire AWD / dam performance | racecard 有父系/母系名稱，但無 AWD / 子嗣統計 | 不可用 AWD 加分；只可顯示 sire/dam name。若日後新增本地 sire table，先可啟用 |
| debut trial quality | trackwork extractor 可抽 trial/gallop，但未必每匹都有 | 有 structured trial/readiness 才用；無資料則 debut confidence cap |
| retained jockey status | `07c_jockey_profiles.md` 有 static date-bound rule | 只可在 effective date 未過期且 horse/trainer/jockey match 完整時用 |
| ST -> HV transfer advantage | Racecard/Formguide/Facts 可識別場地轉換 | 只有同程/相近路程成績、好檔、trainer HV transfer signal 至少一項硬 evidence 才可小幅支持；單純轉場不可加分 |

### 6.3 禁止使用 / 先移除

| Data / Concept | 原因 | Auto handling |
|---|---|---|
| live odds / market / value / fair odds / edge | 市場結果，不是能力因素 | 永久不入 scoring |
| race-level pace prediction / leader count / expected speed / pace collapse | 現階段避免步速誤導 | 不入 scoring；如 template 保留必須標示 not used |
| trainer intent without trigger fields | 無法由 extractor 驗證 | 不可加分 |
| jockey confidence / trying hard / selective effort | 主觀且未有穩定欄位 | 不可入分 |
| horse temperament not derived from structured comments | 不穩定 | 不可入分 |
| sire AWD without local structured sire data | racecard 只有父母名，不等於 AWD | 不可入分 |
| jockey-trainer combo if only resource example says “golden combo” | 靜態例子會過期 | 無當季 structured combo data 即中性 |
| unparsed PDF text table | raw text 易欄位漂移 | 必須先 parse 成 JSON 並通過 schema validation |

### 6.4 Source Coverage By Matrix

| 7D | Required Extractable Inputs | Missing-data behavior |
|---|---|---|
| `stability` | last 6/10 form, margins, margin trend, body weight trend, days since last, invalidated runs | 用已抽到近績計；缺 margin/body trend 則不做相關加減，confidence 扣分 |
| `sectional` | sectional splits, L400/L600, energy, standard/reference times, finish time deviation | 無 sectional 時 `speed_score=60`；不可用 pace 補 |
| `race_shape` | draw stats, barrier, field size, track/course/distance, trip comments, running positions | 無 draw stats 時 `draw_score=60 + missing_draw_data`；不可用主觀內外檔 |
| `trainer_signal` | jockey/trainer identity, rankings, horse-jockey history, trainer signals with complete trigger fields, trackwork rider involvement | 缺 combo/ranking 時中性；只用可驗證 signal |
| `horse_health` | injury notes, body weight trend, days since, trackwork, medical keywords, Conghua/休養 notes | 缺健康資料不可當健康良好；中性 + confidence cap |
| `form_line` | Facts.md formline report / opponent follow-up / strong-middle-weak assessment | 無 Facts formline 時 N/A/60，不強行扣分 |
| `class_advantage` | race class, official rating, rating trend, class history, weight, distance record | 缺 class history 時只用 racecard official rating/weight，並降低 confidence |

### 6.5 Implementation Rule

Auto engine 必須先跑 `data_availability.py`：

```python
availability = audit_sources(horse_input)
if not availability["field"].usable:
    score_component = 60
    reason_codes.append("missing_field")
    confidence_penalties.append("missing_field")
```

任何 feature scorer 不可以直接讀 raw text 後自由理解；必須經過 typed parser 輸出 JSON，例如：

```python
RaceContext
HorseRacecard
PastRun
HorseProfileRun
DrawStat
TrackworkDigest
JockeyTrainerStats
FormLineSummary
```

## 7. Ability Score 公式：改用 7D 加權

Auto 版 `ability_score` 以 7D 為唯一正式來源，權重跟現有 rating engine 嘅「核心 / 半核心 / 輔助」精神一致。

### 7.1 Python 能否處理「唔完全係數學」嘅賽馬判斷？

可以，但 Auto 版要承認一件事：Python 做嘅唔係自由判斷，而係將現有 Wong Choi analyst knowledge 轉成「可驗證資料 + deterministic rules + caps / floors + confidence gate」。

即係：

- 如果一個判斷可以由 Racecard / Formguide / Facts.md / trackwork / PDF structured parser 抽到資料，就可以寫成 Python rule。
- 如果一個判斷只係「似乎」「感覺」「馬房有部署味」「騎師應該搏」而無 raw evidence，就不可入分。
- 如果資料有一半，但唔完整，可以小幅加減或只作 reason code；不可當完整 signal。
- 如果資料完全無，必須中性 60 + `missing_*` reason code + confidence penalty。
- 所有非純數學 racing concepts 都要先變成 trigger specification，之後先可以入 scorer。

例：

| Racing judgement | Python 可否做 | Auto rule |
|---|---:|---|
| Top rider + 馬匹歷史有支持 | 可以 | 需要 `jockey_win_rate/place_rate` + `horse_jockey_starts/wins/places/avg_finish`；無人馬歷史就只計騎師基本分，不可當配搭支持 |
| 騎練 combo 強 | 有條件 | 需要 structured `jockey_trainer_starts/wins/places` 且 sample size 合格；無當季資料則中性 |
| 馬房部署 | 有條件 | 只可由可驗證 trigger 觸發，例如換強騎師、配備轉變、trackwork rider involvement、休後試閘、同程轉場紀錄 |
| 可寬恕敗仗 | 可以 | 需要 form comment / Facts.md 有 blocked, wide, checked, slow away, lame, vet 等 deterministic tag |
| 沙田轉跑馬地可能有利 | 有條件 | 單純 ST -> HV 不加分；必須同時有 HV / similar-turning-track form、今日檔位支持、同程/相近路程支持或 trainer transfer signal |
| 跑法配合今日形勢 | 只可部分 | 可以評估檔位/走位可行性；不可評估步速、leader count、race collapse |
| 騎師今日搏唔搏 | 不可 | 主觀，不入 Auto scoring |
| 馬房信心 | 不可 | 除非有可抽取 structured evidence，否則不可入分 |

因此 Python 可以「properly score」嘅前提係：

1. 每個 signal 都有資料來源。
2. 每個 qualitative rule 都有明確 trigger。
3. 每個 trigger 都有分數幅度、sample cap、confidence cap。
4. 無資料就中性，不猜。
5. V1 分數要經 historical dry run / backtest 校準，唔應該一寫完就當成最終 truth。

Auto scoring 目標係建立乾淨、可重跑、可審計嘅選馬模型；唔係模仿 LLM 嘅自由推理。

```python
ability_score =
    sectional_score * 0.23 +
    trainer_signal_score * 0.21 +
    stability_score * 0.17 +
    race_shape_score * 0.15 +
    class_advantage_score * 0.10 +
    horse_health_score * 0.07 +
    form_line_score * 0.07
```

權重理由：

- `sectional` 同 `trainer_signal` 係現有 rating engine 核心維度，合共 44%，必須高過半核心同輔助。
- `stability` 同 `race_shape` 係半核心，合共 32%，保留強影響力，但不可單獨壓過核心。
- `class_advantage`, `horse_health`, `form_line` 係輔助維度，合共 24%，用作補強、封頂、風險與排序。
- `class_advantage` 保留 10%，因為原 Wong Choi 仍重視真級數、official rating、負磅同升降班。
- 呢個分佈比平均 7D 更貼近原本 Wong Choi「核心 > 半核心 > 輔助」設計。

Sorting / ranking rule：

- Race ranking 只按 `ability_score` 排序。
- Top 4 = 全場 `ability_score` 最高 4 匹。
- Top 2 = 全場 `ability_score` 最高 2 匹。
- Grade 不參與排序；Grade 只係把 `ability_score` 轉成人類容易睇嘅參考 label。
- 若 `ability_score` 完全相同，tie-breaker 按以下順序：
  1. `confidence_score` 較高者
  2. `risk_score` 較高者
  3. `sectional_score + trainer_signal_score` 較高者
  4. `race_shape_score` 較高者
  5. 馬號較小者，確保 deterministic

`risk_score` 同 `confidence_score` 不推高能力分，只作 gating：

- 風險太高可令 `MODEL_TOP_PICK` 變 `WATCH`。
- 信心不足可令高能力馬變 `WATCH`。
- 風險極高可令馬匹變 `NO_PICK`，即使 ability_score 高。
- S-tier 需要額外 confidence / risk guardrails。

## 8. Grade 規則

Auto 版支援完整 S-tier：

```text
S+ = 96+
S  = 92-95.99
S- = 88-91.99
A+ = 84-87.99
A  = 80-83.99
B+ = 74-79.99
B  = 68-73.99
C  = 60-67.99
D  = 60 以下
```

Grade 生成方式：

- Grade 由 `ability_score` 直接映射。
- Grade 只作 reference label，方便閱讀。
- Ranking、Top 4、Top 2、MODEL_TOP_PICK 全部使用 numeric scores。
- 同 Grade 內嘅排序不可按 Grade 字母或 S/A/B label，必須按 `ability_score`。

S-tier guardrails：

- `S-` 或以上必須 `confidence_score >= 70`。
- `S` 或以上必須 `confidence_score >= 75`，且無 major risk flag。
- `S+` 必須 `confidence_score >= 82`，且至少 4 個 ability component score >= 85。
- 若 `risk_score < 65`，Grade 最高封頂 `A`。
- 若存在 fatal risk flag，Grade 最高封頂 `B+`。
- Debut / import / insufficient data 馬即使 ability_score 高，也要按 confidence cap 處理。

Grade 代表馬匹基本面能力區間，不代表排序本身，亦不代表是否值得投注。

## 9. Model Pick Status

```text
MODEL_TOP_PICK = rank <= 2 且 ability_score >= 70 且 confidence_score >= 55 且無 major / fatal risk flag
WATCH          = ability_score >= 70 但 confidence_score 不足，或存在 major risk flag
NO_PICK        = 其他
```

不輸出：

```text
BET
NO_BET
value bet
edge bet
fair odds
```

實際買唔買由用戶之後按即場賠率判斷，例如：

```text
Python top 2 + odds > 2 才考慮
```

## 10. Score Band Labels

Auto 版可以顯示 score band label 幫助閱讀，但 label 不參與任何計算或排序。

```text
90-100 = Elite
80-89  = Very Strong
70-79  = Strong
60-69  = Neutral / Usable
50-59  = Weak
0-49   = High Risk / Poor
```

顯示例：

```text
段速質量：82.4 / 100 (Very Strong)
騎練訊號：68.5 / 100 (Neutral / Usable)
```

禁止：

- 不顯示 tick。
- 不以 band label 排名。
- 不以 Grade 排名。

## 11. 7D Rating Matrix 詳細計法

### 11.1 `stability` 狀態與穩定性

目標：判斷馬匹近期是否可靠、狀態是否向上、輸都是否輸得近。

Python inputs：

- 近 6 / 10 場名次
- 頭馬距離趨勢
- 體重變化
- 出賽間距
- 可寬恕 / 作廢場次
- 近績波動

計法：

```python
stability_score =
    form_score * 0.45 +
    consistency_score * 0.40 +
    risk_score * 0.15
```

分段指引：

```text
85-100 = 近 10 仗入三甲 ≥70%，頭馬距離收窄，體重穩定，無重大風險
70-84  = 近 10 仗入三甲 ≥50%，或近 6 仗多次前列，輸得近
55-69  = 有走勢但波動，或資料中性
40-54  = 近績反覆、大敗多、頭馬距離擴大
0-39   = 連續大敗、健康未明、狀態明顯崩壞
```

特別規則：

- 明確醫療 / 受阻 / 慢閘等作廢場次，該場不得直接拖低 stability。
- 近 3 仗連續下滑且無寬恕：`downtrend_detected`，可降 5-12 分。
- 近 4 仗全部前 5 但 0 勝，需標記 `serial_placer_no_breakthrough`，避免將「穩定平庸」當成強穩定。
- 首出馬 stability 預設中性 60，不因無正式賽績判死刑。

### 11.2 `sectional` 段速質量

目標：判斷馬匹是否有足夠速度 / 時間能力，而不是靠形勢或賠率。

Python inputs：

- L400 / L600
- 完成時間偏差
- class par / standard time
- speed trend
- 同程 / 相近路程能量輸出
- trial / trackwork 替代資料（只限首出 / 輕驗馬）

計法：

```python
sectional_score =
    speed_score * 0.75 +
    distance_score * 0.25
```

分段指引：

```text
85-100 = L400/L600 全場前 15-20%，趨勢穩定或上升，完成時間偏差優於場均
70-84  = 段速全場前 30%，或 class par 有支持
55-69  = 段速中位，無明顯弱點
40-54  = 末段偏慢、完成時間偏差惡化
0-39   = 多次末段崩潰或速度明顯不足
```

禁止：

- 不用 pace prediction。
- 不用 leader count。
- 不用 race collapse / fast pace setup。
- 不因「估計會慢步速」而提升 sectional。

### 11.3 `race_shape` 檔位與走位（不含步速）

目標：保留現有 7D key，但 Auto 版只評估檔位、走位可行性、場地幾何，不評估步速。

Python inputs：

- HKJC 檔位統計
- track / surface / course / rail
- distance
- field_size
- barrier
- 上仗走位消耗 / blocked / wide trip
- 今日檔位相對改善或惡化
- horse known running style（只作走位可行性，不作 pace 預測）

計法：

```python
race_shape_score =
    draw_score * 0.70 +
    positioning_adjustment_score * 0.20 +
    track_geometry_score * 0.10
```

`positioning_adjustment_score` 只可由硬資料產生：

- 上仗外疊 / 受困 / 沿途蝕位，今仗檔位明顯改善：加 5-10。
- 上仗低消耗順暢仍大敗，今仗無改善：扣 5-12。
- 後追型 + 急彎短直路 + 外檔，只可作場地幾何風險，不可混入 pace。

### 11.4 `trainer_signal` 騎練訊號

目標：將現有 `07a_signals_framework.md`, `07b_trainer_signals.md`, `07c_jockey_profiles.md`, `07c_trainer_coldshot.md` 變成 Python 可審計規則。

Python 可以判斷「Top rider + 配搭 / 馬匹歷史有支持」，但必須有結構化 input。無 input 時只可中性或封頂，不能靠名氣加分。

需要 input fields：

```text
jockey_name
jockey_season_rank
jockey_win_rate
jockey_place_rate
jockey_last30_win_rate
jockey_last30_place_rate
jockey_profile_tags
trainer_name
trainer_tier
trainer_win_rate
trainer_place_rate
trainer_last30_win_rate
trainer_last30_place_rate
jockey_trainer_starts
jockey_trainer_wins
jockey_trainer_places
jockey_trainer_win_rate
jockey_trainer_place_rate
horse_jockey_starts
horse_jockey_wins
horse_jockey_places
horse_jockey_place_rate
horse_running_style
equipment_change
trainer_specific_signal
retained_jockey_status
last_jockey_rank
current_jockey_rank
```

計法：

```python
trainer_signal_score =
    jockey_component * 0.30 +
    trainer_component * 0.30 +
    combo_component * 0.25 +
    deployment_component * 0.15
```

高分 guardrails：

- `trainer_signal_score >= 80` 必須至少有兩個獨立硬 evidence，例如騎師本身能力 + 人馬歷史、練馬師部署 + 騎練 combo。
- `trainer_signal_score >= 85` 必須在 `jockey_component`, `trainer_component`, `combo_component`, `deployment_component` 四項中至少三項有正面 evidence。
- 只有名氣騎師 + 名牌練馬師，但無 combo / 人馬歷史 / tactical fit / deployment，最高 74。
- 有戰術誤配、弱 combo、主帥棄騎風險，最高 68，除非有兩項以上硬 evidence 對沖。
- 所有加分必須列出 source provenance；無 structured source 不可正面加分。

#### 11.4.1 `jockey_component`

細分公式：

```python
jockey_component =
    jockey_base_score * 0.45 +
    tactical_fit_score * 0.25 +
    horse_jockey_history_score * 0.20 +
    jockey_recent_form_score * 0.10
```

基礎分：

```text
HK Top 3 / HK Tier 1 jockey = 76-82
HK Top 10 / HK Tier 2 jockey = 68-75
海外 / 客串頂級騎師，有 structured elite profile = 72-82
海外 / 客串高質騎師，有 structured profile 但缺 HK 樣本 = 66-76
排名 10 名外但近期有表現 = 58-68
低勝率 / 無 structured profile / 缺資料 = 55-62
見習騎師 = 56 起，按減磅與馬匹跑法調整
```

重要 caps：

- 只有名氣、無 combo / 馬匹歷史 / tactical fit 支持：最高 72。
- 78+ 必須有至少一項硬支持：人馬歷史、騎練 combo、戰術匹配、近期狀態。
- 85+ 必須有兩項以上硬支持，而且無 major mismatch。
- Top rider 但 `sectional` 明顯弱：不可用騎師將整體推入 S/A。
- 首配不是自動扣分；只有 style mismatch 或高難度場景先扣。
- 見習騎師減磅只可作小幅正面，不可單獨成為強 signal。

`jockey_base_score`：

```text
HK Top 3 / Tier 1 且 season win/place rate 有支持 = 76-82
HK Top 10 / Tier 2 且近期無明顯低迷 = 68-75
海外 / 客串頂級騎師，有 structured elite profile = 72-82
海外 / 客串高質騎師，有 structured profile 但缺 HK 樣本 = 66-76
10 名外但近 30 日有勝出 / 多次入位 = 58-68
低勝率、休後復出、無 structured profile、資料不足 = 55-62
見習騎師 = 56 起，按減磅、跑法、場地風險細調
```

`jockey_base_score` 不等於 HK 排名。Python 必須先決定 `jockey_class_source`：

```text
1. HK current-season ranking / win-place rate，適用於常駐香港騎師
2. Local structured visiting jockey profile，適用於海外 / 客串 / 國際賽騎師
3. Starter PDF structured jockey stats，若有當日官方資料
4. Unknown fallback = 60 或 55-62，不可憑名字加分
```

海外 / 客串騎師規則：

- 例如 Ethan Brown、J Mac 呢類騎師，若 `jockey_profiles.json` 或 `07c_jockey_profiles.md` structured migration 有 `overseas_elite`, `G1_record`, `major_carnival_record`, `international_top_tier` 等有效欄位，可給 72-82 base。
- 無 HK season rank 不等於低分；但無 structured overseas profile 亦不可因「聽過個名」加分。
- 客串頂級騎師如果無 HK 同馬 / 同場地 / 同練馬師資料，base 可以高，但 `tactical_fit_score`、`combo_component` 應保持中性。
- 客串騎師首次跑 HK / 首次跑該場地，應加 `visiting_jockey_local_adaptation_unknown` reason code，並用 confidence 而非 base score 去反映不確定性。

`tactical_fit_score`：

```text
預設 = 60

只在有硬 evidence 時細幅調整：

+4 至 +6：
- 騎師近季 / 近 30 日於同場地有明顯高於個人平均位置率
- 騎師與此馬已有同程 / 相近路程入位紀錄
- 騎師過往騎此馬時，馬匹跑法穩定、名次或頭馬距離改善

+2 至 +4：
- 騎師本季於同場地 / 同 surface 表現高於自身平均
- 騎師過往騎此馬無明顯負面，且今日檔位未增加難度

-4 至 -8：
- 騎師過往騎此馬多次未能發揮，且無寬恕因素
- 騎師首配 + 馬匹有明確難騎標記
- 騎師於同場地 / 同 surface 明顯低於自身平均

無同場地 / 同馬 / 同程 hard evidence = 60，不加不扣
```

`tactical_fit_score` 禁止單靠靜態 profile 加高分。`front_running_skill`, `closing_skill`, `hv_skill`, `awt_skill` 只可作 reason code / display reference；除非同時有實際同場地、同馬、同程或相近路程結果支持，否則不可提升分數。

`horse_jockey_history_score`：

```text
horse_jockey_starts >= 2 且 place_rate >= 50% = 72-84
horse_jockey_starts >= 3 且 win_rate >= 20% = 78-88
horse_jockey_starts >= 3 且無入位 = 40-55
首次合作 = 60，除非 tactical mismatch
樣本少於 2 = 60-66，並加 small_sample_horse_jockey
```

`jockey_recent_form_score`：

```text
近 30 日勝率 / 位置率高於個人季內平均 = 66-78
近 30 日正常 = 58-66
近 30 日明顯低迷 = 45-58
無近況資料 = 60
```

騎師 reason codes：

- `elite_jockey_with_data_support`
- `famous_jockey_only_no_bonus`
- `positive_tactical_fit`
- `jockey_tactical_mismatch`
- `horse_jockey_combo_support`
- `small_sample_horse_jockey`
- `jockey_recent_form_positive`
- `jockey_recent_form_weak`

#### 11.4.2 `combo_component`

細分公式：

```python
combo_component =
    jockey_trainer_combo_score * 0.60 +
    horse_jockey_history_score * 0.40
```

騎練 combo（只限 structured field 存在時啟用）：

```text
starts >= 10 且 win_rate >= 20%        = 85-95
starts >= 10 且 place_rate >= 40%      = 78-88
starts >= 5  且 place_rate >= 35%      = 70-80
starts < 5 但有近期入位             = 62-72，並加 small_sample_combo
win_rate < 5% 且近 10 次無入位        = 35-50
無資料 / 只有 resource 例子無當季數據 = 60
```

人馬歷史：

```text
horse_jockey_starts >= 2 且 place_rate >= 50% = +4 至 +8
horse_jockey_starts >= 3 且無入位             = -4 至 -8
同人同馬近仗有明顯改善                        = +3 至 +6
首次合作                                      = 0，除非 profile mismatch
```

主帥制 / retained jockey 例外：

- 若騎師是練馬師主帥，屬預設安排，不可自動觸發黃金組合加分。
- 若主帥被外借到其他馬房，且資料顯示非預設安排，可標記 `retained_jockey_external_booking`.
- 若練馬師有主帥但不用，除非有合理原因，標記 `retained_jockey_bypass_risk`。
- 主帥制資料必須有 effective date；過期資料不得生效。
- 主帥制屬預設安排，只可計騎師本身能力，不可同時觸發 combo bonus。
- 無 current-season structured combo data 時，combo 一律 60，不可用靜態黃金組合例子加分。

combo reason codes：

- `positive_jockey_trainer_combo_structured`
- `elite_jockey_trainer_combo_structured`
- `weak_jockey_trainer_combo_structured`
- `missing_structured_combo_data`
- `retained_jockey_default_no_combo_bonus`
- `retained_jockey_external_booking`
- `retained_jockey_bypass_risk`

#### 11.4.3 `tactical fit`

Python 可用 `07c_jockey_profiles.md` 將騎師能力轉成 tags，但 tags 本身只係 display / reason-code reference，不可單獨加高分：

```text
front_running_skill
closing_skill
hv_skill
awt_skill
positioning_skill
drive_strength
```

計分原則：

```text
預設 = 60

只有以下硬 evidence 先可細幅加分：
- 騎師同此馬已有同程 / 相近路程入位或頭馬距離改善 = +4 至 +6
- 騎師於同場地 / 同 surface 表現高於自身平均 = +2 至 +4
- 騎師過往騎此馬無明顯負面，且今日檔位未增加難度 = +2 至 +4

以下硬 evidence 可扣分：
- 騎師過往騎此馬多次未能發揮，且無寬恕因素 = -4 至 -8
- 騎師首配 + 馬匹有明確難騎標記 = -4 至 -8
- 騎師於同場地 / 同 surface 明顯低於自身平均 = -4 至 -8
```

`tactical fit` 不可用「前置型 + front_running_skill」或「後追型 + closing_skill」直接加分，因為呢類 profile 偏靜態，亦容易將 pace / 跑法形勢偷偷帶返入模型。若無同場地 / 同馬 / 同程 hard evidence，tactical fit 中性 60。`horse temperament` 不可憑文字感覺入分。

#### 11.4.4 `trainer_component` / `deployment_component`

`trainer_component` 細分公式：

```python
trainer_component =
    trainer_base_score * 0.40 +
    trainer_recent_form_score * 0.20 +
    course_distance_pattern_score * 0.20 +
    stable_intent_evidence_score * 0.20
```

練馬師基礎：

```text
Tier 1 / 近期高勝率 = 72-82
Tier 2 / 主力穩定 = 65-74
Tier 3 / 中後段 = 56-66
無資料 = 60
```

`trainer_recent_form_score`：

```text
近 30 日勝率 / 位置率高於季內平均 = 66-78
近 30 日正常 = 58-66
近 30 日低迷 = 45-58
無近況資料 = 60
```

`course_distance_pattern_score`：

```text
同場地 + 同距離 / 相近距離有穩定勝率 = 68-80
場地專家但缺同距離支持 = 62-72
場地 / 距離無特別訊號 = 60
該場地 / 距離長期弱 = 42-58
```

`stable_intent_evidence_score` 只可由硬 trigger 產生：

```text
特定 trainer pattern 命中且所有欄位齊全 = 78-90
通用正面模式 >=2 個 = 72-84
通用正面模式 1 個 = 64-74
無部署訊號 = 60
負面部署 pattern = 40-56
```

部署訊號：

```text
特定 trainer signal 命中（07b 8.2d） = +8 至 +14
通用正面模式 >=2 個 = +8 至 +12
通用正面模式 1 個 + Tier 1 = +6 至 +10
騎師升級 = +4 至 +8
騎師下降 = -5 至 -10
頻繁換騎 / 找答案 = -5 至 -12
升班裸出 = -6 至 -12
```

不採用或需改寫嘅 trainer signals：

- 任何依賴 pace setup 嘅訊號不進分。
- `Pace Setup`, `慢步速`, `快步速`, `leader_count` 等只可 display-only 或完全停用。
- `ST -> HV` 轉場不可因「新鮮刺激」單獨加分，見 11.8。
- 練馬師不在 resource list = 無訊號中性，不可扣分。
- 場地專家只可小幅加分，不能單獨推到 80+。
- 特定 trainer pattern 必須所有 trigger fields 齊全；缺一項即不觸發。

deployment reason codes：

- `trainer_positive_deployment`
- `trainer_specific_pattern_triggered`
- `trainer_distance_class_pattern`
- `trainer_no_signal_neutral`
- `trainer_negative_pattern`
- `jockey_upgrade_signal`
- `jockey_downgrade_risk`
- `frequent_jockey_switch_risk`
- `class_rise_no_support_risk`
- `pace_dependent_trainer_pattern_disabled`

### 11.5 `horse_health` 馬匹健康 / 新鮮感

目標：衡量健康、休賽、體重、trackwork、資料完整度，並作 confidence / grade cap。

計法：

```python
horse_health_score =
    risk_score * 0.60 +
    freshness_score * 0.25 +
    body_weight_stability_score * 0.15
```

主要扣分：

- unresolved medical red flag：fatal。
- 久休無 trial / trackwork 支持：major。
- 體重大變、連續跌磅、操練中斷：major / minor。
- 過密出賽 + 加磅：major。
- 健康事故後已有復出證明，不可重複扣分。

### 11.6 `form_line` 賽績線

目標：使用 Facts.md 已抽取對手後續與強弱組，判斷「上仗 / 近仗賽績含金量」。賽績線唔係單純對手越強越高分，必須同時衡量馬匹自己有冇喺強組入面保持競爭力，避免「輸畀好馬但自己完全唔近」都被高估。

計法：

```python
form_line_score =
    opponent_strength_score * 0.40 +
    own_competitiveness_score * 0.40 +
    form_relevance_score * 0.20
```

三個 component：

```text
opponent_strength_score：
- 對手後續同級 / 高級贏馬、入位、升班再有表現 = 高
- 對手後續普通或資料不足 = 中性
- 對手後續弱、該場時間慢、同場多匹再出失準 = 低

own_competitiveness_score：
- 自己喺該強組輸得近、入前 25%、段速 / 完成時間偏差有支持 = 高
- 自己跑中游、輸 2-4L，有部分支撐 = 中性
- 自己大敗、包尾、輸 >6L，且無寬恕 = 低

form_relevance_score：
- 該場與今場同場地 / 同程 / 相近路程 / 同班或更高班 = 高
- 距離、場地、surface 差異大 = 降權
- 超過 24 個月或馬匹現況明顯不同 = 降權
```

分段：

```text
強組 + 自己跑近 / 有競爭力 = 75-90
強組 + 自己只屬中游 / 輸 2-4L = 62-74
強組 + 自己大敗無寬恕 = 最高 60
中組 / mixed evidence + 自己有競爭力 = 58-70
弱組但自己贏得有餘 / 段速有支持 = 58-72
弱組 + 自己只係普通表現 = 35-55
N/A = 60，且此維度可標記為 data_missing，不強行扣分
```

硬性 caps：

- 如果 `own_competitiveness_score < 45` 且無 `forgiven_run_major`，`form_line_score` 最高 60，即使對手很強。
- 如果馬匹喺強組輸 >6L 且無寬恕，`form_line_score` 最高 58。
- 如果馬匹喺強組輸得近但今場距離 / surface 完全不同，`form_line_score` 最高 72。
- 如果 Facts.md 只有「強組 / 弱組」文字，但無對手後續或自身距離 / 名次 evidence，`form_line_score = 60`，加 `insufficient_form_line_evidence`。
- 首出馬 / 無正式賽績馬：`form_line_score = 60` 或 N/A display，不可扣分。

reason codes：

- `strong_form_line_competitive`
- `strong_form_line_but_not_competitive`
- `weak_form_line_cap`
- `form_line_distance_relevance`
- `form_line_surface_mismatch`
- `insufficient_form_line_evidence`
- `opponent_follow_up_supported`
- `opponent_follow_up_weak`

### 11.7 `class_advantage` 級數優勢

目標：拆開真級數、official rating、升降班、負磅與路程級數。

計法：

```python
class_advantage_score =
    class_score * 0.45 +
    weight_score * 0.30 +
    distance_score * 0.25
```

分段：

```text
超級降班 + 高班近距離輸 + 負磅合理 = 80-92
同班穩定競爭 + 負磅中性 = 65-78
升班但輕磅 / 近績強 = 60-75
升班太急 + 加磅 / 頂磅 = 40-58
評分見頂 + 近期不足 = 35-55
```

### 11.8 `track_going_score` 場地 / 場地狀態處理

`track_going_score` 仍然保留為 sub-score，但不再係獨立 7D 維度。它主要餵：

- `race_shape`
- `horse_health`
- `class_advantage`

ST -> HV 轉場規則修正：

- 不應因「沙田轉跑馬地可能有新鮮刺激」直接加高分。
- Python 可以捕捉 ST -> HV，但只可在有硬 evidence 時作正面：
  - 首跑 HV + 沙田同程 / 相近路程曾入三甲：`st_to_hv_supported_by_st_distance_form`，小幅加分。
  - 首跑 HV + 好檔 + trainer 有明確 HV transfer signal：`trainer_hv_transfer_supported`，小幅加分。
  - 已有 HV 同程入位 / 贏馬：直接用 HV record，不當作轉場幻想。
  - HV 同程 ≥3 次全失敗：轉場 signal 失效。
- 若只有「由 ST 轉 HV」但無賽績、檔位、trainer pattern 支持：中性 60，reason code `unproven_track_transfer`。
- AWT -> HV 不適用 ST -> HV 正面轉場邏輯。

## 12. 12 個 Sub-Score 詳細計法

### 12.1 form_score 近績分

來源：

- 近 6 場名次
- 頭馬距離
- 可寬恕 / 作廢因素
- 最近趨勢
- 賽績線強弱
- 出馬數 / 名次百分位
- 該場班次 / rating band
- 同場 / 同程 / 相近路程 context
- 賽事短評 structured tags，例如受阻、外疊、慢閘、醫療、不適

核心原則：

- `form_score` 評估近期賽績質量，不是只數名次。
- Python 必須先做法醫過濾，再計分：先判斷作廢 / 寬恕 / 低可信度場次，之後先計加權近績。
- 近 6 場係主計分窗口；近 10 場只用作趨勢、鐵腳 / 長期穩定、突然贏馬回落、沉睡專家回師等輔助檢查。
- 資料不足時用中性 60，不可因缺資料直接扣成差馬。

近 6 場權重：

```text
最近一場 30%
第二近   22%
第三近   18%
第四近   12%
第五近   10%
第六近    8%
```

如果近 6 場內有作廢場次：

- `medical_auto_void`, `severe_blockage_auto_void`, `stewards_finding_auto_void` 場次從主加權計算排除。
- 排除後剩餘權重按比例重新 normalize 至 100%。
- 如果有效場次少於 3 場，`form_score` 最高 72，並加 `limited_valid_form_sample`。
- 如果只有 0-1 場有效正式賽，`form_score = 60`，交由 debut / trackwork fallback 處理。

每場基礎分先按名次 / 出馬數計：

```text
勝出                     = 92-96
第2名                    = 82-88
第3名                    = 74-82
第4名                    = 64-72
第5名                    = 58-64
第6-8名                  = 45-58
第9名或以後              = 32-48
無名次資料               = 60
```

出馬數 / 名次百分位修正：

```text
12 匹或以上跑第 4-5，且頭馬距離接近 = 可較同名次高 3-6 分
小場 6-7 匹跑第 4-5 = 不可當強近績，扣 3-6 分
跑入前 25% = +2 至 +5
跑入後 30% = -4 至 -10
包尾或接近包尾 = -8 至 -15，除非作廢 / 寬恕
```

頭馬距離修正：

```text
勝出或輸 <= 0.5L      = +8 至 +12
輸 0.5L 至 1.0L       = +5 至 +8
輸 1.0L 至 2.0L       = +2 至 +5
輸 2.0L 至 4.0L       = 0 至 -5
輸 4.0L 至 6.0L       = -8 至 -15
輸 > 6.0L             = -15 至 -25
無頭馬距離資料         = 0，並加 missing_margin_data
```

班次 / 含金量修正：

```text
高一班或以上近距離輸        = +4 至 +8
同班近距離輸                = +2 至 +5
低班勝出但升班受壓          = 0 至 -5
降班前高班大敗但無寬恕      = 最高 68
弱組 / 慢時間勝出            = 最高 78，除非段速另有支持
強組 / 對手後續有支持        = +3 至 +6
```

法醫作廢 / 寬恕規則：

```text
medical_auto_void              = 該場排除，不入 weighted form
severe_blockage_auto_void      = 該場排除或權重降至 25%
stewards_finding_auto_void     = 該場排除
forgiven_run_major             = 權重減半，分數不可低於 58
forgiven_run_minor             = 權重保留，但該場扣分最多減半
wide_trip / blocked / slow_away = 按嚴重程度加 reason code，必要時降權
```

趨勢修正：

```text
近 3 場名次或頭馬距離連續改善 = +4 至 +8
近 3 場名次或頭馬距離連續惡化 = -6 至 -12
近 4 場全部前 5 但 0 勝，且至少 1 次入三甲 = 不扣 form_score，但加 serial_placer_no_breakthrough
近 4 場全部前 5 但 0 入三甲 = form_score 最高 72，避免穩定平庸被高估
近 4 場中 >=3 場第 4-6 名且 0 入三甲 = form_score 最高 68
5-6 歲上仗突然勝出，但近 10 仗入三甲 <=2 = 加 sudden_win_regression_risk，form_score 最高 78
近 3 場連續第 8 名或以後，且無寬恕 = form_score 最高 55
```

小樣本 / 質新馬：

```text
出賽 <=5 場且已有入三甲 = 可正常計，但 confidence 扣小樣本風險
出賽 <=5 場且近 3 場連續改善 >=3 位 = +5 至 +8，reason code rising_lightly_raced_profile
出賽 <=5 場但單次好表現、其他資料不足 = form_score 最高 76
初出馬無正式賽績 = form_score 60；不可用試閘直接當正式近績分
```

最終計法：

```python
valid_runs = forensic_filter(last_6_runs)
weighted_run_score = sum(run.adjusted_score * run.normalized_weight for run in valid_runs)
form_score = weighted_run_score + trend_adjustment + class_quality_adjustment
form_score = apply_caps(form_score, form_caps)
form_score = clip(form_score, 0, 100)
```

reason codes：

- `close_margin_recent_form`
- `strong_recent_win`
- `high_class_close_loss`
- `weak_class_win_cap`
- `forgiven_run_major`
- `forgiven_run_minor`
- `medical_auto_void`
- `severe_blockage_auto_void`
- `stewards_finding_auto_void`
- `downtrend_detected`
- `improving_recent_profile`
- `serial_placer_no_breakthrough`
- `stable_but_not_winning`
- `sudden_win_regression_risk`
- `limited_valid_form_sample`
- `missing_margin_data`

輸出必須顯示：

- 逐場分
- 逐場權重
- 是否作廢 / 寬恕
- 頭馬距離修正
- 出馬數 / 名次百分位修正
- 班次 / 強弱組修正
- trend adjustment
- caps applied
- final `form_score`

### 12.2 speed_score 速度 / 時間表現分

來源：

- L400 / L600
- 完成時間偏差
- energy trend
- class par / standard time
- 正式賽段速

不使用：

- race pace prediction
- leader count
- on pace / backmarker
- pace collapse

規則：

```text
正式賽 L400/L600 明顯高於同班 class par = 82-92
L400 穩定偏快 + 完成時間偏差佳 = 72-85
段速普通但無明顯弱點 = 58-68
反覆慢、末段衰退、大敗無寬恕 = 35-55
無段速資料 = 60
```

保護：

- 只有 trial / trackwork，不可高於 70，除非初出馬專用規則。
- 單次閃光不可直接給 85+，必須有穩定或 class par 支持。
- 健康事故場次需先由 forensic filter 判斷是否作廢。

### 12.3 class_score 班次適應分

來源：

- 今場班次
- 升班 / 降班 / 同班
- 官方評分趨勢
- 高班近距離輸
- 同班表現
- 同場平均 official rating

規則：

```text
高班近距離輸 / 降班有支持 = 78-90
同班穩定競爭 = 68-78
升班但近績強 = 62-75
升班太急 / 高班大敗 = 40-58
降班但近期大敗無寬恕 = 最高 68
```

reason codes：

- `class_drop_with_close_high_class_form`
- `same_class_competitive`
- `class_rise_supported`
- `class_rise_too_fast`
- `class_drop_but_poor_recent_form`

### 12.4 jockey_score 騎師分

來源：

- 騎師季內勝率
- 位置率
- 近期狀態
- 騎師 + 練馬師配搭
- 騎師 + 馬匹配搭
- `07c_jockey_profiles.md`
- structured overseas / visiting jockey profile
- Starter PDF structured jockey stats

計法：

```python
jockey_score =
    jockey_base_score * 0.45 +
    tactical_fit_score * 0.25 +
    horse_jockey_history_score * 0.20 +
    jockey_recent_form_score * 0.10
```

規則：

```text
HK top rider + structured combo / 人馬歷史 / tactical fit 有硬數據支持 = 78-90
海外 / 客串頂級騎師 + structured elite profile + 硬數據支持 = 76-88
Top rider 但只有名氣、無配搭或馬匹支持 = 65-72 cap；structured overseas elite 可放寬至 76 cap
HK Top 10 / Tier 2 + 場景合適 = 68-78
海外 / 客串高質騎師但缺 HK / 同馬 / 同場地樣本 = 66-76
普通騎師或無資料 = 58-65
低勝率 / 換弱騎 / tactical mismatch = 40-58
```

限制：

- HK jockey ranking 不是騎師能力唯一來源；它只係常駐香港騎師嘅其中一個 source。
- 海外 / 客串騎師必須由 structured local profile 或 Starter PDF structured stats 證明，不可由 LLM / web / 名氣推斷。
- 不可單靠名氣加分。
- Famous jockey only 不可觸發高分，最高 72。
- Structured overseas elite profile 代表有能力 base，但不代表 automatically 85+；85+ 仍然需要同馬、同場地、同練馬師、近期狀態等至少兩項硬 evidence。
- 78+ 必須有至少一項硬 evidence；85+ 必須有兩項以上硬 evidence。
- Python 必須先檢查 `horse_jockey_history`, `jockey_profile_tags`, `horse_running_style`；如要用 `jockey_trainer_combo`，必須有 structured current-season starts/wins/places，才可給 78+。
- 若 combo / horse history 樣本不足，需加 `small_sample_jockey_support`，並限制加分幅度。
- 若騎師 profile 顯示戰術誤配，加入 risk flag。
- 見習騎師減磅只可小幅調整，不可單獨建立強 positive signal。

`jockey_class_source` 優先次序：

```text
1. HK current-season rank / win-place rate
2. Structured visiting jockey profile with effective date
3. Starter PDF structured jockey stats
4. Unknown fallback
```

海外 / 國際賽騎師處理：

```text
international_elite / overseas_elite profile = base 72-82
overseas_high_quality profile = base 66-76
visiting jockey with no structured profile = 60
visiting jockey first HK / first venue run = add visiting_jockey_local_adaptation_unknown
elite overseas profile + no local/horse/trainer support = cap 76
elite overseas profile + horse/trainer/course support = eligible for 78-88
```

reason codes：

- `elite_jockey_with_data_support`
- `overseas_elite_jockey_structured_profile`
- `visiting_jockey_local_adaptation_unknown`
- `visiting_jockey_no_structured_profile`
- `positive_jockey_trainer_combo_structured`
- `horse_jockey_combo_support`
- `famous_jockey_only_no_bonus`
- `jockey_tactical_mismatch`

### 12.5 trainer_score 練馬師分

來源：

- 練馬師季內勝率
- 位置率
- 近期狀態
- 同路程 / 同班次部署
- 初出 / 第二次上陣表現
- 冷門部署 / 反差配
- `07b_trainer_signals.md`
- `07c_trainer_coldshot.md`

計法：

```python
trainer_score =
    trainer_base_score * 0.40 +
    trainer_recent_form_score * 0.20 +
    course_distance_pattern_score * 0.20 +
    stable_intent_evidence_score * 0.20
```

規則：

```text
練馬師近況強 + 場景吻合 = 75-88
部署正面但證據一般 = 65-75
普通 / 無明顯訊號 = 58-65
冷廄、部署反覆、弱 pattern = 40-58
```

限制：

- 練馬師不在 resource list = 無訊號中性，不可自動扣分。
- 場地專家 / 距離專家只可小幅支持，不可單獨推上 80+。
- 特定 trainer pattern 必須所有 trigger fields 齊全；缺一項即不觸發。
- 任何 pace-dependent trainer pattern 必須停用或 display-only。

reason codes：

- `trainer_positive_deployment`
- `trainer_distance_class_pattern`
- `trainer_coldshot_signal`
- `trainer_no_signal_neutral`
- `trainer_negative_pattern`

### 12.6 draw_score 檔位分

來源：

- HKJC draw stats
- track
- surface
- course
- distance
- field_size
- barrier
- draw starts
- draw wins
- draw places
- draw win rate
- draw place rate

不使用主觀 rule：

```text
內檔好
外檔差
```

匹配優先次序：

```text
1. track + surface + course + distance + field_size
2. track + surface + course + distance
3. track + surface + distance
4. track + distance band
5. 無資料 -> draw_score = 60 + missing_draw_data
```

公式：

```python
draw_win_rate_index = draw_win_rate / setup_average_win_rate
draw_place_rate_index = draw_place_rate / setup_average_place_rate
sample_confidence = min(1.0, starts / 100)

draw_index =
    draw_win_rate_index * 0.45 +
    draw_place_rate_index * 0.45 +
    sample_confidence * 0.10
```

draw_index 轉分：

```text
>= 1.40   = 90-100
1.20-1.39 = 78-89
1.05-1.19 = 68-77
0.95-1.04 = 58-67
0.80-0.94 = 48-57
< 0.80    = 低過 48
```

樣本數保護：

```text
starts >= 100 -> 正常計
50-99         -> draw_score 限制 45-85
25-49         -> draw_score 限制 50-78
<25           -> draw_score 限制 55-70
無資料        -> draw_score = 60
```

輸出必須顯示：

- matched level
- draw starts / wins / places
- win index
- place index
- sample confidence
- sample cap
- final draw_score

### 12.7 distance_score 路程分

來源：

- 同程 record
- 相近路程 record
- 最近 24 個月同程 / 相近路程紀錄
- 全 career 同程 / 相近路程紀錄（只作 fallback / 降權）
- best distance
- 今次增程 / 減程
- 父系 / 母系名稱（只作顯示，除非日後有本地 structured sire stats）
- 初出馬試閘 / 晨操替代資料

樣本範圍：

- `distance_score` 不限近 6 場。
- 近 6 場主要用嚟計近期狀態、近況走勢同穩定性，不應限制路程適性樣本。
- 同程 / 相近路程優先用最近 24 個月紀錄。
- 如果最近 24 個月樣本不足，再 fallback 到全 career 同程 / 相近路程。
- 超過 24 個月嘅舊賽績可以保留作背景，但必須降權，因為馬匹年齡、班次、能力同健康可能已經變化。
- 若近期表現與舊同程強績明顯矛盾，近期正式賽證據優先。

相近路程定義：

```text
短途 1000-1200m：相差 <= 200m
中距離 1400-1800m：相差 <= 200m；特殊場地可放寬至 400m，但要降權
長途 2000m+：相差 <= 400m
```

規則：

```text
同程勝 / 多次入位 = 78-90
相近路程強 + 今程合理 = 68-80
首試但血統/走勢支持 = 58-72
首試缺資料 = 55-65 + unproven_distance
同程多次失敗 = 35-55
```

限制：

- 已有充分正式同程實績時，父系 / 母系名稱只可作背景，不可壓過實績。
- 首出馬可用 trial / trackwork 作替代；sire / dam 只可在日後有 structured sire stats table 時入分，否則不加分。

### 12.8 track_going_score 場地 / 場地狀態分

來源：

- Sha Tin / Happy Valley record
- Turf / AWT record
- going record
- track module
- venue transfer
- AWT kickback / surface risk

規則：

```text
同場同面勝 / 多次入位 = 75-88
場地適應正常 = 62-72
場地轉換未證明 = 55-65
場地明顯不合 = 35-55
無資料 = 60
```

場地 modules：

- `10a_track_sha_tin_turf.md`
- `10b_track_happy_valley.md`
- `10c_track_awt.md`

步速相關內容只可 display-only，不可入 score。

### 12.9 weight_score 負磅分

來源：

- 今場負磅
- 全場 median weight
- lightest / top weight
- 比上仗加減磅
- 見習騎師減磅
- 升降班互動
- 路程修正

規則：

```text
低於中位數且非弱馬 = 68-80
中性負磅 = 58-66
頂磅但級數支持 = 52-64
頂磅 + 加磅 + 中長途 = 35-55 + top_weight_pressure
升班加磅 = 額外扣分
降班重磅 = 扣分較少
```

特別 caps：

- 3YO + >=133lb：major risk。
- HV + heavy weight gap：按距離調整 risk。
- Quick backup + 加磅：疊加 risk。

### 12.10 consistency_score 穩定性分

來源：

- 近 6 場名次波動
- 頭馬距離趨勢
- speed consistency
- running profile consistency
- 連續下滑
- 連續前列但無突破

規則：

```text
長期前 5 / 輸得近 / 少大敗 = 75-88
有上名但波動 = 62-74
連續下滑 = 40-58
反覆大敗 = 30-50
初出 / 資料不足 = 60 或按晨操完整度調整
```

reason codes：

- `stable_recent_profile`
- `close_margin_consistency`
- `volatile_form`
- `downtrend_detected`
- `serial_placer_no_breakthrough`

### 12.11 risk_score 風險分

高分代表低風險。由 100 開始扣分。

Major risk 每個扣 12-20：

- 久休無復課支持
- 未跑過今程且缺替代證據
- 未跑過場地且場地轉換不利
- 近期大敗無寬恕
- 升班太急
- 頂磅中長途壓力
- 健康事故未證明恢復
- AWT 食沙 / 場地適應風險
- draw data missing 或樣本太低

Minor risk 每個扣 5-10：

- 資料部分不足
- 換騎未知
- 配備變動未驗證
- 體重波動
- 間距稍短 / 稍長

Fatal risk：

- unresolved medical red flag
- wrong hard data / missing core data
- scratched horse
- logic JSON corrupted

Fatal risk 直接：

- `model_pick_status = NO_PICK`
- Grade 最高 B+
- `confidence_score` cap 50

### 12.12 confidence_score 信心分

信心分不是能力分。

```python
confidence_score =
    consistency_score * 0.35 +
    risk_score * 0.35 +
    data_completeness_score * 0.30
```

`data_completeness_score` 檢查：

- 近績資料
- 段速資料
- 班次 / rating 資料
- 騎師資料
- 練馬師資料
- draw stats
- 路程資料
- 場地資料
- 負磅資料
- 健康 / trackwork 資料

每缺一個重要資料組，扣 5-12。資料少但 ability_score 高，應輸出 `WATCH`。

## 13. 7D Output / Template Layer

舊 7D matrix 繼續出現，而且係 Auto 版正式 rating matrix。分別係：舊版由 LLM 填 tick；Auto 版完全取消 tick，改為 Python numeric score + Python NLG 理由。

| 7D Section | Python Sources | 顯示內容 |
|---|---|---|
| 狀態與穩定性 | `form_score`, `consistency_score`, `risk_score` | 近績、穩定性、風險扣分 |
| 段速質量 | `speed_score` | L400/L600、時間偏差、class par |
| 檔位與走位（不含步速） | `draw_score` | HKJC 檔位統計、matched level、sample cap |
| 騎練訊號 | `jockey_score`, `trainer_score` | 騎師、練馬師、配搭 |
| 馬匹健康 / 新鮮感 | `risk_score` | 健康、休賽、trackwork、freshness |
| 賽績線 | `form_score`, `class_score` | 對手後續、強弱組 |
| 級數優勢 | `class_score`, `weight_score`, `distance_score` | 班次、負磅、路程 |

每個 section 必須 render：

- numeric score
- score band label，例如 `Strong 78.4` / `Neutral 62.1`，只作閱讀輔助，不參與排序
- score weight
- weighted contribution
- raw evidence
- reason codes
- risk flags
- Python judgement text：自然語言解釋點解 Python 畀呢個分

每個 section 嘅 Python judgement text 要類似而家 Wong Choi 逐項 matrix reasoning，但由 Python template NLG 產生：

```text
狀態與穩定性 76.8 / 100：
近六場加權近績分 74.2，頭馬距離最近三仗由 3.5L 收窄至 1.2L，穩定性分 78.0；不過近四仗未有勝出，所以未能升入 85+ 區間。
```

```text
騎練訊號 69.5 / 100：
今場騎師屬 Top 10，騎師基礎分有支持；此馬同騎師歷史只得一次合作，樣本不足，未能觸發強配搭加分。練馬師部署未見完整 structured signal，所以維持中性偏正面。
```

禁止：

- 不顯示舊 tick symbols 作為評分。
- 不用 tick count 排名。
- 不用 Grade 排名。
- 不用 LLM 寫 section reasoning。

## 14. Python Core Logic NLG 詳細規格

`core_logic` 必須由 Python `core_logic_nlg.py` 生成。

硬性限制：

- `core_logic_nlg.py` 只可使用 Python template NLG、固定 phrase bank、reason-code mapping、score-band mapping。
- 不可呼叫 OpenAI / Claude / Gemini / local LLM / browser AI / shell 外部模型。
- 不可將 Python output 交俾 LLM 改寫成自然語言。
- 不可用 LLM 做「文字潤飾」、「補原因」、「判斷風險」、「寫 verdict」。
- 同一 input 必須逐字產生同一 `core_logic`。
- 若資料不足，Python 必須用 deterministic fallback 句式標示資料不足，而不是交俾 LLM 補空白。

輸入：

- scores
- grade
- rank
- model_pick_status
- top scoring components
- weakest scoring components
- reason_codes
- risk_flags
- score_breakdown
- 7D grouped summary

輸出風格：

- 香港賽馬廣東話。
- User-facing text 必須全香港中文；internal key 只可在 JSON / CSV 欄位名保留英文。
- 自然段落，不似 JSON dump。
- 3 至 5 段。
- 至少 120 至 250 中文字，視資料量調整。
- 不使用「自動生成」「系統判定」「具備一定競爭力」等罐頭句。
- 不提賠率。
- 不以步速作核心理據。
- 同一 input 產生同一 output。
- 所有句子必須能追溯到 `matrix_scores`, `feature_scores`, `score_breakdown`, `reason_codes`, `risk_flags`。
- Report 文字必須用 `模型首選 / 觀望 / 不選`，不可直接顯示 `MODEL_TOP_PICK / WATCH / NO_PICK`。
- Report 文字必須用 `風險分 / 信心分 / 能力分`，不可直接顯示 `risk_score / confidence_score / ability_score`。

段落結構：

1. **總評段**：排名、能力分、Grade、模型狀態中文顯示。
2. **主要加分段**：描述最高 2-3 個 7D 維度及其背後 sub-scores。
3. **次要支撐段**：如 class / distance / track / jockey / trainer 有支撐，補充。
4. **風險段**：描述最低 1-2 個分數與風險標記。
5. **信心段**：解釋信心分，說明點解係模型首選 / 觀望 / 不選。

例：

```text
呢匹馬排第 1，能力分 82.4 屬 A 級，模型狀態係模型首選。佢唔係單靠一項亮點撐起，而係近績、段速同檔位三個板塊都企得住，所以整體基本面比同場大部分馬完整。

主要加分位係近績分 84.0、速度分 79.5 同檔位分 86.0。近六場有穩定前列走勢，頭馬距離未見明顯擴大；正式賽末段數據亦高過中性線，唔似純靠形勢。檔位方面，HKJC 檔位統計顯示今次檔位嘅勝率同上名率都高過同配置平均，樣本數亦夠支持。

風險方面，負磅分只有 56.0，代表今場負擔唔算輕；風險分 62.0 亦提示仍有加磅或資料完整度不足嘅問題。整體而言，佢係模型首選；Auto 只輸出基本面排序同風險判讀，實際投注與否由用戶另行處理。
```

## 15. Analyst Resources Migration Matrix

每份 HKJC analyst resource 必須標記 adopted / adopted-partial / excluded / display-only。

| Resource | Auto Python 用途 | Status |
|---|---|---|
| `00_sip_index.md` | 審計 active / retired baked rules | adopted |
| `sip_changelog.md` | 確保最近規則無遺漏 | adopted |
| `01_system_context.md` | 保留 anti-hallucination、WorkCard、data integrity 規則 | adopted |
| `02_data_retrieval.md` | 定義可信 Python input fields | adopted |
| `03_engine_pace_context.md` | Legacy/display only；不進 scoring | display-only |
| `04_engine_corrections.md` | 只採用非步速 correction | adopted-partial |
| `05_forensic_analysis.md` | form/speed/consistency/risk/forgiveness/medical filtering | adopted |
| `05b_debut_guide.md` | 初出馬 scoring fallback、confidence cap、risk flags | adopted |
| `06_rating_engine.md` | caps/floors/micro-adjustments/longshot safety net 轉 Python rules | adopted |
| `07a_signals_framework.md` | 騎練 signal 共用定義 | adopted |
| `07b_trainer_signals.md` | `trainer_score` / `trainer_signal`；pace-dependent trainer signals excluded | adopted-partial |
| `07c_jockey_profiles.md` | `jockey_score` / tactical fit / retained jockey rules | adopted |
| `07c_trainer_coldshot.md` | 冷門部署 reason codes | adopted |
| `08_templates_core.md` | 報告風格 only | display-only |
| `08_templates_rules.md` | verdict format only，不准 LLM 排名 | display-only |
| `09_verification.md` | 轉 QA gates/tests | adopted |
| `10a_track_sha_tin_turf.md` | track/distance/draw/going rules，排除 pace | adopted-partial |
| `10b_track_happy_valley.md` | HV draw/weight/distance/track rules，排除 pace | adopted-partial |
| `10c_track_awt.md` | AWT surface/kickback/draw/track rules | adopted |
| `11_factor_interaction.md` | SYN/CON/CONTRA 轉 caps、risk flags、confidence adjustment | adopted |

## 16. Python Module 設計

新增：

```text
.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/racing_engine/
  features/
    form.py
    speed.py
    class_rating.py
    jockey.py
    trainer.py
    draw.py
    distance.py
    track_going.py
    weight.py
    consistency.py
    risk.py
    confidence.py
  scoring.py
  matrix.py
  grading.py
  pipeline.py
  core_logic_nlg.py
  data_availability.py
  reason_codes.py
  validation.py
  resource_mapping.py
```

Core output contract：

```python
{
  "feature_scores": {
    "form_score": 0-100,
    "speed_score": 0-100,
    "class_score": 0-100,
    "jockey_score": 0-100,
    "trainer_score": 0-100,
    "draw_score": 0-100,
    "distance_score": 0-100,
    "track_going_score": 0-100,
    "weight_score": 0-100,
    "consistency_score": 0-100,
    "risk_score": 0-100,
    "confidence_score": 0-100
  },
  "matrix_scores": {
    "stability": 0-100,
    "sectional": 0-100,
    "race_shape": 0-100,
    "trainer_signal": 0-100,
    "horse_health": 0-100,
    "form_line": 0-100,
    "class_advantage": 0-100
  },
  "matrix_reasoning": {
    "stability": "Python generated section reasoning",
    "sectional": "Python generated section reasoning",
    "race_shape": "Python generated section reasoning",
    "trainer_signal": "Python generated section reasoning",
    "horse_health": "Python generated section reasoning",
    "form_line": "Python generated section reasoning",
    "class_advantage": "Python generated section reasoning"
  },
  "ability_score": 0-100,
  "grade": "A",
  "rank": 1,
  "model_pick_status": "MODEL_TOP_PICK",
  "reason_codes": [],
  "risk_flags": [],
  "data_availability": {},
  "score_breakdown": {},
  "core_logic": "Python generated natural language explanation"
}
```

## 17. Logic JSON Integration

Each horse receives:

```json
"python_auto": {
  "version": "HKJC_AUTO_SCORE_V1",
  "feature_scores": {},
  "matrix_scores": {},
  "matrix_reasoning": {},
  "ability_score": 0,
  "grade": "A",
  "rank": 1,
  "model_pick_status": "MODEL_TOP_PICK",
  "reason_codes": [],
  "risk_flags": [],
  "data_availability": {},
  "score_breakdown": {},
  "core_logic": "",
  "seven_dimension_display": {}
}
```

Race-level receives:

```json
"python_auto_verdict": {
  "ranking": [],
  "top2": [],
  "top4": [],
  "model_top_picks": [],
  "watch_list": [],
  "no_pick": []
}
```

## 18. Output Template Integration

現有 template 保留，但改 render source：

- `最終評級` 讀 `python_auto.grade`
- Top 4 排序讀 `python_auto_verdict.top4`
- `核心邏輯` 讀 `python_auto.core_logic`
- 舊 `評級與tick數量` 改為 `ability_score / grade / confidence_score / risk_score`
- 7D matrix 區塊 render `matrix_scores` + `matrix_reasoning` + `seven_dimension_display`
- Auto 必須使用獨立 renderer / compiler branch；不可直接沿用 classic tick renderer。
- 舊 `矩陣算術` 改為 `分數算術`。
- `tick_count` 移除，不可在 Auto Analysis 或 CSV remark 出現。
- `步速修正偏差` 改為 `時間偏差 / 段速偏差`。
- `走位-段速複合` 改為 `走位成本與檔位改善`。
- CSV 加入：
  - 7D `matrix_scores`
  - 12 `feature_scores`
  - `ability_score`
  - `rank`
  - `grade`
  - `confidence_score`
  - `risk_score`
  - `model_pick_status`
  - `reason_codes`
  - `risk_flags`

如保留步速相關版面，必須標示：

```text
Not used in Python scoring
```

### 18.1 如何融入現有 Analysis.md 觀感

Auto 版唔重寫整份 report design。原則係「舊 template、新 data owner」：

| 現有 output 區塊 | Auto Python render source | 變化 |
|---|---|---|
| Race summary / 場次資料 | existing extractor fields | 保持原樣 |
| 每匹馬基本資料 | Racecard + Facts.md | 保持原樣 |
| 7D matrix | `python_auto.matrix_scores` + `matrix_reasoning` | tick 改 numeric score；每節保留文字判讀 |
| 核心邏輯 | `python_auto.core_logic` | 由 Python NLG 生成，不經 LLM |
| 最終評級 | `ability_score` + `grade` | Grade 只作參考；排序仍以 score |
| Top 4 / verdict | `python_auto_verdict.top4` | 按 numeric `ability_score` 排序 |
| CSV remarks | Python phrase bank | 不准 LLM rewrite |

每匹馬每個 7D section 必須顯示：

```text
段速質量：82.4 / 100（強）
權重：22%
加權貢獻：18.13
Python 判讀：L600 及完成時間偏差均高於同場平均，同程速度有支持；但最近一仗末段未能再加速，所以未入 90+。
主要證據：L600 全場第 2 / 12，完成時間偏差 -0.42 秒，路程分 76.0
原因代碼：strong_l600, above_par_finish_time, distance_supported
風險標記：無
```

舊 Wong Choi 入面由 LLM 寫嘅「每節馬匹分析」會改成 Python deterministic section reasoning。文字可以自然，但必須由 template NLG + reason code mapping 組成。

### 18.2 Ranking / Grade / Score Display

Auto output 必須同時顯示：

- 全場排名
- 能力分
- `grade`
- 7D section scores
- 12 feature scores，可在詳情或 CSV 顯示
- 信心分
- 風險分
- 模型狀態（模型首選 / 觀望 / 不選）

Top 4、Top 2、全場排名只可以根據 `ability_score` 排序。Grade 只是由分數派生出來嘅 reference label，不可反過來改排名。

## 19. Validation Rules

Fail if scoring contains：

- `odds_score`
- `market_score`
- `value_score`
- `fair_odds`
- `edge_pct`
- `pace_score`
- `pace_derived_race_shape`
- `expected_speed`
- `leader_score`
- `on_pace_score`
- `backmarker_score`
- `llm_commentary`
- `llm_reasoning`
- `model_commentary`
- `ai_generated_analysis`

Fail if：

- feature scores / 7D matrix scores missing
- score outside 0-100
- `ability_score` formula mismatch
- `rank` not sorted by `ability_score`
- Top 4 not sorted by `ability_score`
- Grade used as a sorting key
- `grade` threshold mismatch
- `core_logic` empty
- `core_logic` contains forbidden generic phrases
- `core_logic` or verdict text is not produced by `core_logic_nlg.py` / Python renderer
- any matrix section missing `matrix_reasoning`
- any matrix section reasoning does not cite its numeric score or source evidence
- any Auto script imports or calls an LLM provider for output generation
- any Auto JSON field is marked `[FILL]` for LLM completion
- `MODEL_TOP_PICK` violates gating rules
- any score lacks source provenance in `score_breakdown`
- a disabled / unavailable field is used for positive scoring
- Auto user-facing report contains `tick_count`
- Auto user-facing report contains classic `矩陣算術`
- Auto user-facing report contains `步速修正偏差` or `走位-段速複合`
- Auto user-facing report directly displays `MODEL_TOP_PICK / WATCH / NO_PICK` instead of 香港中文 mapping
- Auto user-facing report directly displays `risk_score / confidence_score / ability_score` instead of 香港中文 mapping
- Auto core logic / section reasoning contains odds / 賠率 / value / 值博率 wording
- same input produces different scoring output

## 20. Implementation Phases

1. Finalize this plan.
2. Create `hkjc-wong-choi-auto.md` agent.
3. Create `hkjc_wong_choi_auto/SKILL.md`.
4. Add Auto resources: scoring contract, resource migration matrix, output mapping.
5. Build typed parsers and `data_availability.py` gate.
6. Build 12 sub-score Python package, each scorer reading typed fields only.
7. Build draw scorer using HKJC draw stats.
8. Build risk/confidence scoring.
9. Build S-tier grade / caps / guards.
10. Build detailed Python `core_logic_nlg.py`.
11. Build Auto wrapper for existing `Race_X_Logic.json`.
12. Build Auto verdict ranking by 7D-derived `ability_score`.
13. Build validation module.
14. Build independent Auto compiler/render adapter for 7D numeric matrix + 12 sub-scores，不可沿用 classic tick renderer。
15. Add tests.
16. Run historical dry run / calibration set，檢查 score distribution、Top4 stability、S-tier 是否過鬆或過緊。
17. Adjust weights / caps only through versioned Python config and test fixtures，不准 LLM tuning。
18. Run sample meeting dry run.
19. Compare output style against classic Wong Choi.
20. Decide whether Auto remains separate or becomes default later.

## 21. Tests

Unit tests：

- `form_score` high / neutral / low / missing.
- `speed_score` official sectional / trial-only / missing.
- `class_score` class drop / class rise / same class.
- `jockey_score` elite supported / famous only / weak fit.
- `jockey_score` top rider with no combo / horse history / tactical fit is capped at 72.
- `jockey_score` top rider + weak `sectional` cannot push horse into S/A by rider name alone.
- `jockey_score` apprentice allowance only small-adjusts and cannot create a strong signal alone.
- `jockey_score` tactical mismatch creates risk flag and cap.
- `trainer_score` positive deployment / no signal / coldshot.
- `trainer_score` Tier 1 with no deployment signal remains neutral-to-positive, not high.
- `trainer_score` trainer not in resource list remains neutral, not negative.
- `trainer_score` pace-dependent pattern disabled.
- `combo_component` current-season strong combo / small sample cap / missing structured data neutral.
- `combo_component` retained jockey default arrangement does not add combo bonus.
- `combo_component` retained jockey external booking adds reason code only when effective-date rule is valid.
- `draw_score` exact match / fallback / missing / sample cap.
- `distance_score` same distance / first try / failed distance.
- `track_going_score` same track / transfer / AWT risk.
- `weight_score` light / neutral / top weight pressure.
- `consistency_score` stable / volatile / downtrend.
- `risk_score` major / minor / fatal.
- `confidence_score` complete / partial / insufficient data.
- `core_logic_nlg` deterministic and natural.
- `core_logic_nlg` no LLM call / no network model call.
- `matrix_reasoning_nlg` produces deterministic natural HK Chinese for all 7D sections.
- `data_availability` marks extractable / conditional / unavailable fields correctly.
- disabled fields such as unstructured jockey-trainer combo, horse temperament, and Sire AWD cannot increase scores.

Integration tests：

- Existing `Race_X_Logic.json` -> Auto scoring -> updated JSON.
- Meeting folder -> all Race logic files scored.
- Top4 order equals 7D-derived `ability_score` order.
- 7D matrix drives ranking; 12 sub-scores only feed 7D.
- Grade labels match scores but do not affect Top4 order.
- Each horse output displays `ability_score`, `grade`, `confidence_score`, and all 7D section scores.
- No `[FILL]` in scoring fields.
- No `[FILL]` in `core_logic`, 7D reasoning, verdict, CSV remarks, or any Auto-rendered report field.
- Auto run succeeds in an environment with no LLM credentials.
- Removing a source field changes only the linked feature to neutral / missing, not to guessed values.
- Template compatibility test：Auto rendered `Analysis.md` keeps existing Wong Choi section structure while replacing LLM judgement with Python scores / Python reasoning.
- Template language test：Auto rendered `Analysis.md` user-facing text uses 香港中文 labels for 模型首選 / 觀望 / 不選、能力分、信心分、風險分。
- Template anti-tick test：Auto rendered `Analysis.md` contains no `tick_count`, no classic `矩陣算術`, and no tick symbols as scoring display.
- Template anti-pace test：Auto rendered `Analysis.md` contains no `步速修正偏差` or `走位-段速複合`; replacement labels are `時間偏差 / 段速偏差` and `走位成本與檔位改善`.
- Calibration test：sample historical races produce sane score spread，不可出現大部分馬同分、S-tier 過多、或 major risk 馬仍被標記 `MODEL_TOP_PICK`。

Regression tests：

- Same input twice = same scores / rank / grade / core_logic.
- Forbidden scoring fields fail validation.
- Forbidden LLM fields fail validation.
- Grade threshold exact boundary tests for S+, S, S-, A+, A, B+, B, C, D.

## 22. Acceptance Criteria

Implementation is accepted when：

- Old HKJC Wong Choi still works unchanged.
- Auto agent exists separately.
- Auto skill exists separately.
- Existing extraction outputs can be scored by Auto.
- Every horse has 12 sub-scores, 7D matrix scores, ability score, grade, rank, pick status, risk flags, reason codes, core logic.
- Every score has source provenance and availability status.
- S-/S/S+ grades supported with confidence/risk guardrails.
- 7D output retained as the official rating matrix.
- No tick scoring, no tick count, no derived tick display.
- Top 4 and all race ranking are sorted by `ability_score`.
- Grade is reference-only and never used for sorting.
- Every 7D section displays numeric score and Python-generated section reasoning.
- No odds/market/pace scoring enters `ability_score`.
- `core_logic` is Python-generated natural HK Chinese and covers multiple scoring sections.
- All user-facing Auto text is 香港中文; internal English keys may remain in JSON / CSV headers only.
- Auto output contains no `tick_count`, no classic `矩陣算術`, and no odds / 賠率 / value / 值博率 wording.
- Auto pipeline has zero LLM dependency and zero LLM-generated text.
- Historical dry run / calibration report reviewed before Auto becomes production default.
- Tests pass.
