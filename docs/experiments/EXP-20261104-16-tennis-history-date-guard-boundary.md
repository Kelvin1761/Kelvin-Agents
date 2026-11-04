# EXP-20261104-16 Tennis 歷史發球點數日期閘界線

2026-11-04 06:40 UTC。以 [EXP-15 官方逐場對照](EXP-20261104-15-tennis-official-match-reconciliation.md) 嘅 Madrid F 作固定反例，沿用 [EXP-14](EXP-20261104-14-tennis-cross-provider-point-overlap.md) 封存 manifest `e6dbf1f4a0a63ef007c58f5431488d58a555a7790412046582e6fbb7cb969a61`。正式 18:00 Sydney 排程當時未到。今次只執行唯讀審計同記憶體 SQLite。

現有 `features/history_asof.py` 容許 `match_date < as_of_date - 13 days` 嘅行略過 `created_at`。以下直接執行現有 SQL helper。4 月 22 日係 Sackmann 嘅 Madrid F 紀錄日，實際決賽係 5 月 3 日。11 月觀測時間係隔離測試值，用嚟驗證後來取得嘅資料會點處理。

| 模擬截點 UTC | 原閘接納行數 | 逐行觀測時間嚴格早於截點 |
|---|---:|---:|
| 2026-05-03 00:00 | 0 | 0 |
| 2026-05-05 00:00 | 0 | 0 |
| 2026-05-06 00:00 | 1 | 0 |

重現方法，喺 tennis package 目錄用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3`：

```python
import sqlite3

from tennis_wc.features.history_asof import guard_clause, guard_params

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE h(player_id, opponent_id, match_date, created_at)")
conn.execute("INSERT INTO h VALUES (1, 2, '2026-04-22', '2026-11-04T06:38:43Z')")
query = "SELECT count(*) FROM h WHERE match_date < ?" + guard_clause()
for day in ("2026-05-03", "2026-05-05", "2026-05-06"):
    print(day, conn.execute(query, (day, *guard_params(day, day + "T00:00:00Z"))).fetchone()[0])
```

全量再按 provider、tour、原來源 key 去掉最後一節得到嘅 edition key、stored day、球員分桶。每桶要有多於一個來源賽事 key。固定排除 held 同 incomplete 組，兩個 provider 合計 71,658 組。

| Provider | 雙側組 | 同 edition 同日同球員重複桶 | 涉及來源賽事 key | 一桶最多紀錄 |
|---|---:|---:|---:|---:|
| Sackmann | 29,419 | 15,348 | 28,397 | 7 |
| TennisMyLife history | 42,239 | 21,746 | 39,998 | 6 |

呢個係 stored day 粒度診斷。相同日可以有多場，數字未證明每一筆日期都係賽事起始日。四場官方對照亦未能外推 TML 全歷史都係實際賽事日。F02 嚴格重播要檢查選用版本嘅實際觀測時鐘同逐場完場證據，不能以現有 13 日閘或固定 provider 優先次序代理。未量度正式歷史卡受影響比例，未更改現役讀取或舊回測判決，新增合資格 0。
