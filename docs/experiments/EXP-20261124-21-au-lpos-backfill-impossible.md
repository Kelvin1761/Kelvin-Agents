# EXP-20261124-21 AU Lpos 歷史回填（EXP-20261120-87）停止 —— Sportsbet AllRacing 只回溯約 11 日

- 日期：2026-11-24　平台：AU　類型：管線修正（停 job），冇判決
- 發現：Claude AU 覆核（Kelvin 2026-11-24）；forward tracker 顯示 `lpos_backfill 0 / 3974`。

## 發生咩事

`run_au_auxiliary.sh mobile-sectionals` 由 2026-11-21 起每晚 forward 抓完就跑 `fetch --backfill`（08-05 → 11-05）。
每晚第一個請求 `AllRacing/2026-08-05` 就 HTTP 400，即停：

```
{"state": "stopped", "stop_reason": "AllRacing 2026-08-05: HTTP 400"}   # 11-23、11-24 一樣
au-lpos-backfill-status.json: races_collected 0, idle_nights 3, state collecting
```

冇 Telegram（`state` 一直係 collecting，forward tracker 要夠數先推）。預先登記嘅「連續 3 晚冇進度就收」條件
啱啱到期 —— 下一晚會喺 0 場上「完成」。

## 量度（2026-11-24，同一個 `curl_cffi` chrome120 session，每次隔 3 秒）

| 日期 | HTTP |
|---|---|
| 11-23、11-20、11-17、11-14 | 200 |
| 11-12、11-10、11-01、10-25、10-15、09-15、08-05 | 400 `{"message":"Invalid Date","code":"ERR-IS"}` |

即係 API 只保留約 10–11 日。08-05 → 11-05 結構上抓唔到，唔係被擋、唔係時間窗唔夠。

## 處理

- `run_au_auxiliary.sh`：`mobile-sectionals` 只跑 forward fetch（`exec`），回填同 `au_lpos_backfill.py` 唔再叫。
- `au_forward_tracker.FORWARD_TESTS`：剷 `lpos_backfill`（留註解）。
- `au_lpos_backfill.py` 同佢嘅測試保留（重現／紀錄用），冇 caller。
- EXP-20261120-87：**放棄，冇判決**（唔係 REJECT）。Lpos 只靠 EXP-20261116-20 forward（11-24：297 / 2,500）。

## 教訓

設計回填之前要先探來源保留幾耐（一個請求就答到）。要歷史，只可以喺 11 日內抓落嚟自己存。
