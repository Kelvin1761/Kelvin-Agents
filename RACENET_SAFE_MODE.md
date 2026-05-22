# RACENET Safe Mode

呢份手冊係畀 AU Wong Choi / AU extractor 喺 Racenet 解封後，盡量減低再次觸發 browser challenge / cookie check 封鎖。

## 核心原則

1. 只用真實 Chrome session + 有效 cookies。
2. 唔好用 free VPN、住宅代理、或者會轉 IP 嘅不明網絡。
3. 唔好同一時間開多個 AU Racenet 腳本。
4. 唔好長時間 batch 掃站，除非你明確知道自己做緊乜。
5. 一見到 block / cooldown，就即停，唔好連續重試。

## 現時預設保護

AU Racenet transport 而家預設係 `strict` mode，會做以下保護：

- 停用無 cookies 嘅 stateless HTTP probe。
- 預設要求本機 Chrome session 或 storage-state cookies。
- 會 clone 一份臨時 Chrome profile 去跑，避免直接撞你主 profile。
- 同一個 process 內會 cache 相同 URL，避免重覆打站。
- 內建 request guard：
  - 最少間隔：`4` 秒
  - 每 process 上限：`18` 次
  - 每小時上限：`40` 次
  - 一旦偵測 block，會進入 cooldown，期間拒絕再打 Racenet

## 開跑前 Checklist

每次正式跑 AU Wong Choi 之前，先做以下幾步：

1. 用正常 Google Chrome 開一次 [Racenet](https://www.racenet.com.au/)。
2. 確認冇用 free VPN。
3. 關掉唔需要嘅舊 crawler / batch script terminal。
4. 如果之前試過被 block，先做 probe。

## 安全 Probe

先測試連線：

```bash
python3 .agents/skills/au_racing/au_race_extractor/scripts/check_connection.py
```

如果成功，先再跑正式分析。

如果見到 `guard is cooling down`，代表之前已經觸發保護，應該等 cooldown 完結，唔好即刻再試。

## 安全日常用法

最建議日常跑法：

```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL>"
```

通常唔需要手動設 env，因為 `strict` mode 已經係預設。

如果你想明確寫死安全設定，可以用：

```bash
RACENET_SAFETY_MODE=strict \
RACENET_USE_LOCAL_CHROME=1 \
RACENET_HEADLESS=0 \
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL>"
```

## Bulk / Backfill 規則

以下腳本而家預設唔會直接跑：

- `.agents/skills/au_racing/au_wong_choi/scripts/batch_discovery.py`
- `.agents/scripts/au_season_batch_crawler.py`
- `.agents/scripts/backfill_auto_analysis.py`

如果真係要跑，必須明確加：

```bash
RACENET_BULK_MODE=1
```

而且建議同時拉長 cooldown：

```bash
RACENET_BATCH_COOLDOWN_SECONDS=90
```

如果唔係必要，唔好開 bulk mode。

## 遇到 Block 時

如果出現以下訊息：

- `Request blocked`
- `403`
- `cookie`
- `browser challenge`
- `guard is cooling down`

請跟以下流程：

1. 即刻停止所有 AU Racenet 腳本。
2. 唔好反覆重跑 probe。
3. 用正常 Chrome 手動打開 Racenet，確認網站是否正常。
4. 等 guard cooldown 完結後先再試。
5. 如果 Racenet support 已經手動解封你，先確保當下冇其他 crawler 仲喺背景跑。

## Guard 檔案

guard 狀態預設會寫喺：

```text
~/Library/Caches/Antigravity/racenet_guard.json
```

用途：

- 記錄 request window
- 記錄最近一次 block
- 記錄 cooldown 到幾時完

除非你已經確認 Racenet 真係解封，而且冇任何舊 script 仲喺跑，否則唔建議手動刪除。

## 高風險動作

以下做法好容易再次出事：

- 手動開幾個 terminal 同時跑 AU scripts
- 開 `RACENET_ALLOW_STATELESS_HTTP=1`
- 開 bulk mode 之後連續掃大量日期
- 用 free VPN / 會自動換線嘅代理
- 見到 403 後不停 retry

## 建議習慣

- 每次只跑一個 meeting。
- 跑完一場 meeting，再等一陣先開下一場。
- 長任務前先做 `check_connection.py`。
- 如果要做歷史補數，分批做，唔好一口氣跑成季。

## 快速指令

安全 probe：

```bash
python3 .agents/skills/au_racing/au_race_extractor/scripts/check_connection.py
```

正式分析：

```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL>"
```

明確 strict mode：

```bash
RACENET_SAFETY_MODE=strict RACENET_USE_LOCAL_CHROME=1 RACENET_HEADLESS=0 \
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL>"
```

啟用 bulk mode：

```bash
RACENET_BULK_MODE=1 RACENET_BATCH_COOLDOWN_SECONDS=90 <your command>
```
