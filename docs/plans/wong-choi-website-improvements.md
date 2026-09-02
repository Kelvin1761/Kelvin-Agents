# 旺財網站改進方案（形勢推演 · 賽道 · 步速）

**用途**：收埋 2026-09-02 一連串抽取／顯示層改動嘅**收尾同未完項目**，
每一項都寫明**點驗**同**幾時算完**。
**建立**：2026-09-02。
**原則**：同 [`au-wong-choi-defect-scan.md`](au-wong-choi-defect-scan.md) 一樣 ——
唔准靠「睇落唔妥」，每一項要有偵測方法同判定門檻。

## 開工前一定要讀

1. [`AGENTS.md`](../../AGENTS.md)
2. [`docs/model-evaluation-contract.md`](../model-evaluation-contract.md)
   —— 尤其 **§7 正確性修正**（呢批改動大部分行呢條路）
3. [`docs/experiments/INDEX.md`](../experiments/INDEX.md)
   —— EXP-20260902-01 ～ -05 就係呢份方案嘅來源

---

## 一、已完成（有驗證證據）

| 項目 | 證據 | 記錄 |
|---|---|---|
| 賽道幾何改為生成（85/96 場地，兩來源交叉核對） | `test_track_profile_venue_scoping.py`；修好之前 14,727 行印住 Canterbury 嘅數、6,227 行冇數 | EXP-01 |
| 跑法收成單一 Sportsbet 來源 + 三態化 | `test_run_style_single_source.py`；golden 冇郁 | EXP-02 |
| 官方 Speedmap parser 修正（836/836 頁） | `test_odds_capture.py` 加咗「馬先」版面 fixture | EXP-03 |
| Speedmap 駁線 + 日常暖 cache | 實跑 2025-08-09 Randwick：`SpeedPos` **0 → 132 行有值**；`test_au_daily_schedule.py` 三個測試 | EXP-03 |
| 起步位 `Settled → 800m → 400m` fallback | 跑法證據覆蓋 **27% → 76%**；891 場 A/B 兩個 primary 都跨零 | EXP-04 |
| 報告 🏃 形勢推演 換成真表 | 行真 `au_auto_orchestrator.py` 產生嘅 `Race_3_Auto_Analysis.md` 有表，`validate_report_text` 過 | EXP-03 |
| Dashboard 形勢推演 圖 | `test_static_template.mjs` 四個測試；真瀏覽器 375px + 1280px 都睇過 | 本文件 |
| **賽道幾何上網站（2.3 已完成）** | payload 由 `_attach_track_geometry()` 帶；`test_generate_static.py` 六個測試 + `test_static_template.mjs` 四個；真瀏覽器兩個闊度睇過 | 本文件 |

⚠️ **Dashboard 嗰一項差啲出事**：`parseBattlefieldOverview()` 會將**每一個** markdown 表
由 notes 剷走，只認得「項目/內容」同「排名/馬號」。第一版 hook 插錯咗喺
`renderAnalysisDocumentSection`（戰場全景根本唔行嗰條路），個表會被剷走又冇人畫 ——
**比改之前更差**。而第一版用 SVG `<text>`，喺 375px 手機縮到 0.464×，字得 **5.6px**，
實測到之後改用 HTML/CSS 百分比（而家 10.6–10.9px）。
**教訓：加咗一個 renderer 之後，一定要行真 pipeline + 真瀏覽器兩個闊度睇過。**

---

## 二、未完成

### 2.1 舊報告唔會有新版形勢推演（最高優先）

**現況**：語料庫 **1,955 份** `Race_*_Auto_Analysis.md` 仍然係舊罐頭句
（「形勢推演暫時以跑法分佈…未納入步速預測」），**0 份**有新表。
新 section 只喺重新渲染之後先出現，所以網站而家睇落**完全冇變**。

**偵測**：
```bash
grep -rl "預測定位" <AU_RACING>/*/Race_*_Auto_Analysis.md | wc -l
grep -rl "形勢推演暫時以跑法分佈" <AU_RACING>/*/Race_*_Auto_Analysis.md | wc -l
```
**做法（要揀）**：
- (a) 只向前生效 —— 下個賽日自然有。最平，但舊場次永遠冇。
- (b) 重跑 `au_auto_orchestrator.py --meeting-dir` 逐個場次重渲染。
  ⚠️ 重渲染會**同時**帶入起步位 cascade（EXP-04），即係舊場次嘅分數會變。
  嗰個係 §7 正確性修正，但**改寫已發佈嘅歷史預測**要你明確批准。
**完成準則**：兩條 grep 一個 0、一個等於場次總數；或者明確決定行 (a) 並寫落記錄。

### 2.2 官方 Speedmap 歷史覆蓋

**現況**：日常抽取已經會暖 cache（`warm_speedmap_pages`），但**歷史只有已 cache 嗰批**。
836 個 cache 頁入面同語料庫對得到嘅只有 **25 場**（2026-08-05 之後）。
所以「官方」同「混合」兩欄喺大部分舊場次會係 `—`。

**偵測**：`SpeedPos:` 行入面非 `-` 嘅比例，逐月睇。
**做法**：`sb_browser_bridge.py --view=Speedmap` 補一段歷史（要真瀏覽器、headed）。
**完成準則**：2026-08-05 之後嘅場次 `SpeedPos` 覆蓋 ≥80%。

### 2.3 賽道幾何上網站 —— ✅ 已完成（2026-09-02）

**做法**：`generate_static._attach_track_geometry()` 由 `au_track_geometry.json` 查，
貼落 `meeting.track_geometry`；`renderTrackGeometry()` 喺 戰場全景 畫一條
周長／直路／方向／級別／場地。**由 payload 帶而唔係由報告文字 parse，所以
舊報告唔使重新渲染都即刻有** —— 呢個係刻意繞開 2.1 嘅做法。

**踩到嘅三個坑（寫低免得重蹈）**：
1. **cache**：`_collect_meeting()` 嘅結果會入 cache 而且 fingerprint 唔變。
   喺嗰度貼 = 已 cache 嘅場次永遠冇賽道資料。要喺**讀完 cache 之後**先貼。
2. **alias 表**：`Rosehill Gardens` / `Sandown Hillside` / `Ballarat Synthetic`
   靠引擎個 alias 表對名。dashboard **唔可以自己抄一份**，一抄就會有一日唔同步。
   一律 import 引擎個 `_load_track_geometry`，import 失敗要**出聲**
   （靜靜返 None 同「呢個場地本來就冇數據」喺畫面上一模一樣）。
3. **主題變數**：`index.css` 喺 `/* __CSS_PLACEHOLDER__ */` inline，而 dashboard
   有淺色主題。第一版 speedmap CSS 寫死深色，喺淺色主題度變灰底白字睇唔到。
   全部改用 `var(--color-surface-alt)` 呢類主題變數。

**⚠️ 唔好順手拎去評分** —— EXP-01 已測：做排名特徵三個切法全部越加越差。

### 2.4 11 個場地仲係冇幾何

Broome、Carnarvon、Caulfield Heath、Emerald、Gympie、Katherine、Mt Isa、
Narrandera、Pakenham Synthetic（只有周長）、Roma、Tuncurry。
兩個來源加人手都查唔到。**偵測**：`fetch_au_track_geometry.py` 輸出嘅
`venues_with_geometry`。**完成準則**：≥90（而家 85）。

### 2.5 混合權重 0.3 要向前重驗

`OFFICIAL_SPEEDMAP_WEIGHT = 0.3` 係喺 353 場（dev 247 / holdout 106）揀嘅。
holdout 贏 +0.063 CI [+0.023, +0.102] ✅，但語料窗係 2025-08 → 2026-08。
**完成準則**：儲夠 200 場新場次之後重跑 `sm_power.py`，w 曲線峰仍然喺 0.2–0.4。

### 2.6 HKJC 冇形勢推演

HKJC renderer **零次**提及「形勢推演」，HKJC 引擎亦冇同類 speed map。
呢個係一個真嘅產品缺口，唔係 bug。要做就係一個獨立項目
（HKJC 有官方排位表同往績走位，但同 Sportsbet 唔同來源）。

### 2.7 Facts 重建失敗 129/1,134 未查清

EXP-04 個 A/B 入面 1,134 場得 891 場可比：114 場冇賽果（正常）、
**129 場 Facts 重建失敗（原因未查清）**。跑咗十分鐘背景 job 未撞到失敗，
即係應該係零星，但**未有定論**，所以 EXP-04 嘅樣本有冇系統性偏差仍然係開放問題。
**2026-09-02 跟進**：喺同一批場次上**逐場串行重跑** `inject_fact_anchors.py`，
跑晒全部，**0 場失敗**。即係話嗰 129 場大機會係環境性（A/B 嗰陣係並發 subprocess
＋180s timeout），唔係場次本身嘅特性。⚠️ 但當時冇逐場記低成因，所以呢個係
**推論唔係證實**。要坐實就要喺 A/B harness 度加逐場 failure log 再重跑一次。
**完成準則**：A/B harness 會記低每一場失敗嘅 stderr；重跑一次確認失敗率 <1%。

---

## 三、建議次序

1. ~~**2.3**（賽道幾何上網站）~~ ✅ 2026-09-02 完成
2. **2.1**（決定重渲染定向前生效）—— 形勢推演嗰個表仍然要重渲染先出現
3. **2.7**（A/B harness 加 failure log）—— 串行重跑 0 失敗，但未坐實
4. **2.2**（Speedmap 補歷史）—— 要人手開 headed browser
5. **2.5 / 2.4 / 2.6** —— 可以等

## 四、唔好做嘅嘢（已測過）

- ❌ 賽道幾何做排名特徵（EXP-01：三個切法全部越加越差）
- ❌ 跑法做排名特徵（EXP-02：Stage 4 v2 `primary_regression`）
- ❌ 預測起步位做排名特徵（EXP-05：覆蓋 92.5%、AUC 0.5416、ρ +0.147，
  dev 十五個配置 `gold` 從未改善）
- ⏸️ **未試**：場級 `_pace_bias_adjustment()`（步速壓力）—— 早前 wash-to-negative
  所以預設 OFF，但步速圖而家準咗好多，值得重測**嗰個**而唔係再試逐匹加特徵
