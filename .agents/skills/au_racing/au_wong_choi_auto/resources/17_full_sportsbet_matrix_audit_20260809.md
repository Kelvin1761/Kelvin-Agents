# AU Wong Choi — Full Sportsbet / Matrix Audit (2026-08-09)

## Executive decision

今次由現役 code path 重新開始，固定用 **805 場／8,249 匹** current-runtime snapshot，
結果只喺 scoring 完成後 join。Development／terminal holdout 按完整日期切成
**594／211 場**，唯一升級閘門係 Top-5 within-race paired AUC：development delta 不可負，
terminal 95% race-bootstrap CI 下限必須大過 0。

結論：

- Racenet → Sportsbet 現役 runtime migration 已完成；舊 `racenet_*` 只剩 archive PF
  provenance compatibility，唔會發網絡請求。
- 修復三個 migration/alignment bug：Sportsbet 綵衣 DOM 次序、早期 Racecard 人名冇回填
  Logic、薄樣本 trainer 被錯寫成「冇官方記錄」。
- `class_score` 已退出排名，亦唔再錯誤計入 ability coverage；仍保留 report context。
- Dashboard preview 將 leaf 收入真正 parent matrix，唔再把同一票顯示兩次。
- 現役 ability spine 保持六維。冇證據支持 Top-2 lock、rank-3/4 rerank、track-specific
  hard rule、濕地加碼、重新啟用賽績線或再重配 matrix。
- 唯一通過 terminal canonical gate 嘅能力升級係 point-in-time
  `performance_quality_score`，其餘候選全部拒絕。

## Sportsbet field utilisation inventory

### Meeting / race metadata

| Extracted field | Runtime use | Status / evidence |
|---|---|---|
| venue, race number, distance, class | Race identity、cohort、class/distance context、對齊結果 | Active |
| track condition | `track_score`、wet overlay、meeting display | Active；Good/Soft/Heavy 分 cohort 驗證 |
| weather, rail, start time | Meeting intelligence / display | Context only；未證明 incremental ranking value |
| runner number / horse name | 全 pipeline primary alignment key | Active；Facts/Logic/Racecard 會 hard-validate |
| people IDs / linked names | Trainer/jockey cache join | Active；現時 linked-name match 100% |
| fixed win/place odds | 存檔及 dashboard context | Not in ability；mutable market snapshot 唔用作歷史能力訓練 |
| scratched | 抽取時剔除 | Active correctness guard |
| silk URL | Racecard `Silk:` → dashboard | Active display；有缺失時保留 graceful fallback |

### Runner overview

| Extracted field | Runtime use | Status / evidence |
|---|---|---|
| trainer, jockey | People score、人馬配搭、輸出身份 | Active；早期 Logic blank 已由同馬 Racecard 回填 |
| age / sex | Racecard / context | Display/context；未另造重複 ability leaf |
| days since last run | 原始 Formguide 保存 | Dated last-run record 先係 scoring source；避免 mutable overview leakage |
| career | Career stage / class context | Active |
| win%, place%, Ave$ | 原始資料保存 | Mutable overview；歷史 candidate 有高表面 AUC但可包含 target race，拒絕入分 |
| last6 | Facts recent-form transport | Active only after target-date/future censor |
| official rating | Field-relative `rating_score` | Active；72.11% runners 用官方 rating |
| current odds | Dashboard / research | Report-only；唔當 horse ability |

### Career / condition stats

| Sportsbet stat | Runtime use | Status / evidence |
|---|---|---|
| Weight | Report、wet burden、missing-rating handicap proxy | Active context；standalone `weight_score` report-only/inverse |
| Career / Win / Place | Career evidence | Active indirectly；唔另加重複 long-term vote |
| Track / Distance / Trk-Dist | Same-track / distance evidence | Track active；distance report-only |
| Firm / Good / Soft / Heavy / Synthetic | Today-going suitability / wet evidence | Active；完整 record parser 已修正 |
| 1st / 2nd / 3rd Up | Stage context | Report/context；standalone value不足，唔入 rank |
| Jockey (J/H overview) | 原始 Formguide保存 | Mutable target-inclusive risk；rank 用 dated pre-race rides/wins/places 取代 |
| 12 months / Turf / Win Range / Prizemoney / Ave$ | Display / research | 未證明 point-in-time incremental value；不加 signal |

### Historical run rows

| Extracted field | Runtime use | Status / evidence |
|---|---|---|
| date / track / going / distance / class / prize | Point-in-time form、quality、distance、class context | Active；只接受 `run_date < meeting_date` |
| finish / field / margin | `form_score`、`performance_quality_score` | Active；field/margin candidates 已逐項測試 |
| jockey / barrier / weight | Dated J/H history、shape/context | Active or contextual |
| SP / fluctuation | 保存作 report | Not in ability；歷史時點一致性不足 |
| settled / 800m / 400m | Run-shape evidence | Parsed；全局 shape alternatives未過 gate，唔加新 vote |
| Sectionals 600m | Historical-race L600 environment | Active as race-level context；唔冒充 runner individual split |
| opponents / follow-up | `formline_score` | Report-only；恢復 1–10% 權重全部不過 gate |

### Sportsbet people pages

| Field family | Runtime use | Status |
|---|---|---|
| LY rides / wins / places | Jockey / trainer score with minimum sample + shrinkage | Active primary source |
| career / 12-month / recent / going / distance / field-size / prize buckets | Cache / research | Current-page snapshot唔係 historical point-in-time；未升級 |

Sportsbet 現時唔提供可靠、已接入嘅 pedigree wet proxy；Sire/Dam transport 留空時唔會扮成
中性能力訊號。

## Migration and alignment defects fixed

1. **綵衣 DOM order**：Sportsbet current markup 係 runner number → `runner-silks` image；舊
   parser只認 image → number。兩種 sibling order 而家都支援。Ballarat 8 場 raw capture
   分別取得 `11/13/12/15/10/9/10/13` 個 silk；dashboard smoke 經 scratched filter 仍有
   `8/12/10/12/10/7/9/12`。
2. **Racecard identity recovery**：早期 Sportsbet Facts header冇 jockey/trainer，舊 Logic
   因而留空；Racecard 同馬其實有完整名字。依 horse-name keyed Racecard profile回填後，
   people linked-name match由 98.7% 變 100%，分析唔再顯示 `騎師: - / 練馬師: -`。
   Canonical comparison八項 ranking metric全數 `0.00pp`，屬 correctness fix，冇冒認性能增益。
3. **Trainer thin-sample narrative**：Brian Lawlor `6:0-0-0` 係有資料、但未達 10 場可信
   門檻。輸出改為明講薄樣本按中性，只有真正無 Sportsbet統計先叫 missing。
4. **Track record schema**：`1: 0-0-0` 以前被 `\S+` 截成 `1:`，之後仲可能跨欄把 Distance
   數字當 wins。現時只接受完整 `starts:wins-seconds-thirds`，partial token當 missing。
5. **PF provenance**：Sportsbet 600m係 historical-race environment，唔再硬標成 runner-level
   Racenet CFB。Archive `racenet_*` provenance保留，因為語意確實唔同。
6. **Ability coverage registry**：`class_score` 已係 report-only但仍計入 ability coverage；
   現已移出，active ability leaf由 11 正確變 10。
7. **Evaluation ruler**：散落工具嘅 Gold/Good/Pass 舊定義集中到一個 adapter；主評估只剩
   `au_eval.py` 一把 canonical 尺。
8. **Dead Racenet code**：移除三個只會請求 Racenet 嘅 backfill/temp/season-gap scripts，
   safe-mode文件改為 retired redirect；現役文檔改用 Sportsbet。

## People / rating / J-H coverage

| Source | Usable official sample | Thin sample | Absent | Exact 60 | 58–62 |
|---|---:|---:|---:|---:|---:|
| Jockey | 99.26% | 0.05% | 0.69% | 0.65% | 10.51% |
| Trainer | 96.50% | 0.67% | 2.84% | 3.10% | 20.79% |

Pre-Sportsbet people-cache regression estimate約為 jockey 63% / trainer 51%；current measured
coverage係 99.26% / 96.50%。所有已連結姓名正規化比對 100%。

Rating source：

- official field-relative rating：5,948 / 8,249（72.11%）；
- class proxy：1,008（12.22%）；
- class + handicap-only field-relative weight proxy：1,293（15.67%）。

Maiden 有 996 匹，當中 190 匹仍有 official rating；其餘主要係未評分馬。WFA/SW 會拒絕
weight proxy，唔會把性別／年齡定磅當能力。

人馬配搭：48.71%有 current jockey × horse 正式賽 history，35.43%有其他 pre-race context，
15.86%完全冇 scoring evidence而按 archive cohort校準到 58。其分佈 mean 62.41、SD 3.99、
range 55.89–74.40、AUC 0.546（terminal 0.555）。移除後 dev Top-5 AUC `-0.0045`、
terminal `-0.0041`，Gold `-1.12pp`、Good `-1.61pp`、Pass `-0.87pp`；保留現有 shrink，
唔擴闊 tiny-sample 分數。

## System-wide neutral saturation audit

`fallback` 係 evidence state，唔一定等於 neutral。例如 performance quality fallback係舊
consistency實證，仍有 AUC；所以唔可以見 fallback高就強行 widen。

| Feature | Role | Mean | Median | SD | Min–Max | =60 | 58–62 | fallback | AUC all / terminal |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| form | rank | 58.50 | 57.22 | 11.63 | 35.47–100 | 6.93% | 17.95% | 5.18% | .610 / .615 |
| trial | rank | 72.19 | 69.00 | 10.77 | 58–100 | 29.19% | 29.93% | 29.93% | .554 / .550 |
| sectional | report | 68.29 | 62.74 | 10.28 | 60–100 | 46.22% | 46.22% | 27.36% | .537 / .550 |
| draw / pace-map | rank | 60.55 | 60.58 | 2.61 | 50.57–64.05 | 1.65% | 50.25% | 0% | .527 / .511 |
| jockey | rank | 59.37 | 58.37 | 9.11 | 32.66–94.39 | 0.65% | 10.51% | 0.65% | .594 / .594 |
| trainer | rank | 60.07 | 61.69 | 8.68 | 25.16–97.63 | 3.10% | 20.79% | 0% | .590 / .617 |
| J/H fit | rank | 62.41 | 62.31 | 3.99 | 55.89–74.40 | 0% | 36.61% | 16.64% | .546 / .555 |
| class | report | 59.74 | 60.00 | 3.42 | 47.73–67.52 | 22.68% | 49.35% | 3.78% | .558 / .531 |
| rating | rank | 59.88 | 59.34 | 5.65 | 47–73.50 | 1.79% | 29.24% | 27.89% | .585 / .589 |
| weight | report | 59.84 | 60.00 | 1.47 | 53–63 | 83.11% | 83.11% | 5.64% | .479 / .482 |
| distance | report | 58.94 | 61.00 | 5.11 | 49–66 | 16.71% | 54.69% | 5.18% | .556 / .559 |
| same-track/going | rank | 66.30 | 63.70 | 7.16 | 42.94–86.74 | 0% | 5.04% | 12.23% | .529 / .508 |
| formline | report | 65.05 | 63.00 | 9.18 | 53–100 | 10.75% | 13.52% | 8.69% | .508 / .539 |
| consistency | report | 77.77 | 77.62 | 13.75 | 46.10–100 | 0% | 6.32% | 5.18% | .593 / .578 |
| performance quality | rank | 77.23 | 77.62 | 15.71 | 0–100 | 0% | 4.70% | 89.25% | .612 / .651 |
| health | report | 60.41 | 61.00 | 0.88 | 55–61.40 | 17.31% | 98.16% | 0% | .519 / .497 |
| confidence | report | 82.66 | 84.00 | 6.07 | 63–92 | 0% | 0% | 0% | .529 / .553 |
| L600 environment | rank | 60.05 | 60.23 | 19.26 | 0–100 | 5.88% | 13.29% | 5.84% | .584 / .574 |

Flagged outcomes：

- `weight_score`係唯一長期反向項，已 report-only；能力訊號由 rating承擔，唔反向重加。
- `health`幾乎全中性且 terminal接近隨機，維持 report risk context，唔扮 ranking vote。
- `class`、`distance`、`sectional`有少量 standalone value但 incremental candidate均失敗，
  留 report-only。
- `draw/pace-map` spread細係原始 contextual evidence弱，唔人工放大。
- Rating/JH並非「全部 60」；display matrix gain後 rating parent SD 10.88，J/T parent SD 12.19。

## 場地分 / 場地適性

兩者原本唔係兩次投票：`track_score`係唯一 leaf，`track`係 `60 + deviation × display gain`
後嘅 parent matrix。模型相關係 1.0，ranking只食一次。問題係 UI/命名令人以為重複。

現改名：

- parent：`場地與地況適性`；
- debug child：`同場／地況往績分`。

Preview只顯示 parent一次，child留喺 reason/deep analysis。Track standalone AUC .529、terminal
.508；移除後 development AUC `-0.0016`、Gold `-1.12pp`、Pass `-0.62pp`，所以未有證據
刪除；但最新 drift偏弱，列入 forward monitor。

## Draw, wet and course findings

### Draw

以 track+distance、track、field-size rolling hierarchy重建嚴格 point-in-time draw，所有同日賽果
要當日完結後先加入：相對現行 static archive lookup，dev `-0.0092`、terminal `-0.0075`
（CI `[-0.0174,+0.0024]`）；相對 neutral draw亦係 dev `-0.0038`、terminal `-0.0065`。
新 contextual draw model未證明價值，唔 ship。現行 barrier leaf保留，但歷史 static bias有
look-ahead風險，唔用佢宣稱新性能提升。

### Soft / Heavy

Good/Firm、Soft、Heavy Gold分別 18.7% / 15.4% / 12.4%；Good分別 30.6% / 24.3% /
17.4%。濕地係真弱點。但 wet overlay scale 0、0.5、0.75、1.25、1.5 全部未過 gate：
最有方向嘅 ×0 terminal AUC `+0.0078`，CI `[-0.0016,+0.0176]`，而 Gold `-0.99pp`。
保持 ×1.0；唔因 cohort差就硬加濕地權重。

### Racecourses

樣本 20+ 場中 Eagle Farm 最弱（45場：Top1 win 6.7%、Good 15.6%、Gold 2.2%、
Winner@3 33.3%）；Rosehill Good 8.9%，Geelong Winner@3 36.0%。相反 Pakenham、
Cranbourne較強。Feature direction按場變化，但 course sample細、移除 track/shape喺日期窗
互相衝突；冇 course-specific hard adjustment通過。Eagle Farm列為 data-quality／individual
ability forward investigation首位，唔用 45 場過擬合。

## 賽績線 recovery

賽績線定義係「本駒近期對手其後升班／再贏嘅成色」，唔係純 `3-7-2-5`。Sportsbet opponent
rows已正確接入；問題係 follow-up稀疏同訊號重複，而唔係 parser仍等 Racenet。

Canonical matrix測試：

- existing opponent-followup @1/2/5/10%；
- reconstructed normalised recent quality（45%近績、40% margin/prize quality、15% class）
  @1/2/5/10%。

8個候選全部不過 gate。Opponent 5/10%令 Good約 `-1.12/-0.99pp`；normalised 5/10%
令 Good `-1.24/-1.49pp`、Pass `-1.24/-1.99pp`。維持 report-only；唔叫「冇資料」，
而係「已有資料但未有 incremental ranking value」。

## Simplification / incremental value

Active leaf移除全部令 development變差；最清楚三條：

| Removed signal | Dev Top-5 AUC Δ | Terminal Δ / CI | Gold | Good | Pass |
|---|---:|---:|---:|---:|---:|
| performance quality | -0.0035 | -0.0181 `[-.0321,-.0046]` | -0.12pp | -1.86pp | -1.49pp |
| jockey | -0.0137 | -0.0173 `[-.0321,-.0022]` | -0.87pp | -2.24pp | -3.48pp |
| rating | -0.0123 | -0.0103 `[-.0225,+.0021]` | -0.37pp | -2.24pp | -3.48pp |
| J/H fit | -0.0045 | -0.0041 `[-.0132,+.0060]` | -1.12pp | -1.61pp | -0.87pp |
| track | -0.0016 | +0.0012 `[-.0043,+.0071]` | -1.12pp | 0.00pp | -0.62pp |

刪整個 stability或 people matrix，terminal CI全負。因此簡化重點係剷 dead code、重複顯示、
錯 registry同多套 evaluator，而唔係剷仍有能力值嘅 leaf。

## Before vs current performance

Old係 performance-quality branch未啟用、用 consistency fallback嘅舊 production；current係
point-in-time performance quality。完全同一 805 場、同一日期 split：

| Metric | Old | Current | Delta |
|---|---:|---:|---:|
| Gold（actual Top3全入 model Top4） | 16.15% | 16.77% | +0.62pp |
| Good（model Top1+Top2都上名） | 24.60% | 25.71% | +1.12pp |
| Pass（model Top3中兩匹上名） | 45.59% | 47.20% | +1.61pp |
| Top1 win | 25.34% | 25.22% | -0.12pp |
| Winner@3 | 55.16% | 56.27% | +1.12pp |
| Winner@5 | 74.66% | 75.53% | +0.87pp |
| Top3 precision | 46.83% | 47.70% | +0.87pp |
| Top-5 paired AUC | .68673 | .69294 | +.00622 |

Terminal Top-5 AUC delta `+.02374`，95% CI `[+.01260,+.03569]`，正式通過 gate。
Top1 win微跌 0.12pp，所以唔應宣稱「所有指標都升」；整體 Top3 ordering／coverage提升係
robust，單一冠軍率未改善。

## Current rank capability

- Top1 win/place：25.22% / 54.66%；
- winner inside Top2/Top3/Top4/Top5：43.48% / 56.27% / 67.08% / 75.53%；
- Top2 individual place rate：52.55%；Good（兩匹都上名）25.71%；
- actual Top3 fully inside model Top3/Top4/Top5：6.58% / 16.77% / 31.06%；
- winner ranked #3/#4：23.60%；
- rank #3/#4有 actual placer而 Top2未能雙上名：50.93%。

錯序 pair唔係被單一 weak signal壓低：actual lower-ranked horse喺 stability、PF/L600、J/T、
rating、track幾乎全部都較 false Top2低。呢個支持尋找新、正交、point-in-time individual
ability evidence，唔支持鎖 Top2後微調 slot。

## Dashboard consolidation

Preview而家按實際 engine parent分組：模型摘要、騎練、狀態與賽績、場地與環境、賽事形勢、
能力與級數、其他資料。`騎師／練馬師／JH`同`同場／地況往績分`留喺 parent reason；唔再
各自變第二張卡。Full analysis仍保留每個 leaf、來源、分數、權重同 in-ranking狀態，方便 debug。

## Regression evidence

- AU Wong Choi Auto suite：361 tests（最後一個 coverage expectation同步 active 10-leaf
  registry後重跑）；
- focused engine/dashboard parser：pass；
- frontend Vite production build：pass；
- Python compile：pass；
- `git diff --check`：pass；
- Sportsbet silk cache + dashboard parser smoke：pass。

## Recommended next evidence, not next micro-rule

1. 保存更多 forward、source-labelled Sportsbet individual ability fields（尤其完整 dated margin、
   field strength、market expectation snapshot如日後獲授權）。
2. Eagle Farm / large-field 13+建立獨立 data-quality monitor；未到足夠日期窗前唔加 track rule。
3. People page going/distance buckets要先有真正 race-date snapshot，否則唔可用 current cache做
   歷史提升證據。
4. 繼續用單一 canonical evaluator；任何研究 script只可產候選，最終判決全部回到 `au_eval.py`。
