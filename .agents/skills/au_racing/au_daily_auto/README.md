# AU Wong Choi — 每日自動排程

四個 launchd job，本機時區 `Australia/Sydney`：

| Job | 時間 | 做乜 |
|---|---|---|
| `com.antigravity.au-wong-choi.evening` | **每日 22:00** | 覆盤 + 歸檔 dashboard 上已跑完嘅場次 → 分析下一個澳洲賽日 → 驗證 → 發佈 Cloudflare |
| `com.antigravity.au-wong-choi.morning` | **每日 10:00** | 覆核 dashboard 上每場嘅場地狀況／退出馬／後備入替／檔位／騎師 → 有實質變動先重評分 → 驗證 → 發佈 |
| `com.antigravity.au-wong-choi.healthcheck` | **02:30／09:15／11:00** | 獨立核實今日分析同 live dashboard；只對已知發佈故障自動補救 |
| `com.antigravity.au-wong-choi.bot` | **每 2 分鐘** | 輪詢已授權 Telegram 指令（`/status`、`/health`、`/retry` 等） |

launchd 用**本機 wall clock**，而本機時區就係 `Australia/Sydney`，所以 22:00 / 10:00
直接等於悉尼時間，DST 亦自動跟。runner 開工會核對，時區唔對就喺 run log 大聲警告，
installer 更會直接拒絕安裝。

## 資料位置：AU 分析樹住本機硬碟（2026-08-05 搬遷）

```
source of truth  ~/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing
Drive 鏡像       …/CloudStorage/GoogleDrive-…/Wong Choi Horse Race Analysis/AU_Racing
```

**點解搬。** 兩個 job 裝好之後，由 launchd 觸發會即刻死（實測
`launchctl kickstart` 2026-08-05 01:30）：

```
❌ [preflight] 讀唔到 AU_Racing（PermissionError: [Errno 1] Operation not permitted:
   …/CloudStorage/GoogleDrive-…/Wong Choi Horse Race Analysis/AU_Racing）
```

macOS TCC：由 launchd 起嘅 process 同 Terminal 係唔同 context。**手動由 Terminal 跑
完全正常**，所以純粹係排程觸發嘅權限問題。賜 `/bin/zsh` 完全取用磁碟權限係得嘅，但要
人手做、而且將來每個新 launchd 入口都要再做一次。所以行 tennis-wong-choi 2026-07-14
條路：搬離 Drive，令排程根本唔需要讀 CloudStorage。

**權限係一半一半，唔係全冇。** 2026-08-05 喺 launchd 底下對住 Drive AU 路徑連續探測
三次，三次結果一致：

| 操作 | launchd |
|---|---|
| `iterdir()` | ❌ `PermissionError` errno 1 |
| 讀檔內容 | ❌ `PermissionError` errno 1 |
| `stat()` | ✅ |
| 建立新檔＋刪除一般檔 | ✅ |
| 覆寫／刪除既有 dataless placeholder | ❌（FileProvider 可拒絕） |

兩個直接後果：

1. **`.is_dir()` / `.exists()` 唔可以當可讀性探測** —— 佢哋係 stat，喺一條同一個
   process 列都列唔到、讀都讀唔到嘅路徑上面照樣返 True。要試就試真嘅操作。
   （`wongchoi_paths.check_data_root()` 同 `step_mirror_reports` 都跟返呢點。）
2. **鏡像返 Drive 喺 launchd 底下係做得嘅** —— 一般檔用 sibling temp + atomic replace；
   如果 canonical 名已經係 FileProvider 鎖死嘅 dataless placeholder，就寫入固定
   `.latest.csv` sibling。所有 AU historical-results consumer 會揀兩者之中較新且非空嗰份，
   唔會再誤讀 0-byte placeholder。

**點接線。** `run_au_daily_schedule.sh` 明確 export 兩個變數（唔靠 repo 裏面嗰個
gitignore 嘅 dotfile —— worktree／新 clone 都唔會有）：

| 變數 | 作用 |
|---|---|
| `WONGCHOI_AU_DATA_ROOT` | 本機 source of truth，引擎讀寫呢邊 |
| `WONGCHOI_AU_MIRROR_ROOT` | 跑完之後鏡像返 Drive，**best-effort** |

兩個都可以用 repo root 嘅 dotfile 代替（`.wongchoi_au_data_root` /
`.wongchoi_au_mirror_root`，兩個都 gitignore），咁直接跑 `au_daily_schedule.py` 都跟。

`wongchoi_paths.AU_RACING` 認得呢個覆寫，所以成條 pipeline（`au_archive_calibrator`、
所有 backtest、`Horse_Racing_Dashboard/generate_static.py`）一齊跟。只搬 AU，HK / NBA /
tennis 照留 Drive：佢哋喺 Drive 上面絕大部分係未下載嘅 placeholder，搬過嚟等於要逐個
檔即時下載幾萬次，而且冇一個係 launchd 底下跑。

鏡像 step 仍然係 best-effort：寫唔入就 warn 一句照過（`[mirror] skipped-unwritable`），
唔會拖垮已經做完嘅分析同發佈。實測 2026-08-05 02:13 由 launchd 跑出嚟係
`[mirror] ok {"copied":0,"failed":0}`（嗰次 run 冇場次更新，所以冇嘢要抄）。
如用咗 FileProvider fallback，run log `mirror.fallbacks[]` 會記錄實際 `.latest.csv` 路徑。

驗證：

```bash
launchctl kickstart gui/$(id -u)/com.antigravity.au-wong-choi.morning
tail -5 .agents/skills/au_racing/au_daily_auto/logs/launchd.morning.stdout.log
```

見到 `[preflight] ok {"au_meeting_folders":…,"au_root":"/Users/imac/WongChoiData/…"}`
就係通咗。`au_root` 仲係 CloudStorage 就代表覆寫冇生效。

⚠️ **preflight fail 就係整個 run fail，唔會退而發佈。** 呢個係故意嘅：Drive 讀唔到
嗰陣 `build_test_dashboard.py` 個 archive filter 同 metadata overlay 會靜靜咁失效，
發佈出去就係一份「乜都冇排除」嘅 dashboard（2026-08-04 12:08 實際發生過）。
唔發佈好過發錯。

## 安裝 / 卸載 / 狀態

```bash
.agents/skills/au_racing/au_daily_auto/install_macos_launchd.sh
.agents/skills/au_racing/au_daily_auto/install_macos_launchd.sh --status
.agents/skills/au_racing/au_daily_auto/install_macos_launchd.sh --uninstall
```

## 手動觸發

```bash
# 完整 22:00 流程
./.agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh evening

# 完整 10:00 流程
./.agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh morning
```

**用 wrapper，唔好直接 `python3 au_daily_schedule.py`** —— wrapper 砌返 launchd 冇嘅
`PATH`（`npx wrangler` 要 node，冇就「分析成功、發佈靜靜失敗」），又 export 兩個 AU
root。直接跑 `.py` 都得（`.wongchoi_au_data_root` / `.wongchoi_au_mirror_root` 會頂上），
但就冇 node PATH 嗰層保險。

常用旗標（全部可以疊）：

| 旗標 | 作用 |
|---|---|
| `--today 2026-08-04` | 覆寫「今日」。重跑一個過去嘅晚更就用呢個 |
| `--skip-review` | 唔覆盤／歸檔 |
| `--skip-analysis` | 唔分析下一個賽日 |
| `--no-archive` | 覆盤但唔搬 folder（安全排練） |
| `--skip-deploy` | build + 驗證但唔發佈 |
| `--skip-refresh` | morning：唔出網覆核，直接由本機現有分析重建 + 發佈（本機改過但發佈唔上去嗰陣用，唔會重抽任何一版）|
| `--max-meetings 2` | 每晚最多分析幾個場次（0 = 全部）；被略過嘅會寫落 log |
| `--rounds 8` | 個站拒絕之後最多再等幾輪（預設 8） |
| `--round-gap 900` | 每輪之間等幾秒（預設 900 = 15 分鐘） |
| `--json` | 完場印出成個 run log |

### 為咩要 rounds

⚠️ **改行真瀏覽器之後，rounds 應該極少會觸發** —— 呢個機制係 curl_cffi 年代嘅產物：
嗰陣一個冷卻窗大約**只夠抽一個場次**，之後就 403。改行 headed 真 Chrome 之後實測
連續幾十版零拒絕，所以 rounds 而家係安全網而唔係常態路徑。留住佢，因為個站幾時
變都唔知，而由 22:00 到早更 10:00 有十二個鐘，等一陣再續係免費嘅。

每輪之間 circuit breaker 會 reset，已經抽好嘅場次全部 cache 命中，所以續跑唔會重打
任何一版。連續三輪**零增長**就當真封鎖收工（要數「真係多咗場次」，唔係「冇拋
exception」—— 一個零增長嘅半份場次會令計數永遠歸零）。

⚠️ **每一輪嘅次序會輪替（`rotate_for_fairness`）。** 2026-09-01 晚更：Murray Bridge
第 7 場每一輪都喺 90 秒 timeout 停低，於是四輪冷卻嘅第一個請求全部餵咗俾佢，
Sandown 同 Warwick Farm 由頭到尾**一個請求都冇出過**，兩個馬場整晚 pending。冷卻窗
大約只夠抽一個場次，所以「邊個排頭位」實際上就係「邊個今晚抽得成」—— 次序唔變嘅
重試會令一個卡住嘅場次永遠餓死排喺佢後面嘅所有場次。

### 「攞唔到」同「個站拒絕」係兩件事

`sb_browser_fetch` 只有喺**個站真係唔畀入**嗰陣先會 trip circuit breaker：

| 症狀 | 判斷 | 做法 |
| --- | --- | --- |
| 非 200 status | 個站拒絕 | 即刻收手，唔重試 |
| 版細過 `MIN_BYTES` | 攔截頁 | 即刻收手，唔重試 |
| `net::ERR_*` | 本機出唔到門 | 退避重試三次（20/40/60 秒） |
| `TargetClosedError` 之類 | Chrome 死咗 | 重開再試兩次 |
| 淨係 `Timeout`（冇 `net::`、瀏覽器又冇死）| **呢一版** hang 咗 | 退避重試兩次（15/30 秒）；仲係唔得就當**單版失敗**，跳過呢一場繼續下一場，circuit breaker **唔跳**。連續三版都咁先當真係唔通收手 |

⚠️ 呢個表存在嘅原因係同一類誤判出過三次，每次都係**本機／單頁故障扮成遠端封鎖**，
而兩者嘅正確應對相反（真封鎖要收手，其餘要重試）：08-08 `TargetClosedError`、
08-11 `ERR_NETWORK_CHANGED`、09-01 `Page.goto: Timeout 90000ms exceeded`。09-01 嗰次
事後即刻手抽同一版：9.6 秒 200。個站由頭到尾冇回過一個非 200。

節奏由 `WC_AU_FETCH_DELAY`（秒）控制，預設 25，**硬下限 12**（低過就會被拉返上去）。

## 睇狀態同 log

```bash
# 排程狀態（含 last exit code）
.agents/skills/au_racing/au_daily_auto/install_macos_launchd.sh --status

# 人類可讀 log（跨所有 run）
tail -f .agents/skills/au_racing/au_daily_auto/logs/au_daily_schedule.log

# 最近一次 run 嘅結構化 log
ls -t .agents/skills/au_racing/au_daily_auto/logs/run-*.json | head -1 | xargs cat

# 一眼睇每次 run 嘅結果
for f in .agents/skills/au_racing/au_daily_auto/logs/run-*.json; do \
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); \
  print(f\"{d['started_at']}  {d['mode']:8} {d['status']:8} \
archived={len(d['races_archived'])} added={len(d['races_added'])} \
updated={len(d['races_updated'])} errors={len(d['errors'])}\")" "$f"; done
```

Exit code：`0` 完全成功 · `75` 部分／暫時性失敗（下一次排程會續） · `1` 硬失敗。

### 自動復原界線

獨立 healthcheck 會先比較官方今日場次、live dashboard 同本機評分檔，並逐個本機 meeting
檢查預期場數、Racecard／Formguide／Facts／Logic／Analysis／Scoring 非空、going refresh、
J/T coverage（預設至少 80%），以及 11:00 後 morning odds 是否齊全；亦會檢查最近一次
`ingest-results` 同 `mirror` step。場次齊但資料 gate 唔過會報 `degraded`，唔再當綠燈。
確認今日有賽事但本機完全冇分析時，會自動開一次受共用鎖保護嘅 morning recovery；
同一日最多一次，完成後仍然要過原本 snapshot 驗證先可以發佈。純發佈故障繼續用
cache-only 重建補發。未知錯誤、模型／資料矛盾同重複失敗只會 Telegram 報警，唔會
自行改 code 或者無限重試。

## Run log 內容

每次 run 一個 JSON（步驟完成即刻寫落 disk，中途炸都仲有記錄）：

`task_name` · `mode` · `timezone` · `review_day` · `started_at` / `completed_at` /
`duration_seconds` · `status` · `steps[]` · `meetings_processed[]`（逐個場次一個狀態）·
`races_archived[]` · `races_added[]` · `races_updated[]` · `scratchings_detected[]` ·
`track_changes_detected[]` · `analysis_changes[]` · `dashboard_validation` ·
`cloudflare_deployment`（含 `deployment_url` / `commit` / `verified`）· `errors[]` ·
`warnings[]` · `retries[]`

場次狀態字典：

| 狀態 | 意思 |
|---|---|
| `archived` | 覆盤完，已搬入 `Archive/` |
| `already_archived` | 已經喺 `Archive/`，冇做嘢（重跑安全） |
| `pending_results` | 賽果攞唔到 —— **唔會歸檔**（腰斷／改期／成績未出） |
| `partial_results` | 賽果唔齊 —— **唔會歸檔**，log 列出缺邊幾場 |
| `archive_blocked_corpus` | 呢個賽日已入歷史賽果 CSV，搬走會由 backtest 語料庫消失 |
| `archive_conflict` | `Archive/` 已經有同名 folder，唔覆蓋 |
| `analysed` | 抽取 + 評分完成，已加入 dashboard |
| `analysed_partial` | 只抽到部分場次（撞到拒絕，或者個別版 hang 咗被跳過）—— 已評分，但**仍然留喺待辦**，下一輪／下一次排程續抽 |
| `skipped_already_analysed` | 場數已到齊而且評齊（重跑安全，零請求） |
| `skipped_already_archived` | folder 已經喺 `Archive/` |
| `pending_extraction` | 一場都抽唔到（網站拒絕）—— 下一輪／下次排程再試 |
| `rescored` | 早更發現實質變動，已重新評分（`rebuilt: true` = 連出賽名單一齊重建）|
| `unchanged` | 早更覆核冇實質變動，**故意唔改** |
| `refresh_deferred` | 早更攞唔到最新頁面 —— 分析保持原狀（唔會用半份資料改分） |
| `failed` | 非預期錯誤，log 有 exception |

⚠️ **退出馬唔可以只靠重評分。** 早更有兩條路，睇變動係邊一層：

| 變動 | 做法 |
|---|---|
| 退出馬／後備入替／換檔／換騎師／馬匹數（`FIELD_LEVEL_CHANGES`）| 由 cache 頁**重寫 Racecard** → Facts → Logic → 評分（`rebuild_meeting_from_cache()`，全程 cache-only 零請求）|
| 只係場地狀況變 | `au_auto_orchestrator --going` 純重評分（快好多）|

點解：退出馬係喺 `write_meeting` 寫 `status:Scratched` 嗰層剔走嘅，`au_auto_orchestrator`
由現有 `Logic.json` 重算，而 Logic 係通宵嘅 Racecard 砌出嚟 —— 一隻通宵之後才退出嘅馬
仍然喺 Logic 裡面，於是照樣入榜。2026-08-05 實測：Canterbury 7 場偵測到 24 隻退出馬
全部照樣排名，R2 #6 Blenheim Girl 退出咗仲排第二（Kelvin 睇 dashboard 發現）。修好後
6 個場次共 97 隻退出馬，dashboard 上 0 隻殘留。有回歸測試。

⚠️ **「做完」唔可以只睇 `Meeting_Summary.md` 存在。** 2026-08-05 實測：Hobart 抽到
第 1 場就俾個站拒絕，`Meeting_Summary.md` 已經寫落去，於是下一次 run 當佢做完，
餘下 8 場永遠冇人補。完成嘅定義係 **抽到嘅場數同評到嘅場數都到齊索引話有嘅數**
（`meeting_is_complete()`，有回歸測試）。

## 重用嘅現有命令

呢個 runner **只做編排**，實際工作全部交返現有腳本，所以手動同排程行同一條路：

| 步驟 | 命令 |
|---|---|
| 發現賽日 / 場地狀況 | `claw_sportsbet_form.discover_meetings()`（sportsbet.com.au NextEvents API） |
| 發現 meetingId / raceId | `claw_sportsbet_form.parse_date_index()`（`sportsbetform.com.au/{date}/`） |
| 抽取 | `claw_sportsbet_form.py --meeting-url … --races … --out-dir … --delay 25` |
| Facts + Logic + 評分 | `au_wong_choi/scripts/au_orchestrator.py <DIR> --auto --skip-cloudflare-deploy --going "…"` |
| 只重評分 | `au_wong_choi_auto/scripts/au_auto_orchestrator.py <DIR> --going "…"` |
| 賽果 | `sb_results.py --meeting <key> --meeting-dir <dir>` |
| 覆盤 | `au_reflector/scripts/au_reflector_orchestrator.py <DIR> --skip-backtest` |
| Dashboard 合併 | `Horse_Racing_Dashboard/generate_static.py --base-snapshot … --au-meeting-dir …` |
| 發佈 | `WC_DASHBOARD_BASE_SNAPSHOT=<json> Horse_Racing_Dashboard/deploy.sh` |

## ⚠️ 三個一定要知嘅陷阱

### 1. `AU_Racing` 根目錄同時係 backtest 語料庫

`au_archive_calibrator.ARCHIVE_ROOT = AU_RACING`，而且用**非遞歸** `iterdir()`。
所以「搬入 `Archive/`」= 由每個 backtest 消失。`Archive/` 唔係「完成嘅場次擺呢度」，
佢係 **dashboard 排除名單**。

所以歸檔嘅準則係「**而家掛喺 live dashboard 上**」，唔係「日期 <= 今日」。
2026-08-04 用「日期」準則實測過一次，33 個語料庫場次一鋪清袋（已還原）。
另外有第二道閘：賽日已經入 `AU_Historical_Raw_Race_Results.csv` 就拒絕搬。

dashboard 成員資格同時亦係天然嘅後帳清單 —— 錯過一晚，場次仍然掛喺 dashboard，
下一晚照樣處理。

### 2. sportsbetform 只行真瀏覽器（headed 真 Chrome）

2026-08-05 實測，同一時間、同一個 IP：

| 方式 | `/{date}/` 索引頁 | 賽事頁 |
|---|---|---|
| curl_cffi (`impersonate="chrome120"`) | 403 | 一個冷卻窗約 8 版之後 403 |
| Playwright bundled chromium, headless | 403 | — |
| Playwright **真 Chrome**, `headless=True` | **403** | — |
| Playwright **真 Chrome**, `headless=False` | **200** | 200 |

**被偵測嘅係 headless 本身**，唔係邊個 Chrome、亦唔係 IP。而真瀏覽器路徑實測
10 秒一版連續幾百版零 403，而 curl_cffi 25 秒都被封 —— 所以真瀏覽器唔止唔會被封，
實際上又快又穩。

所以現役設計係 **browser-only**：

- 所有 `sportsbetform.com.au` 存取行 `sb_browser_fetch.BrowserFetcher`
  （`channel="chrome"` + `headless=False` + persistent profile，每個 run 開一次）
- 做法：navigate 去一版**同源**索引頁 → 之後逐個 URL 喺 page 裏面 `fetch()` 攞
  raw HTML → 寫落同一個 `.sportsbet_cache`（sha1(url) 公式同 bridge 一致）
- 要 raw HTML 而唔係 `page.content()`：下游 parser 全部係食原始 markup 嘅 regex
- Python 側**一個請求都唔准出**：`run_cmd()` 對每個 subprocess 強制
  `WC_SB_CACHE_ONLY=1`，`SportsbetFormFetcher` cache miss 直接回 None。有測試釘住。
- 個人頁（`/Jockey/{id}/`、`/Trainer/{id}/`）由 `warm_people_pages()` 喺 claw 之前
  落 cache。冇呢步 `(LY:)` 全部係 `-`，jockey/trainer 覆蓋率跌到 63%/51%。

**兩個例外，都係故意嘅：**

1. `sportsbet.com.au` NextEvents API（賽日／馬場／官方場地狀況）仍然行 curl_cffi ——
   另一個 host、從來冇封過，而且由 sportsbetform 個 page 去 fetch 佢係跨域，CORS
   會擋住讀 body，技術上做唔到。
2. `sb_browser_bridge.py` 仍然留住做人手補頁用（見下）。

⚠️ **代價**：headed 要有 active GUI login session（鎖螢幕冇問題，**登出就唔得**），
而且每次 run 會彈一個 Chrome 窗（用獨立 profile，唔會撞你自己個 Chrome）。

⚠️ **界線**：用真瀏覽器係因為個站本來就係咁 serve 呢啲內容，而且我哋照守保守節奏
同撞非 200 即停。**唔會**加任何目的係擊敗 bot detection 嘅嘢（唔改
`navigator.webdriver`、唔用 `--disable-blink-features=AutomationControlled`、
唔輪換 fingerprint / UA / proxy）。

人手補一版（例如想預先暖索引頁）：

```bash
python3 .agents/skills/au_racing/sb_browser_fetch.py 2026-08-06
```

### 3. 索引頁有海外賽事

2026-08-05 嗰版 12 個場次，一半係英國／愛爾蘭／南非／加拿大
（`lingfield`、`pontefract`、`roscommon`、`kenilworth`、`brighton`、
`assiniboia_downs`）。所以 **NextEvents API 配對係硬性要求**：配唔到就唔分析，
被剔走嘅會列喺 `discover / non-au-excluded`。索引頁嘅 slug 係縮寫
（`murray_bdge`），API 出全名（`Murray Bridge`），所以配對要容錯 ——
但撞正多過一個候選就唔猜。

## 可靠性做法

- **Idempotent**：抽過又評過 → `skipped_already_analysed`；已歸檔 → `already_archived`；
  meetingId 對應表同名覆寫；build 出嚟嘅 snapshot 同 live 一樣就唔發佈
  （`deploy-skipped-no-change`）。
  ⚠️ 「一樣」嘅定義要食到**排名**。2026-08-05 早更實測：6 個場次全部重評分
  （場地 Soft 6→Soft 5、Soft 5→Good 4、多個退出馬），但場次同場號一個都冇變，
  於是舊 signature 話「冇變」，把早更成果扣咗喺本機。修法兩重：signature 加入
  逐場 `top_picks` / grade / confidence 指紋，加上「今次 run 真係改過嘢就一定發佈」。
- **唔怕資料唔齊**：冇賽果／賽果唔齊一律唔歸檔，各自記狀態。
  ⚠️ 「要唔要重抓賽果頁」睇**覆蓋率**，唔係睇「賽果檔存唔存在」。半份賽果檔
  （晚更跑嗰陣最後一場仲未跑完）會令舊寫法之後每次都跳過重抓、由同一份舊 cache
  重建同一份半份賽果 —— 場次永遠 `partial_results`、永遠唔會歸檔。有回歸測試。
- **起始頁有後備**：真 Chrome 要落一版同源頁先可以 `fetch()`，落唔到就一版都攞唔到。
  所以收兩個候選（覆盤日索引頁、今日索引頁）逐個試。`/` 根目錄唔可以做後備 ——
  CloudFront 擋 root。
- **缺人資料優先補齊**：`warm_people_pages()` 先抽從未 cache 嘅騎師／練馬師，再做 TTL
  freshness refresh；同一個 run 跨 meeting 去重，唔會重複抽同一個人。晚更對 missing
  pages 唔受每場 40 個 refresh cap 限制，確保 rural meeting 唔再長期被 metropolitan
  cached people 擠走；`WC_AU_PEOPLE_PER_MEETING`（預設 40）只限制已 cache 人物嘅更新量。
- **單場失敗唔會拖死其他場**：逐個場次 try/except，狀態逐個記。
- **retry**：live snapshot 3 次、發佈 3 次（遞增退避）、發佈後核實 poll 6 次
  （production alias 有大約一分鐘 edge cache 延遲，一次讀到舊 snapshot 唔算失敗）。
- **唔會撞車**：兩個 mode 共用一把 `flock`；撞到就靜靜退出（exit 0）。
- **網絡紀律**：預設 25 秒、下限 12 秒；撞到穩定非 200 即停唔重試。
- **驗證唔過就唔發佈**：重複場次、空場次、孤兒 races key、已歸檔仍在榜 —— 任何一項
  fail 都會 `return False` 而唔會 call `deploy.sh`。

## 測試

```bash
python3 -m pytest .agents/skills/au_racing/au_daily_auto/tests/ -q
```
