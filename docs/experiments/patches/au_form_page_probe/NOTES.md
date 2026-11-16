# AU 往績頁唔使瀏覽器：對照測試（2026-11-16，未完成）

目標：AU 抓 sportsbetform 往績頁唔再開 headed Chrome，好似 NBA／網球咁全背景跑。

## 來源

- Sportsbet 主站 API `Racing/Events/{id}/RacecardWithContext` 嘅 `racecardEvent.longFormLink`
  指去 `https://www.sportsbetform.com.au/form/<CODE>_<DDMMYYYY>_<NN>.html`（全場一版）。
- `curl_cffi`（chrome120）攞到 200，**現有 `parse_race()` 唔使改就讀到**。
- 冇賠率（`overview[*].fixed_win` = `-`、`meta.odds` 空）同開跑時間（`meta.start`）；兩樣主站 API 都有。
- 手機版 `/mobile/{eventId}/{n}/` 每版只得一匹馬嘅完整往績，唔適合；但佢有逐駒分段速度
  （Early／Mid／Late km/h、1000/800/600/400/200m 分段），係新資料，要入模型就係另一個實驗。

## Run 1：2026-11-16 Goulburn + Wangaratta（16 場，**賽後**抓）

命令：

    python3 compare.py --date 2026-11-16 --venues Goulburn Wangaratta \
      --cache /Users/imac/wongchoi-scheduler/.agents/skills/au_racing/.sportsbet_cache --out <dir>

- 抓取：15 版連續，每版約 29 秒，全部 200，零 403。
- 瀏覽器 cache 係當日 12:00 賽前版；`/form/` 係 18:20 賽後版，所以已經包咗當日嗰仗。
  剔走 16/11 嗰仗之後按 (日期, 場地, 場次, 名次, 檔位, 騎師) 配對：
  - 1,889 條完全一致，1 條 SP 唔同（3.80 vs 3.40）
  - 130 條只喺瀏覽器版（40 條試閘）、18 條只喺 `/form/`（部分係首出標籤 `First Start <場地>`）
    —— 推測係賽後頁加咗當日一仗之後擠走最舊嗰條，未證實。
  - `track_condition` 9 場唔同：日間場地更新（Good 4→3、Soft 6→7），唔係 parser 問題。
  - `people_names`：瀏覽器版有 `&amp;` 未 unescape，`/form/` 版反而乾淨。
- **結論：未可以判。** 一定要做賽前對賽前（同一時間窗）先知 130／18 條係咪真差異。

## 下一步

1. 22:00 evening job 用瀏覽器抓完翌日場次之後，即刻用 `/form/` 抓同一批，賽前對賽前比。
2. 一致先寫正式 fetcher：`/form/` 頁 + API 補賠率同開跑時間；瀏覽器留做後備。
3. 抽取結果有任何唔同 → 改咗模型輸入，要行 `model-regression-gate`。
