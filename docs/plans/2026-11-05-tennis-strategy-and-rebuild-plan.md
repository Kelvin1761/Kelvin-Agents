# Tennis Wong Choi：全面重建 + 盈利策略 + 精選 + 夜晚落注 —— 總計劃

- 建立：2026-11-05（Claude Code，同 Kelvin 對話整理）
- 狀態：**階段一／二已實作（EXP-20261105-08），等部署**；階段三（全面重建）未開始。Codex 已停手，tennis 由呢份計劃接手。
- 階段一／二實際做咗：`tennis_wc/featured.py`、`scripts/tennis_night_card.py` + launchd `.night`（21:00／23:00）、
  09:00 card 改補充、取消舊 card／早報／每朝健康心跳推送、統一 ROI 板 tennis 行改精選、前向夠數提示、
  dashboard 精選主位＋其餘紙上注收起。新 code 寫成重建後結構會保留嘅樣（`featured.py` 唔依賴舊 report）。
- 原則：跟 `AGENTS.md`「改模型嘅規矩」同 `docs/model-evaluation-contract.md`；統一研究計劃
  （`tennis-research-execution-plan-20261028.md`）嘅 15 個 REJECT_DEV 唔重開。

---

## A. 已量到嘅事實（2026-11-05，live DB 唯讀）

### A1. 真實成績（只計賽前可核實，`is_point_in_time=1`）

| 範圍 | 注／場 | ROI | 95% CI |
|---|---:|---:|---|
| 全部 value prop 注（08-11 起） | 1,357 注 | −10.7% | [−15.7, −5.7] |
| 回填批（時間未知，05–08 月） | 1,495 注 | +11.2% | 唔算數 |
| Match-winner 參考單 | 273 注 | −13.8% | [−27.3, −0.8] |
| 正式推薦子集（10-28 起，Telegram「+2.2%」） | 188 注／**77 場** | +2.2% | 按場 [−16.1, +21.1] |

- 每個 family 都係負或者 CI 跨零。dashboard 見到「ROI 唔差」係回填批撐起。
- 模型自報 edge 唔排得到結果（edge 20%+ 一樣 −10.1%）。
- 模型 Brier 0.2098 輸市場 0.1902。
- 逐月改善：08 −21.6% → 09 −12.2% → 10 −6.7% → 11 −2.4%。
- 實盤（`prop_live_bets`）0 注。

### A2. 同場疊注（Kelvin 觀察到「一個人 3–4 注」）

- 10-28 起一場最多 10 注、同一球員最多 8 注（讓 1.5／2.5／3.5 局同時買）。
- 264 場多注賽事：每場 edge 最高嗰注減同場其餘平均 **+15.1pp [+4.2, +25.9]**（歷史探索，要前向驗）。
- 一場一注（edge 最高）全期 636 注 −6.5% [−14.8, +1.5]；逐月 08 −20.9% → 09 −10.2% → 10 −2.7% → 11 +15.5%（31 注）。
- 每日揀頭 10 注（按 edge／EV／機率）冇改善；按機率（「最有信心」）最差 −16.4%。

### A3. 落注時間

- 而家 card 09:00 悉尼出；精選注開賽中位數 4.7 個鐘後，一成 1 個鐘內開。
- 開賽集中 09:00–18:00 悉尼（美洲朝早、亞洲下晝）；18:00 後歐洲場好少入 card。
- 88% 注由出 card 到開賽賠率冇郁；收市／card 平均 0.998 → 早落冇損失。
- 18:00 嗰輪抓明日盤：排程註解寫 listing 未開。
- **2026-11-05 22:36 單次試抓**：明日 36 場已列出，部分已有讓局／總局數／讓盤／贏一盤（一場最多 40 盤），部分仲淨係獨贏。→ 夜晚落注有機會。

### A4. 發現嘅問題

1. **card 已經三星期冇出過正式推薦（已確認）**：10-28 至 11-06 每日都係「⚠️ 資料未就緒」；
   10-14 至 10-27 大部分係「❌ 今日無清晰好注」。封鎖理由係**累計歷史**數字（119 場 disputed、
   08-27 起 23% props 冇賽前時間），唔係今日 slate，所以永遠過唔到。
   Kelvin 實際睇緊嘅係 dashboard 全部紙上 value 注。
2. `clv_tracker` 同 `prop_tracker` 同一注結算唔同：8 月 55 注球員總局數判錯，冇重新結算。兩本帳。
3. `combo_tracker` 08-16 後冇新行（排程冇叫 `sync-combo-tracker`）；7 月試驗組合 −92.5%。
4. `recommendation_gate` 每日對 8 個 family 重複測，正 ROI + P(蝕)≤10% 就自動開正式注 → 遲早靠運氣過閘。

### A5. Codex 交接狀態

- 所有 tennis 分支已 push，worktree 冇未保存改動。
- 今日四條：三條已入 main；`codex-tennis-espn-bo5-20261105` 已被 main `7b840d11` 取代。
- `codex-tennis-book-tour-ingest-20261104`：Central 已拒絕。
- 未合併研究：`codex-tennis-source-owner-guard-20261104`（22 commit，身份／Elo generation）、
  `codex-tennis-identity-clock-20261102`、`codex-tennis-point-input-delivery-20261101`、
  `codex-tennis-unified-research-20261028`（15 REJECT 證據）。只作參考。

---

## B. 已拍板嘅策略（Kelvin 2026-11-05）

1. 前向測試取代自動閘：閘只可以「停」，唔可以自動開正式注。
2. 停組合注（card、Telegram、dashboard、tracking 全部拎走）。
3. 暫停靠技術統計結算嘅 family：`player_aces`、`player_double_faults`、`match_total_aces`，同 `player_exact_set_score`。
   保留靠比分結算嘅 6 個：讓局、首盤勝方、贏一盤、首盤讓局、讓盤、總局數。
4. 前向測試未過，唔落真錢。之後真係落注，用 `record-bet`（重建後喺 `tools/`）記入帳本，dashboard 實盤同紙上分開顯示。
5. 加「精選」：最多 10 注，可以係 0。
6. **21:00 出主 card，21:00–00:00 落注（似 NBA）**；23:00 同 09:00 只推「補充精選」做後備。Kelvin 2026-11-05 決定即刻轉，唔等試抓結果。
7. Match-winner 參考單（273 注 −13.8%）同 market-leg 參考：唔再喺 card／Telegram 出；只喺研究記錄保留。

---

## C. 精選嘅定義（預先登記，鎖定之後唔准睇結果再改）

一注要入精選，全部條件都要過：

1. `is_value=1`，而且過 `strategy.meets_formal_profile`（同正式推薦同一個判斷）。
2. family 屬 B3 嘅 6 個比分結算 family。
3. 賽事唔係 `DISPUTED`／mock；定價時間早過開賽（point-in-time）。
4. **一場一注**：同場揀 edge 最高；打和揀 EV 高；再打和揀賠率高。
5. **每日最多 10 注**：按 edge 由高到低；唔夠 10 注就照出，0 注就寫「今日無精選」。
6. 平注 1u。

凍結規則：

- 精選喺**出 card 嗰刻寫低**（新表 `featured_picks`：prop_id、match_id、card_run、rank、odds、edge、featured_at），之後唔改。
- 同日之後再 refresh：只可以**加**未入選、未開賽嘅場次（仍然受每日 10 注上限），唔可以剔走已出嘅注。
- 結算直接讀 `prop_tracker` 結果，唔另計一份帳。

**「要賺錢」嘅誠實講法**：精選只係減少損失（A2）。要賺錢要靠 F 部分嘅研究（更好價錢、更準模型）。
精選嘅任何再收窄（例如加 edge 門檻）都要另外預先登記，唔可以用 A 嘅歷史數據揀。

---

## D. 前向測試（預先登記）

| Arm | 定義 | 起點 | 判決點 |
|---|---|---|---|
| A 正式全部 | 現行正式推薦（formal profile） | 2026-10-28（凍結定價證據開始） | 250 場 |
| B 精選 | C 部分 | 上線日起；10-28 之後可以重播，但只係描述，唔計入判決 | 250 場（≈ 250 注） |

- 指標：ROI，**按場 cluster bootstrap** 4,000 次，seed 20260826，95% CI。
- 判決：CI 下限 > 0 → `ELIGIBLE_FOR_RELEASE_REVIEW`（Kelvin 決定落唔落真錢）；CI 上限 < 0 → `REJECT`；
  其他 → 繼續到 600 場再判一次，之後唔再延長。
- 功效：每注 SD ≈ 1.0；250 注 CI 約 ±12.8%，只捉到 +13% 以上；600 注約 ±8%。照實寫入記錄。
- 夠數**第一次**就推 Telegram（跟 AGENTS.md forward 規則）：新增 tennis forward tracker，
  仿 AU／HKJC `FORWARD_TESTS`；`AGENTS.md` 加 tennis 一行。
- 永遠唔會自動改模型或者自動開真錢。

---

## E. 先後次序：點解「先做細嘢 → 再全面重建 → 再做其餘」

重建係呢份計劃嘅**主幹**，唔係附帶一步。次序咁定：

| 階段 | 內容 | 點解排呢度 |
|---|---|---|
| 一 | 21:00 card + 精選 + 新 Telegram | Kelvin 而家日日收無用訊息、09:00 落注好難；前向測試要儘早開始計數 |
| 二 | （同一）寫成**新結構嘅第一批 module** | 重建時直接保留，唔使做兩次 |
| 三 | **全面重建**（主體） | card 封鎖、兩本帳、組合、自動閘全部住喺舊 code（`daily_report.py` 5,208 行、`ledger.py` 2,863 行）。喺舊 code 修完再重建 = 做兩次，所以呢啲修正直接喺重建入面做 |
| 四 | （已併入一） | Kelvin 決定即刻轉 21:00 |
| 五 | 接手 Codex 數據線 | 喺乾淨嘅新底上做，唔會越修越亂 |
| 六 | 盈利研究 | 要先有乾淨數據同一本帳先量得準 |

---

## F. 執行步驟（每步都要 `./檢查.sh` 同 `./保存.sh`）

### 階段一：21:00 card + 精選 + 新 Telegram（1–2 日，第一個交付）

**排程（悉尼時間）**

| 時間 | 做咩 | Telegram |
|---|---|---|
| 18:00 | 結算、覆盤昨日、歸檔（不變） | 只推每日成績；**取消「早報」** |
| **21:00** | 抓**聽日**全部賽事 + props → 定價 → 揀精選 → 凍結 | **主 card：今日精選 N／10** |
| 23:00 | 再抓一次，只為 21:00 未開盤嘅賽事揀精選 | 有新精選先推「補充精選」 |
| 09:00 | 後備：同上，捉前一晚未開盤嘅 | 有新精選先推「補充精選」 |

- 精選凍結：一注一出就唔改；補充輪只可以加、唔可以減，全日（三輪合計）最多 10 注，唔夠就照出。
- 前向測試以精選**第一次發出嗰陣嘅價**計。
- 21:00 card 包埋 00:00–09:00 開嘅凌晨場（而家 09:00 card 完全捉唔到）。

**監察（取代之前嘅試抓判決）**

- 每星期報告：精選幾多成喺 21:00 出、幾多靠 23:00／09:00 補充；同一注 21:00 價同 09:00 價差幾多；
  有冇精選喺補充之前已經開咗賽。推 Telegram。
- 如果 21:00 長期出唔夠（例如少過一半精選），報返 Kelvin 再決定改 22:00 或其他時間。

**同步做**：精選 module、`featured_picks` 表、新 Telegram 格式、dashboard、登記前向測試（即原階段二內容，見下）。

### 階段二：精選 + 新 Telegram 細節（同階段一一齊交付）

1. 新 module `tennis_wc/featured.py`：純函數揀精選（C 部分），單元測試覆蓋一場一注、上限 10、0 注、打和、只加唔減。
2. 新表 `featured_picks`：出 card 嗰刻寫低，之後唔改。
3. Telegram 換成 H 部分嘅格式：精選訊息、補充精選、每日成績（精選前向進度）。**唔再推「資料未就緒」**；
   個別場次資料有問題就唔入精選，歷史累計數字唔封鎖。
4. dashboard：精選做主角；非精選紙上注喺主頁、預設收起。
   **ROI 只計賽前可核實嘅注**；回填批（`is_point_in_time` 空）另列「歷史參考，唔計成績」，唔再撐高總 ROI。
5. 登記前向測試（D 部分）：`docs/experiments/` 記錄 + tennis forward tracker（夠數推 Telegram）+ `AGENTS.md` 加 tennis 一行。

### 階段三：全面重建（主體，約 1–2 星期）

**目標**：用最簡單、最清楚嘅 code 重寫**成個** Tennis Wong Choi；同一概念只有一個真源；剷晒死 code；舊 bug 喺重建入面修好。

**範圍 = 全部，唔係部分**（Kelvin 2026-11-05 確認）：

| 部分 | 而家 | 重建後 |
|---|---|---|
| 抓數（Sportsbet、ESPN、TennisExplorer、排名）同身份配對 | `providers/`、`ingestion/`、`identity/` | `sources/` 重寫 |
| 數據庫、帳本 | `database/`、`betting/ledger.py` 三本帳 | `store/` 一本帳 |
| 特徵、Elo、模型 | `features/`、`modelling/`、`history/`、`props/*_model.py` | `model/` |
| 定價、選注 | `props/`、`betting/` | `pricing/`、`select/` |
| card、Telegram、dashboard export | `reports/`、`scripts/tennis_daily_schedule.py` 嗰部分、dashboard `tennis_tracking.py` | `publish/` |
| 結算 | `props/settlement.py`、`ledger.py` 一部分 | `settle/` |
| 排程同入口 | `cli.py` 47 命令、`tennis_daily_schedule.py` 1,401 行、recovery、preclose、`daily.sh` | `run.py` + launchd templates |
| 測試 | 103 檔 | 按新結構重寫 |
| 研究腳本 | `scripts/` 39 檔 | 有記錄引用就搬去 `docs/experiments/patches/`，其餘刪 |

Codex 近排加嘅數據防線（來源歸屬、event ID 驗證、賽前階段防線、排名日期等）係**行為**，唔係 code：
重寫時每條都要有測試保住，唔可以因為重寫而靜靜冇咗。

**現況盤點（2026-11-05 掃描）**

| 項目 | 數字 |
|---|---|
| 總行數 | ~65,000（src 36,565、scripts 39 檔、tests 103 檔） |
| 最大嘅檔 | `reports/daily_report.py` 5,208、`betting/ledger.py` 2,863、`props/daily.py` 1,692、`cli.py` 1,433、`props/settlement.py` 1,157 |
| CLI 命令 | 47 個，排程實際只用 7 個（init-db、run-daily、review-date、weekly-review、build-lowtier-corpus、config-check、network-check） |
| 冇人 import 嘅 module | 24 個，1,485 行（`agents/` 殘骸、`research_kernel/`、`betting/devig.py`、`modelling/combiner_backtest.py`、`probability_calibration.py`、betfair／odds_api／sportradar／statsperform 空殼 provider、`features/fatigue|form|injury` 空檔等） |
| 帳本 | 三本：`prop_tracker`、`clv_tracker`、`combo_tracker`（+ 空嘅 `bet_ledger`、`prop_tracker_pre_rebuild`） |

**目標結構**（每層一個責任，上層只讀下層；舊目錄全部唔保留）

```
tennis_wc/
  sources/    Sportsbet、ESPN、TennisExplorer、排名、身份配對（重寫；Codex 防線變測試）
  store/      schema、migration、一本帳（ledger：每個推薦、精選旗、結算、CLV）
  model/      Elo、發球／接發、單一比賽 kernel、市場去水
  pricing/    每個 family 由 model 出機率、edge、EV
  select/     value 判斷、formal profile、精選
  publish/    card、Telegram、dashboard export
  settle/     賽果 → 帳本
  run.py      排程入口：card、settle、probe、review
```

目標 src 大約 1 萬到 1.2 萬行。（估計，做完先知。）

**一定要修嘅 bug（重建入面做，每個獨立 commit、前後對比）**

1. card 用累計歷史數字封鎖（A4-1）→ 只判今日 slate。
2. 兩本帳結算唔一致（A4-2）→ 一本帳；8 月錯判嘅總局數由賽果重算，舊值留 audit。
3. 組合冇記錄（A4-3）→ 組合 code 剷走。
4. 自動閘重複測試（A4-4）→ 閘只可以停。
5. 同場疊注 → 精選一場一注（紙上 value 注照記，用嚟做研究）。
6. 重建途中再搵到嘅 bug：照同一做法逐個記錄。

**剷走清單**

- 24 個冇人 import 嘅 module。
- 40 個排程冇用嘅 CLI 命令：逐個睇；真係要人手用嘅（例如 `record-bet` 記實盤、`settle-backlog`）搬去細嘅 `tools/`，其餘刪。
- `scripts/` 一次性研究腳本：有實驗記錄引用嘅搬去 `docs/experiments/patches/`，其餘刪。
- 組合、4 個暫停 family 嘅推薦路、回填期相容 code、`bet_ledger`／`prop_tracker_pre_rebuild` 空表。
- 測試：刪咗嘅 code 嘅測試一齊刪；新結構按行為重寫。

**方法（同 NBA EXP-20261103-15 一樣）**

1. **先凍結 baseline**：用舊引擎對固定一批過去日子（例如 10-28 至 11-05 全部賽事）輸出每個 prop 嘅機率、value 判斷、精選；連 commit hash 存檔。
   DB 有 2GB：凍結複本一律放外置碟 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-rebuild-20261105/`（先確認有掛載、`df` ≥10GB），唔放 Mac 內置碟。
2. 逐層寫新 code。
3. **replay 對比**（兩層都要過）：
   - 抓數層：用已存檔嘅原始回應（raw responses）重新解析，新 `sources/` 出嘅賽事、球員、盤口、賠率要同舊版一樣；
   - 模型層：同一批輸入，新引擎每個機率差 ≤1e-9、value 判斷同精選完全一樣。
   唔一樣嘅只可以係上面「一定要修嘅 bug」，逐個列明。
4. 切換排程，舊 code 喺同一個 release 刪走。
5. 模型數學（`tennis-v1`）**唔郁**；15 個 REJECT_DEV 唔重開。
6. 統一 kernel（研究計劃 C08／C09，令所有 props 互相一致）會改輸出 → 重建完之後當獨立候選，過 `model-regression-gate` 先用。

### 階段四：（已併入階段一）

- 原本等試抓結果先轉 21:00；Kelvin 決定即刻轉，所以呢步已經喺階段一做。重建時喺新結構照搬。

### 階段五：接手 Codex 數據線

- 按研究計劃「下一步」：來源身份、as-of Elo generation、缺特徵來源。
- 119 場 disputed fixture 結算被扣住：會影響 ROI 分母，要逐場解決或者明確排除。
- 研究參考：外部項目比較筆記 `docs/plans/tennis-external-project-review-notes-20261028.md`、來源清單 `docs/plans/tennis-external-project-sources-20261028.json`、15 個 REJECT 證據喺 `codex-tennis-unified-research-20261028`。
- 先讀 `codex-tennis-source-owner-guard-20261104` 嘅記錄，再決定接邊幾段。

### 階段六：令精選真係賺錢嘅研究（每項都要預先登記）

1. **更好價錢**：Sportsbet 以外有冇其他莊家／exchange 開同類 props；同一注賠率高 3% = ROI 加 3 個百分點，唔使模型變準。
2. **模型準過市場**：等階段五數據修好之後再試；Brier 要先贏市場。
3. 精選再收窄（例如 edge 門檻、賠率範圍）：只可以做新 arm，前向驗。

---

## 時間表（估計）

| 時間 | 事項 |
|---|---|
| 11-06 – 11-07 | 階段一／二：21:00 card、精選、新 Telegram、登記前向 |
| 11-08 – 約 11-25 | 階段三：全面重建（成個系統，包括抓數層） |
| 約 11-14 | 第一份 21:00 覆蓋率監察報告 |
| 11 月尾起 | 階段五、六 |
| 約 12 月中 | 精選 250 場第一次判決 |


## G. Kelvin 決定（2026-11-05 確認）

1. 前向判決：250 場判一次，唔清楚就延到 600 場，之後唔再延。✅
2. 精選打和規則 edge → EV → 賠率。✅
3. ~~夜晚 card 門檻 80%／90%~~ → **改為即刻轉 21:00 主 card，23:00、09:00 做補充後備**（Kelvin 2026-11-05：09:00 好難落注）。補充精選一有就推 Telegram + 入 dashboard。
4. 非精選紙上注：放 dashboard 主頁，**預設收起**，撳開先見。✅

## H. Telegram 訊息整頓（Kelvin 指定優先）

而家每日收到：「資料未就緒，唔可以判斷」+ 一個每日 ROI 訊息，兩樣都冇用。改成：

1. **精選訊息**（每晚 21:00 一個）：聽日精選 N／10 注，逐注列選擇、賠率、開賽時間；0 注就一句「今日無精選」，唔再出「資料未就緒」。
   資料問題只影響個別場次（嗰幾場唔入精選），歷史累計數字唔再封鎖成張 card。
2. **補充精選**（23:00／09:00，有先推）：之後先開盤而又入選嘅注。
3. **每日成績**：只講精選（昨日、前向進度 x／250 場、ROI、CI）；全部紙上注一行帶過。
4. 真係抓唔到盤（Sportsbet 斷線等）先推一個簡短警告。


## I. 對話要求對照表（2026-11-05 逐條核對）

| Kelvin 喺對話提過 | 喺計劃邊度 |
|---|---|
| 用最簡單、最乾淨嘅 code 全面重建，統一、剷 bug 同死 code、需要就改結構 | F 階段三（範圍＝全部、盤點、目標結構、bug 清單、剷走清單、兩層 replay） |
| 係成個重建，唔係部分 | F 階段三「範圍 = 全部」表 |
| 重建排前定排後 | E（先細嘢 → 重建 → 其餘，附理由） |
| 盈利策略：放棄某啲注類／props | A1、B2–B3、B7 |
| 兩樣一齊做定先做重建 | E |
| 參考統一研究計劃同 GitHub 外部項目 | F 階段三第 5–6 點、階段五研究參考 |
| 接手 Codex | A5、F 階段五 |
| Dashboard ROI 睇落唔錯 | A1（回填批）、F 階段二第 4 點 |
| 同一球員 3–4 注唔聰明 | A2、C 第 4 點 |
| 精選最多 10 注、可以 0、最好賺錢 | C、D、F 階段六 |
| 揀最高信心嘅 10 注會唔會好啲 | A2（量咗：按信心揀最差） |
| 精選做唔做到 profitable | A2、C 最後一段、F 階段六 |
| 似 NBA 咁 21:00–00:00 落注 | B6、F 階段一（即刻轉，09:00 做後備） |
| 做唔到就話我知最佳時間 | F 階段一「監察」 |
| 未有盤嘅：有盤再推＋入 dashboard | G3、F 階段一（23:00／09:00 補充） |
| 非精選：dashboard 主頁、預設收起 | G4、F 階段二第 4 點 |
| 「資料未就緒」＋每日 ROI 訊息無用，要整頓 Telegram | A4-1、H、F 階段二第 3 點 |
| 前向判決點、打和規則、夜晚門檻 | G1–G3 |
| 唔落真錢直到證實 | B4 |
