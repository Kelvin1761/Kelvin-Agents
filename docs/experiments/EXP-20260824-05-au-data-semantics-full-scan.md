# EXP-20260824-05 AU 全鏈資料語義、對齊及 leakage 審計

- **日期**：2026-08-24
- **平台**：AU Wong Choi（Sportsbet-only）
- **範圍**：Sportsbet HTML → parser → Racecard/Formguide → Facts → Logic →
  RacingEngine → renderer → data-health/deploy gate → archive evaluation。
- **起因**：Randwick R9 Aeliana 嘅第 4+ 試閘名次存在於 Sportsbet，但舊
  Formguide transport 將佢變成「無試閘資料」；用戶要求唔理佢係咪唯一升至第二嘅
  原因，都要修正，並全面找同類資料語義／錯配問題。
- **判決**：**KEEP correctness fixes；不改 matrix 權重；不聲稱 aggregate 改善。**

## 審計方法與語料

1. canonical runtime corpus：1,411 場／14,109 匹；whole-date dev/terminal 分割沿用
   `docs/model-evaluation-contract.md`，冇改把尺。
2. Sportsbet cache 靜態掃描：1,500 檔，包括 516 個賽事頁、697 個人物頁及 287 個
   其他頁；逐行核對原始 `Finished`、in-running、winning time、barrier、weight、
   profile block 同 parser transport。
3. Sportsbet index point-in-time trial replay：174 meetings／1,450 race pages；只接受
   `trial date < target meeting date`，SP／結果從未進入 scorer。
4. 全 archive data-health：203 meetings；另外對 Randwick R9 以現役 full pipeline
   重播。
5. leakage／alignment regression：127 tests，涵蓋 point-in-time、PQ、PF、Facts
   refresh、runtime dataset、cache alignment、trial transport、renderer 及主 orchestrator。

## Confirmed bugs 與修正

| 問題 | 根因 | 修正／防再發 |
|---|---|---|
| 第 4+ 試閘變「無資料」 | parser 以前只 transport top-3 boolean，冇保存確實名次 | `finish:N/M` 全程保存；現役 engine 直接讀名次；有觀察但近三課全未入前三加 `trial_no_recent_top3`，分數沿用已存在嘅 56 base，唔重複扣分 |
| `Finished 6/ 5.50L` 變假 `6/5` | Sportsbet 部分行省略 field size，舊 regex 把 margin 整數位當 field | field 缺失時保留 place + margin、field 留 `None`，禁止捏造 `finish:N/M`／`starters:N` |
| 頭馬勝距當輸距 | `Finished 1/N 5.75L` 嘅 token 對頭馬係勝距 | parser、archived Facts rebuild、engine digest 三層頭馬 beaten margin 歸零；完整結果見 EXP-20260824-04 |
| scratched runner 假 source mismatch | AU Racecard 保留 `status:Scratched` 編號行，Logic 正確剔除 | data-health source number/name 只比較 active runners；加 regression |
| data-health CLI import 失敗 | `PROJECT_ROOT` 少行上一層，實際指向 `.agents` | 修正 root resolution；standalone CLI 可直接運行 |
| AU full orchestrator 冇 alignment gate | auto score 後只跑 compliance，source/Logic/render mismatch 未攔 deploy | scoring 後、deploy 前新增 AU meeting data-health gate；單檔及 meeting 入口都覆蓋 |
| 兩個 audit 工具 stale import | 仲 import 已退休 top-level `racing_engine` | 改用 package `au_racing_engine`，避免 AU/HK 同名 module 撞名 |
| renderer 漏計部分 formline follow-up | engine 接受「出 N 次」及「見前三 N 次」，renderer 只接受前者 | renderer 同 engine 共用語義：兩種精確勝場描述都計 franking |

## 原始欄位與 runner alignment 結果

- 歷史 runs：raw 63,709／parsed 63,520（99.70%；差額係 regex corpus 定義比
  實際完整 run block 闊，唔係 active runner 丟失）。
- 63,515 個有完整 field size 嘅 finish：**63,515 全部滿足 1 ≤ place ≤ field**，
  `finish:N/M` transport **100%**。
- 5 個來源省略 field size 嘅 runs：而家全部保留 placing，field 明確為 unknown。
- active overview → profile block：5,239／5,239（100%）；barrier／weight 100%。
- 非 top-3 trial placings preserved：7,663。
- in-running transport：46,048／46,123（99.84%）；1200m checkpoint
  12,788／12,816（99.78%）；winning time 47,505／47,607（99.79%）。

Winning time 係 race-level context，未經 track × distance × going 嘅 point-in-time
標準化前唔入分。人物頁 Distance／Barrier／Field Size／Spells 表雖然 697/697 存在，
頁面會滾動更新；現時只可由今日起做 versioned snapshot，唔可倒灌歷史避免未來資訊洩漏。

## Feature／source distribution audit

- 所有 ranking leaf 都有場內散佈；冇發現 live dead／constant feature。
- trial score：mean 71.8、SD 10.8、fallback 31.7%、全樣本／terminal AUC
  0.555／0.554；即係「有資料 vs 無資料」語義重要，但 trial 唔係主要矩陣權重。
- jockey usable history ≥10：97.51%；trainer：89.94%；成功 link 後 name match 100%。
- official rating 66.91%；class proxy 7.85%；只在合資格 handicap 使用嘅 class/weight
  proxy 25.23%。
- same-track／going record container 100% 存在；`track_score` 係單一 leaf，冇重複投票。

## Aeliana 修正及 R9 重播

Sportsbet 賽前可見試閘為：8/9、4/5、6/8、8/8。舊模型將 archived 缺名次行當
fallback 60，冇 risk；新 pipeline 得到 observed 56，並清楚列出
`trial_no_recent_top3`。呢個係正確區分：

- 無試閘資料：保守中性 60（已出賽馬）；
- 有試閘、近三課全部未入前三：observed 56 + visible risk。

用當前 Sportsbet cache full replay（有效檔位按退出馬重排，故唔可將全部分差歸因於
trial）排序為：

| 排名 | 馬 | 分數 | Trial | 備註 |
|---:|---|---:|---:|---|
| 1 | Sheza Alibi | 86.742 | — | 頭馬 margin 語義已修 |
| 2 | Autumn Glow | 82.909 | — | 實際冠軍 |
| 3 | Aeliana | 81.879 | 56 | observed poor-trial risk |

重點係兩匹明顯星馬維持 Top 2、Aeliana 唔再排第二，而且報告唔再講成「無試閘」。
但 Aeliana 原先第二係多因子（強往績、class/rating、騎練、wet）共同造成，唔係單靠
trial fallback。

## Canonical A/B：只恢復 fallback trial placings

設計只替換 captured runtime 中 `feature_evidence_state= fallback`、而 Sportsbet 賽前
實際已有 trial placing 嘅 row；原本 observed trial score 完全不動，冇調參。

- 10,352 匹成功對齊；7,927 匹原本已 observed，保持不變。
- 2,425 匹 fallback 有可恢復試閘證據；37 匹 trial score 真正改變。
- 12／1,411 場排序有變。

| 指標 | 變化 |
|---|---:|
| dev 頭 5 AUC | +0.000062（+0.0062pp） |
| terminal 頭 5 AUC | 0.000000；CI [0,0] |
| Gold | 0.000pp |
| Gold Strict | +0.071pp |
| Good位置／Pass／winner@3 | 0.000pp |
| Top-3 precision | +0.024pp |

判決係 correctness **KEEP**、model promotion **不適用／證明唔到改善**。修正冇整體
傷害，但 effect 太細，唔需要 refit matrix 權重。

## Archive health 判讀

203 個歷史 meeting 入面，67 OK、17 warning、119 error；主要係舊 schema snapshot
缺現役 feature（11,361 個 `MISSING_FEATURES`）同舊 coverage metadata（8,510 個
`NO_COVERAGE`），唔係現役 extractor 今日突然死欄位。5 個 source mismatch 集中舊
Sale／Randwick artifacts；3 個 ambiguous source 係同一資料夾同時有 `Race 1` 及
`Race 1-7` 舊命名。呢啲 archive 唔可當 live regression 樣本直接 deploy。

現役 Randwick R9 full replay：11 匹、coverage 96.4%、0 error／0 warning；新 gate
會喺日常 AU orchestrator deploy 前自動攔真正 active-runner mismatch。

results ingest dry-run 發現 1,429 場中 52 場結果太薄、另有 54 個尚未入 CSV 嘅
same-day rows；scheduler 已有正式 ingest，今次冇將賽後結果寫返 pre-race artifacts。

## 驗證

- targeted semantic／leakage／alignment tests：127 passed。
- AU golden：120 匹全部一致（重錄後再驗）。
- AU data contract：867 場／8,727 匹重校準；最近 60 場全部欄位符合基準。
- model docs：由 `explain_model.py` 生成並通過新鮮度檢查。
- `./檢查.sh --quick`：全部通過。

## 結論與剩餘界線

今次清除咗所有審計中**可重現、可證實**嘅現役資料語義／alignment bugs，並加咗
deploy gate 防止同類錯配靜靜出街。唔可以科學上保證將來永遠「零 bug」；目前剩低係：

1. 舊 archive 已遺失嘅 trial placing 不可逆，只可用仍存在嘅 Sportsbet cache 重建；
2. 滾動人物 profile 未有歷史 snapshots，禁止回填做舊賽 scoring；
3. 舊 schema health error 應與 live gate 分開處理，唔可以用今日 contract 假裝舊檔當時
   已有資料。

現役 scoring weights、wet overlay 及 pace-perf 公式今次全部冇因單場結果改動。
