# 競賽主任報告 live 來源（H5，Kelvin 2026-11-26「做 1-3」第 3 項）

唯讀研究（subagent，每個網站 ≤10 次請求，冇繞過任何驗證、冇登入）。目的：上仗競賽主任報告（出閘慢、受阻、大外冇遮擋、獸醫）
做下一仗嘅賽前輸入（EXP-20261125-06 H5）。

## 已知（唔使再量）
- EXP-20261107-01（舊 Racenet 語料 8,439 對）：**途中受阻 → 今仗冇反彈（−0.77pp），市場反而高估（−3.9pp）**；
  大外冇遮擋 +5.79pp（Holm 0.045）但市場已計入（+0.27pp）。所以「受阻扶高排名」唔值得做；值得追嘅只有 WIDE、VET。
- Sportsbet form 頁（現役來源）**冇**競賽主任評語（cache 13,709 頁 grep 過）。
- NSW：`racingaustralia.horse/PostStewardsReports/*.pdf` 批量抓會觸發「Are you human?」（2026-11-22），而且
  **robots.txt `User-agent: * Disallow: /`** —— 唔准抓。要嘛同 Racing Australia 傾授權，要嘛接受 NSW 缺。

## 各州（2026-11-26 測試）

| 州 | 位置 | 格式 | 歷史 | robots | 普通 GET |
|---|---|---|---|---|---|
| QLD（QRIC，經 Racing Queensland） | `racingqueensland.com.au/racing/full-calendar/thoroughbred/meeting/<場代碼>/<YYYYMMDD>/stewards-report` | HTML，每賽日一頁、分場；逐駒「HORSENAME – 文字」 | 2019 起 | 冇 Disallow | ✅ |
| TAS（Tasracing Integrity） | `tasracing.com.au/hubfs/<YYYY-MM-DD> - <會名> - Stewards Report.pdf`（檔名後綴有時唔同） | PDF，文字，含獸醫跟進 | 2024 起 | 准 | ✅ |
| WA（RWWA） | `static.p.racingwa.com.au/race-files/<id>/0/steward/<場><DDMMYYYY> bwl-<epoch>.pdf` | PDF | 未知 | PDF 主機未測 | PDF ✅；rwwa.com.au 有 Vercel 驗證（429）→ 搵唔到索引 |
| SA（Racing SA） | `racingsa.com.au/files/<seq>_<code><DDMMYY>.pdf`、S3 資產主機 | PDF，逐場逐駒＋賽後獸醫 | 2019 起 | Crawl-delay: 10 | 混合（舊檔 403）；索引頁未搵到 |
| VIC（Racing Victoria） | `racingvictoria.com.au/integrity/stewards/stewards-reports` | 頁面要 JavaScript 先出內容 | 未知 | Allow | 空殼；要無頭瀏覽器或者底層 JSON |
| NSW | 見上 | PDF | ≥1 年 | **Disallow** | ❌（驗證） |

## 建議
1. **試點用 QLD**：HTML、逐駒行、robots 准、歷史長 —— 可以先喺 2019 起歷史量「WIDE／VET → 下仗」（Holm、市場殘差、
   只用今場之前嘅報告），PASS 先寫 live 抽取。TAS 次之（PDF）。
2. 全部係各州機構版權；商業用途要 Kelvin 寫 email 問准（RQ/QRIC、Tasracing Integrity、RWWA、RV）。低頻、每日少量抓公開頁係
   技術上可行，法律基礎未確認 → **未得 Kelvin 同意唔寫抓取器**。
3. NSW／VIC 佔 AU 場次大頭：NSW 要授權（可能收費），VIC 要另外研究頁面嘅資料接口。
