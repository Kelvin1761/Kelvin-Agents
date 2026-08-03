---
name: AU Wong Choi
description: This skill should be used when the user wants to "analyse AU races", "run AU pipeline", "澳洲賽馬分析", "AU Wong Choi", or needs to orchestrate the full Australian horse racing analysis pipeline from data extraction through to final deterministic output generation.
version: 6.0.0
---

# AU Wong Choi — Current Mainline

## Current Reality

`AU Wong Choi` 目前主線係 **full Python pipeline**。

而家嘅 live path：

1. Sportsbet extraction
2. `Facts.md` generation
3. deterministic `Race_X_Logic.json` build
4. deterministic auto scoring / ranking
5. `Race_X_Auto_Analysis.md` / `Race_X_Auto_Scoring.csv` / `Meeting_Auto_Scoring.csv`

> 現時主線 **唔需要 LLM 手動填 core logic、verdict 或 `[FILL]` 欄位**。

## 唯一入口

收到 Sportsbet form URL、meeting folder、或現成 `Race_X_Logic.json` 後，唯一正確入口係：

```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```

如果環境冇 `python3`，可改用：

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```

## 覆盤都由呢個 skill 入（唔使再叫 AU Reflector）

用戶講「**au wong choi review 08-01 rosehill gardens**」或者「**覆盤 08-01 flemington**」
嗰陣，唔好叫佢貼路徑或者 URL，亦唔使另外叫 `AU Reflector` skill。先用 resolver 把
一句話變成 meeting 目錄，再交畀 reflector orchestrator：

```bash
DIR=$(python3 .agents/skills/au_racing/au_meeting_resolver.py "08-01 rosehill gardens") \
  && python3 .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "$DIR"
```

分析（唔係覆盤）就同一個 resolver 接落主入口：

```bash
DIR=$(python3 .agents/skills/au_racing/au_meeting_resolver.py "08-01 rosehill gardens") \
  && python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "$DIR"
```

Resolver 認得 `08-01` / `8-1` / `2026-08-01` / `20260801`，馬場名做大小寫無關嘅
子字串（`rosehill` 對得住 `Rosehill Gardens`），live 根目錄同 `Archive/` 一齊搵。

⚠️ **多過一個 match 佢會 exit 1 並列晒出嚟，唔會亂猜** —— 撞錯馬場好過靜靜咁分析錯。
遇到就把個 list 畀用戶揀，唔好自己挑一個。

⚠️ 覆盤要賽果。`--results-url` 已經冇用（唯一來源係 Sportsbet cache），賽果由
Sportsbet 攞 —— 見 `claw_sportsbet_form.py`。

## ⚠️ 抽取一定要行瀏覽器（curl_cffi 而家 403）

`curl_cffi` 對 sportsbetform **全面 403**，包括曾經成功抓過嘅賽事頁。所以
**唔可以**直接靠 `claw_sportsbet_form.py` 出網 —— 佢會靜靜咁攞唔到，然後 Facts
報「數據不足」。正確分工係：

    抓頁面 → 瀏覽器（每版 15–20 秒）
    parse／評分 → Python，全程 cache-only、零請求

步驟：

1. 開 bridge：`python3 .agents/skills/au_racing/sb_browser_bridge.py --port 8787`
2. **發現場次**（唔使用戶貼 link）：瀏覽器開 `https://www.sportsbetform.com.au/{YYYY-MM-DD}/`
   —— 嗰版列晒當日每個場次嘅 puntcdn PDF（檔名帶 meetingId）同每一場嘅
   `/{meetingId}/{raceId}/` 連結。索引頁 curl_cffi 一樣 403，一定要瀏覽器。
3. 喺瀏覽器度逐版 `fetch()` 賽事頁，POST 上 bridge（bridge 會用同一條
   sha1(url) cache path 寫落 `.sportsbet_cache/`）。

   ### 節奏規則（寧慢勿快）

   | 情境 | 間隔 | 備註 |
   |---|---|---|
   | **排程／通宵跑** | **25–35 秒** | 有時間就用呢個。200 版 ≈ 1.8 鐘 |
   | 日常單場次 | 18–25 秒 | 9 場 ≈ 3 分鐘 |
   | 騎練個人頁 | 18–25 秒 | 頁細（44KB）但速率規則一樣 |
   | 最低 | **唔好低過 12 秒** | 更快冇證據係安全嘅 |

   實測基準：818 版 × 22.5 秒 = 5.2 個鐘，**零 403**。之前 curl_cffi 用
   6 秒間隔就被封，而且封到連本來通嘅頁都 403 —— **封鎖係持續嘅，唔係即時
   恢復**（實測隔夜之後 curl_cffi 仍然 403）。所以快少少嘅代價唔係「慢啲」，
   係「今日之內做唔到嘢」。

   ⚠️ **節奏一定要放喺 bridge 嘅 `/wait?ms=`，唔可以用 `setTimeout`** ——
   背景 tab 嘅 timer 會俾 Chrome clamp 到大約一分鐘一次，設 18 秒實際變 100 秒
   （反方向嘅坑：你以為快，其實慢 5 倍，一晚做唔完）。

   ⚠️ 加少少隨機（`+Math.random()*7000`）——**唔係為咗扮人**，係唔好一秒不差
   咁整齊敲門。

   ⚠️ **撞到任何非 200 就即刻停，唔好 retry。** 唔好加速、唔好換指紋。
   個站話唔得就收工，隔幾個鐘再算。

   ⚠️ 抓過嘅一定落 cache。重跑要由 `/jobs` 攞「未落 cache」嘅清單，
   唔好重打已經有嘅版（我試過一次抓 110 個而其中 53 個 cache 已經有）。
4. 騎練個人頁（`/Jockey/{id}/`、`/Trainer/{id}/`）同樣經瀏覽器落 cache，
   然後 `sb_people_stats.refresh(..., cache_only=True)` 讀返。
   ⚠️ 唔用 `cache_only` 就會出網然後失敗，`(LY:)` 全部變 `-`，
   `jockey_score` / `trainer_score` 由 99%/95% 跌到 63%/51%。
5. 之後 `au_orchestrator.py <DIR> --auto --skip-cloudflare-deploy` 全程離線。

⚠️ **`--skip-cloudflare-deploy` 唔可以漏** —— orchestrator 收尾會自動 deploy，
而個 hook 會重發**現時 live 嘅 snapshot**，唔係你啱啱分析嗰個場次。

## Supported Inputs

- 一句話（例：`08-01 rosehill gardens`）— 經 `au_meeting_resolver.py`
- 已存在 meeting folder
- 現成 `Race_X_Logic.json`
- ~~Racenet form-guide URL~~ — Racenet 2026-08-02 全面封鎖，相關腳本 2026-08-04 已由 repo 剷走；只用 Sportsbet

## Expected Outputs

- `*Racecard.md`
- `*Formguide.md`
- `*Race N Facts.md`
- `Race_X_Logic.json`
- `Race_X_Auto_Analysis.md`
- `Race_X_Auto_Scoring.csv`
- `Meeting_Auto_Scoring.csv`

## Guard Rails

- **嚴禁**跳過 orchestrator 手動拼裝 extraction / facts / logic / output
- **嚴禁**假設要跟 `NEXT_CMD` 做 LLM-driven workflow
- **嚴禁**再用舊 active-path legacy orchestrator
- **嚴禁**手動補 deterministic analysis 欄位

## Related Components

- `.agents/scripts/inject_fact_anchors.py`
- `au_wong_choi_auto/scripts/build_au_logic.py`
- `au_wong_choi_auto/scripts/au_auto_orchestrator.py`
- shared post-success Cloudflare deploy hook

## Archived Legacy Snapshot

如用戶明確要求 legacy comparison，封存版本喺：

- `.agents/archive/wong_choi_legacy_snapshot_20260526/au/au_orchestrator_legacy_snapshot_20260526.py`

用途只限：

- 舊 output 對照
- 手動考古比對
