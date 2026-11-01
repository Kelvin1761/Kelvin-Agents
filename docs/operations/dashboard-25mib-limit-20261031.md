# 2026-10-31：16 個 AU 場次只有 9 個上到 dashboard

## 發生咗咩

全部 16 個場次（132 場）本機都分析完。但係 morning run（10:00 slot，試咗 3 次）
合併到第 10 個場次嘅時候，`dashboard-data.json` 已經去到 24.9 MiB。之後每加一個場次，
個檔就會變成 25.7–26.9 MiB，超過 Cloudflare Pages 單檔 25 MiB 嘅上限，所以發佈閘將
Dalby、Morphettville、Mortlake、Newcastle、Randwick、Traralgon、Wycheproof 放咗入
`publication_rejected`。

## 點解咁大（量度 live snapshot）

| 部份 | 大細 |
|---|---|
| `sports_feed.tennis.tracking.records`（14,350 條，plain JSON） | 12.2 MiB |
| 每匹馬獨立 gzip 嘅 `raw_text`（812 匹） | 5.78 MiB |
| `data_readout` + `dimension_details` | 3.14 MiB |

Tennis tracking 由 `f38d9333`（2026-10-27）開始「完整、唔設上限」，所以每日都會變大。
10-27 起 run log 已經有「逼近 25 MiB 上限」警告，但淨係寫入 log，冇人睇到。另外錯誤訊息
寫死咗「最大標的係 raw_text」，令人追錯欄位。

## 長遠修正

1. **只增唔減嘅內容一律打包。** `generate_static.pack_for_transport` 將每個場次嘅
   `raw_text`／`data_readout`／`dimension_details` 打包成一個 gzip blob
   （`horse_fields_gzip`），tennis tracking 打包成 `records_gzip`。JSON 同 HTML
   都用同一種格式；`load_snapshot` 同前端 `unpackDashboardData()` 會喺任何嘢讀之前還原。
   排程驗證要用嘅欄位（場次、race_number、分數、賠率）保持 plain JSON。
2. **size 閘門會實際量度，唔再估。** 超過 20 MiB 就列出最大嘅幾個部份。
3. **健康通知會提前預警。** live snapshot 用咗超過上限 60%（15 MiB），`au_healthcheck`
   就會出 advisory（`WC_SNAPSHOT_HEADROOM_WARN` 可以改門檻）。

## 驗證（今日真實數據，17 個場次 / 138 場）

| | 修正前 | 修正後 |
|---|---|---|
| Snapshot JSON | 25.7–26.9 MiB（被拒） | 10.99 MiB |
| Dashboard HTML | 推算約 28 MiB | 8.15 MiB |

- 原本已上線嘅 10 個場次經新格式「打包 → 還原」之後逐個欄位一樣（10/10）。
- 1,438 匹馬全部還原到 `data_readout`／`dimension_details`；tennis 14,353 條齊。
- 頁面解壓用 186 ms。
- 每個場次大約 0.55 MiB，所以 JSON 可以容納大約 40 個場次。

## 下次再撞上限

睇 deploy log 嗰行「最大嘅部份」。如果係一個新嘅只增唔減欄位，就加入
`PACKED_HORSE_FIELDS`，或者幫佢寫一個好似 `_pack_tennis_tracking` 咁嘅 packer，
**唔好剪數據**。
