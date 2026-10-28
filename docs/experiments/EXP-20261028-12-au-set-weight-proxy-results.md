# EXP-20261028-12 結果：定磅賽唔再用負磅代理 —— §7 正確性修正上線

> **呢個冇通過表現閘，唔係一個已證實嘅改善。** 上線理由係 code 聲稱嘅行為同事實唔符，而且冇顯著退步。

- **預先登記**：[protocol](EXP-20261028-12-au-set-weight-proxy-protocol.md)（`945bbbdb`（rebase 前 `75f54ce8`）；分類截斷附註喺量度前補）。
- **語料**：同 EXP-20261028-11（3,818 場；v3 2,948 場；§8 2,012 場）。
- **決定**：**B1 上線**（§7），連同 EXP-20261028-13 C3 一齊；B2 只係對照。

## 錯處

`_handicap_weight_proxy` 聲稱定磅賽唔用負磅代理，但 `_is_wfa_or_sw_race()` 只認 `maiden plate`／`wfa`／`sw`／`set weights`。
語料入面賽事名寫明係定磅（PLATE、QUALITY、STAKES、MAIDEN、QTIS）而照用負磅代理嘅有 **1,265 匹**
（892 匹「級數＋負磅」各半、373 匹「混合場只用負磅」）。報告同時寫「讓磅賽由能力定磅，頂磅＝讓磅官評為能力最高」。

## 診斷：定磅賽嘅負磅其實係咩

喺「非讓磅、而 baseline 有用負磅代理」嘅 310 場，場內配對 AUC（前三 vs 其他）：

| 訊號 | AUC |
|---|---:|
| 負磅代理 | **0.511** |
| 性別（雄 > 雌） | 0.524 |
| 年齡（大 > 細） | 0.469 |
| 級數分 | **0.565** |

負磅代理喺定磅賽近乎擲毫。8 月量到嘅 0.577 係喺讓磅賽同定磅賽混埋量。年齡、性別都唔值得另開特徵。

## 判決（v3 fixed_rule，2,948 場）

| | 改到場數 | Gold | Good | ranking | 分層 CI 全負 |
|---|---:|---|---|---|---|
| B1 | 310 | −0.07pp [−0.33, +0.20] p 0.67 | −0.03pp [−0.19, +0.10] | top3 −0.0001、NDCG +0.0003、AUC +0.0003（全部跨零） | 冇（今場代理場 Gold −0.17 [−0.88, +0.48]） |
| B2（對照） | 185 | 0.00 | −0.03 | 全部跨零 | 冇 |

§7 四項：錯處獨立可證 ✅；零顯著退步 ✅；leakage（賽事名係賽前資料）✅；本檔已寫明唔係改善 ✅。
§8（參考，唔影響判決）：fixed／refit 都 `primary_regression`，refit B1−B0 Gold −0.10pp、Good −0.10pp，唔顯著。

## 實施

- `engine_core._is_handicap_title()`／`_is_handicap_race()`：正面認讓磅（handicap／hcp／benchmark／bm64／rating 0-64 組別、
  加截斷嘅 handicap 前綴），取代 `_is_wfa_or_sw_race()`。賽事名空白當非讓磅。
- `_handicap_weight_proxy` 同 `_weight_score`（唔入排名，但「頂磅：讓磅官評為本場能力最高之列」呢句由佢出）都用新判斷。
- **合併檢查（B1 + EXP-13 C3，真引擎重 dump，唔係 replica）**：2,948 場 Gold −0.03pp [−0.37, +0.26]、Good −0.03pp [−0.28, +0.24]，
  三個 ranking 指標全部跨零，冇分層 CI 全負（`v3_engine_B1C3.json`）。
- 引擎 vs replica：121／37,560 匹對唔上（最大 1.65 分）。原因係 replica 冇模擬 `analyze_horse` 嘅
  「近績分 ≥ 72 而級數分 < 60 → 近績分 −4」—— C3 令部分馬嘅級數分跨過 60。合併判決用嘅係真引擎，唔受影響。

## 實例（Warwick Farm 2026-10-28 R1，ASAHI SUPER DRY PLATE）

| 馬 | 負磅 | Rating 分 前 → 後 | 排名 前 → 後 |
|---|---|---|---|
| Snitzel's Girl（3 歲雌） | 54.5kg | 55.5 → 61.8 | 1 → 1 |
| My Ju Ju（4 歲閹） | 59.0kg | 63.7 → 55.0 | 5 → 7 |
| Palm Tree | — | 54.6 → 59.4 | 8 → 5 |

## 重跑

同 EXP-20261028-11；合併檢查：

```bash
python3 scratch/au_fq_weight_class_dump_20261028.py --out $X/dump_new.json      # 改動後
python3 scratch/au_fq_weight_class_judge_20261028.py $X/arms/base.json $X/dump_new.json $X/v3/engine_B1C3.json --extra proxy --extra group:G15
```
