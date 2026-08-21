---
name: data-quality-audit
description: 'Check incoming and stored data before trusting any model output in the Wong Choi pipelines. Use this skill when importing or scraping new data, changing a data source or parser, adding historical data, running a scheduled prediction pipeline, or whenever model performance degrades for no explained reason — check the pipeline before blaming the model.'
---

# data-quality-audit

## 呢個 repo 每一個貴嘅數據 bug 都係同一個形狀

欄位**繼續存在**、code **繼續行**、**冇 test 紅燈** —— 但**值**靜靜變空、
變常數、或者變過期。單元測試睇唔到：佢 assert 自己餵入去嘅 input，
永遠冇睇過 live scraper 真係出咗咩。

實例：
- Sportsbet form page 洩漏當場（17.1% 嘅 run）
- Racenet generic slug（`race-N`）全部靜靜回 race 1
- 七個州曆凍結喺 11 日前（永久 cache）
- `speedmaps=` 寫落每個 call site，**0 行真值**
- **AU results CSV ingestion 停咗一個月，test 全綠** —— 每個 harness 靜靜評估
  一份舊、細嘅語料庫
- `au_statistics_aggregator` 跑一次會用 4,563 行 / 2 場地 覆蓋 12,684 行 / 62 場地

## 現有工具（唔好另寫）

```bash
# 欄位級數據合約：presence / neutral 比例 / 場內散佈 / 值域
python3 .agents/skills/shared_racing/scripts/data_contract.py --platform au --check
python3 .agents/skills/shared_racing/scripts/data_contract.py --platform hkjc --check

# 逐個場次嘅對齊 + 覆蓋率閘（只讀賽前 artifact，唔會變成洩漏路徑）
# ⚠️ 佢係 per-meeting scanner，一定要兩個參數，而且要 PYTHONPATH=<repo root>
PYTHONPATH=. python3 .agents/skills/shared_racing/scripts/racing_data_health.py \
    --platform au --meeting-dir "<meeting folder>"
# ⚠️ 目前只有 hkjc_orchestrator 會自動叫佢；AU 主流程冇接 —— AU 要手動跑

# 來源連結 + neutral/fallback 覆蓋
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_source_coverage_audit.py

# 賽果語料庫有冇停 ingest
python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_results_ingest.py
```

`data_contract.py --calibrate` 由現有語料庫**學**返 baseline，所以個門檻係量出嚟
唔係猜。改完評分邏輯要重新 `--calibrate`。

## 檢查清單

**行數 / 覆蓋**
- [ ] 今次 ingest 咗幾行？同上次同類 run 差幾多？**行數靜靜跌 = 最常見嘅症狀**
- [ ] 語料庫最新日期係幾時？同今日差幾多？（曾經差五星期冇人知）
- [ ] 場地／賽事數目有冇跌（`au_statistics_aggregator` 個 degradation guard）

**欄位值，唔係欄位名**
- [ ] 每個關鍵欄位嘅**非空**行數（唔係 key 存在）
- [ ] 中性值（60.0）佔幾多 %？升咗 = 「停止填」
- [ ] 場內標準差 —— 跌到近 0 = 「變常數」
- [ ] min/max 有冇離譜（單位／parse 反轉）

**schema / 型別**
- [ ] 欄位有冇改名／消失／多咗
- [ ] 型別有冇變（str ↔ float，日期變 epoch）
- [ ] 上游 HTML/JSON 結構有冇改（scraper 靜靜失敗只有一個形狀：
      一個過嚴嘅 regex，或者一個冇上限嘅 window。**先數 page-has vs parsed**
      再落結論話個欄位「冇數據」）

**日期**
- [ ] 有冇無效日期 / 未來日期
- [ ] 日期有冇斷口（缺整個 meeting / 整個星期）
- [ ] 有時間窗嘅欄位（官方評分、州曆、going）係唔係鮮嘅 —— cache TTL 對唔對

**重複 / identifier**
- [ ] 同一場 meeting 有冇兩份記錄
- [ ] 馬名／球員名撞名（tennis：姓名要 ±1 日 + 姓先名縮寫處理）
- [ ] join 失敗率：join 完之後行數少咗幾多？**silent left-join 掉行係大殺傷力**
- [ ] `Race_X` vs `Race 1` 混用、退出馬重編檔位

**分佈**
- [ ] 關鍵欄位嘅分佈同上一期比（KS 或簡單 quantile 表）
- [ ] population 組成：場地／going／班次比例有冇大變。**時間切分等同 condition
      切分** —— 印出組成先，唔好當係同一個 population

## 兩條規矩

1. **懷疑就大聲死，唔好靜靜出預測。** 語料庫過期、覆蓋率跌穿門檻、
   關鍵欄位變常數 —— exit non-zero，唔好照跑落去出 prediction。
   `data_contract.py --check` 已經係咁做，新 pipeline 照跟。

2. **唔准「修」可疑值而唔記錄。** 任何 clamp / 填補 / 覆寫都要記低：
   改咗幾行、由咩改成咩、點解。冇記錄嘅「清洗」= 之後查唔到嘅假數據。

## 特別注意（呢個 repo 專屬）

- **`Archive/` 係語料庫排除名單**，唔係「完成場次擺呢度」。搬入去 = 由每個
  backtest 消失（實測 33 個場次中招）。
- **舊 AU 語料係賽後重新評分過嘅** —— 乾淨 point-in-time 只有 2026-08-05 起。
- **J/T 組合表有兩份**：引擎讀 `resources/` 嗰份，aggregator 寫 `AU_Racing/`
  嗰份，冇自動同步。
- **`檔位` 喺 racecard 係原本抽嗰個**，退出馬會重編；只有
  `Race_Results_*.json` 對得足。
- **Drive 讀取會 stall**：listing 即時，file read 冇 exception 咁掛住。
  用 SIGALRM 偵測，fallback 去 scratch cache。
- **外置碟 launchd 讀唔到**：`stat()` 成功但 listdir/read/write 全拒絕。
  `is_dir()` 唔可以當可讀性探測。
