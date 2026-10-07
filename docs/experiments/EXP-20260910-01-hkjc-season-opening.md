# EXP-20260910-01 HKJC 開季：直接減檔位 REJECT；零出賽扣分修正

- 日期：2026-09-10；平台：HKJC。
- Baseline：`0116c740330db7f02f9d04d2884e211b1d494517`。
- 搜索：EXP-20260902-03/08、EXP-20260904-04/07/09。
- 假設A：檔位與走位轉10個百分點去狀態可改善上名捕捉。
- 假設B：零出賽不可當作已出賽而未上名（可獨立證明的正確性）。
- 兩項單獨比較；沒有選擇最優權重或組合搜索。

## 語料與結果

首場前snapshots：09-06沙田10場、09-09跑馬地8場。原排名與保存rank逐場完全一致。
新增這18場觸發診斷，不視作未見過的holdout。
歷史PIT騎練回放：193場／2438匹／19日期，05-06至07-12。
固定最後15%完整日期（07-04/08/12）31場terminal，其餘162場dev。
無模型訓練；固定A只跑一次；無調參或多輪holdout選擇。

| arm | 歷史Gold | 歷史Good位 | 首選勝出 | 決定 |
|---|---:|---:|---:|---|
| baseline | 14.51% | 26.42% | 26.42% | — |
| A shape 27.37→17.37%; stability 9.83→19.83% | 11.40% | 22.28% | 22.28% | REJECT |
| B 零出賽不扣季內未上名 | 14.51% | 26.42% | 26.42% | 正確性修正，保留本機 |

A dev Gold −4.32pp、Good −6.79pp，已不能過primary gate；不再調參。
terminal Gold +3.23pp CI[−6.45,+16.13]、Good +9.68pp CI[0,+22.58]；
不以terminal表現抵銷dev失敗。場地cohort：沙田Good −5.38pp、跑馬地−1.59pp。
新季18場A局部改善（Good 2→3；首選3→4），不構成可上線證據。

B 在新季213匹中210匹取消錯扣；兩日全排序不變。
歷史primary及首選命中不變；NDCG平均−0.000017，無顯著下降。
因此B是§7正確性修正，**沒有通過表現改善閘，不是已證實的命中率改善**。

## 財將

模型第12（55.78）→實際第二。相對同場平均的加權差額：段速−2.801、
騎練−1.118、檔位反而+0.770。單一心律異常大敗帶出多個相依段速負面訊號。
原始輸入已含事故；新增報告提示其相依性、區分已知醫療事件與資料缺失，均不入分。
沒有刪去最差一仗，也沒有替此馬設定排名特例。

## Leakage與限制

新條件只讀原本賽前season_stats的starts，醫療提示只讀原有medical_flags，
未引入當場結果、市場賠率或事後覆檢資料。此增量leakage audit PASS。
整份歷史衍生特徵來源尚未全面證明PIT；回放只是修好日期及騎練先驗，
不能用它宣告一個複雜模型可promotion。A已在dev失敗，無需新增參數搜索。

## 驗證及改動

- `engine_core.py`：zero-start guard；兩處醫療敘述。
- `test_zero_start_season.py`：4個評分測試、3個判讀測試。
- HKJC data contract重新calibrate；模型說明由生成器更新。
- 原120匹golden全部一致。record曾重抽新sample，為保留可回退基準，
  最終保留原snapshot；此golden只覆蓋矩陣，leaf修正由新增測試負責。
- 完整檢查結果見主審計報告。未commit、push、deploy。

完整逐場數字、分層及CI：[REVIEW.md](../audits/hkjc-season-opening-20260910/REVIEW.md)。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/hkjc-season-opening-20260910/run_audit.py --out /tmp/hkjc-season-opening-20260910 --archive
python3 -m pytest .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests/test_zero_start_season.py -q
./檢查.sh --quick
./檢查.sh
```

賽果reader已修正平頭名次suffix，所有arm同時使用；上表為修正後數字。新增測試驗證平頭第三仍計上名、退出不算完賽。另固定scheduler測試時鐘，詳見主審計報告。
