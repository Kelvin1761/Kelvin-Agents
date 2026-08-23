# EXP-20260823-04 合夥練馬師名 0% 解析成功率 —— HTML entity 冇解碼

- **日期**：2026-08-23
- **平台**：AU
- **起因**：用戶問「Gunroom 個 `trainer_score` 點會係 fallback？我哋唔係有齊
  Sportsbet 嘅騎練數據嗎？」
- **改到嘅檔案**：`claw_sportsbet_form.py`（`_people_key` 加 `html.unescape`）
  ＋ 4 個 test

## 根因

`_match_person` 要把**總覽表嘅全名**配去**連結文字嘅 person id**（連結文字係截短嘅，
所以用前綴比對）。但連結文字係 HTML，合夥練馬師寫成 `Brett &amp; Georgie`。

`_people_key` 做 `re.sub(r"[^a-z0-9]", "", name.lower())` —— **冇 unescape**，
所以 `&amp;` 被剝成 **`amp`** 留喺 key 中間：

| 來源 | 原文 | key |
|---|---|---|
| 連結（截短） | `Brett &amp; Georgie` | **`brettampgeorgie`** |
| 總覽表（全名） | `Brett & Georgie Cavanough` | `brettgeorgiecavanough` |

兩者互相都唔係前綴 → `pid=None` → `trainer_score` 跌落 fallback 60。

## 規模同修復

實測 80 個 cache 頁：

| 類別 | 合夥名 | 修前成功率 | 修後成功率 |
|---|---|---|---|
| Trainer | 單人 | 95.9%（93/97） | 95.9%（不變） |
| **Trainer** | **合夥（`&`）** | **0.0%（0/6）** | **100.0%（6/6）** |
| Jockey | — | 100.0%（92/92） | 100.0%（不變） |

**合夥練馬師佔 runner 5.8%**，全部白白跌落 fallback。`trainer_score` 有效排名
權重 **7.58%**。

修法：`_people_key` 先 `html.unescape()`。一行。

## ⚠️ 生效時點

同 EXP-03 一樣，`(LY: …)` token 係**抽取時**寫落 Formguide 嘅，所以：
- 已存語料唔會變
- 真實效果由下一次抽取開始

## 另外兩個殘留問題（未修）

### ① 單人名仍有 4/97 查唔到 —— cache 唔齊，唔係名字問題

`Alan D Smith`（pid=6505）、`Mark Howard`（pid=3577）—— **pid 查到咗**，但
`AU_Sportsbet_People_Cache.json` 冇嗰個 id 嘅條目。屬於 cache 覆蓋率問題，
唔係配對問題。

### ② `trainer_score` 冇記錄但 `evidence_state` 標 `observed`

Gunroom：`trainer_score` = **60.00**，note 寫「Sportsbet 官方統計未有可用記錄」，
但 `evidence_state` = **`observed`**。後果係 `data_coverage` 報 80%（8/10）而真實
應該係 70%（7/10）—— **低報咗缺數據程度**。唔影響排名（`data_coverage` 只餵
`confidence_score`，而佢 0% 權重），但會令人睇報告時以為證據比實際厚。

## 檢查
- **run_tests.sh**：九個 suite 全綠（新增 4 個 test）
- 寫 test 時我第一次用 `parents[3]` 取 repo 路徑，錯咗一層（`claw_sportsbet_form`
  住喺 `parents[2]` 即 `au_racing/`）—— 正好係 repo 反覆中招嘅 sys.path 陷阱。

**決定**：**KEEP**
