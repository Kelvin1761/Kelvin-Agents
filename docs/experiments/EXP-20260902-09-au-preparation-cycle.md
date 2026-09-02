# EXP-20260902-09 — 久休復出與休後第二仗

## 預先登記

用戶再次提出 2026-08-22 Randwick R1 Gunroom。已讀 EXP-20260824-01/02：
Gunroom 當日距上仗 14 日，但上仗之前休 239 日。固定扣分／按名次降級已失敗，
不重搜舊門檻。Bacetti 則是 154 日後首仗，兩種週期須分開。

先作可獨立驗證的資料／敘事修正：按目標日前正式賽日期，識別休後第一／第二／
第三仗，記錄休賽空窗與本輪已跑場數。試閘不得重設正式賽休賽日數；未有日期不猜。
沿用目前 health 的 >90 日作久休顯示定義，不新搜門檻。

另外固定研究假設：首仗／第二仗／第三仗期間，近四場中的休前資料仍有歷史能力
資訊，但未在本輪全部確認。把休前證據的可信程度定為原來一半；對每個 component
用 `reliability = 1 - 0.5 * 休前證據權重比例`，計
`60 + reliability * (原component - 60)`，同時收縮正負偏離，不直接扣總分或改名次。
FORM、PQ、FORM+PQ 三個固定 ablation；不搜 0.5 或 90 日。只有有實際久休邊界
或直接距上仗 >90 日才觸發；日期不足不觸發。新一輪跑滿四場，不再受本候選影響。

沿用 EXP-06 1822 場／18216 匹鎖定語料、同一 dev/terminal 切法與 baseline；
先 dev，任一 primary 回歸便不開該候選 terminal。Gunroom 位於已曝光 terminal，
只作機制個案，不聲稱 pristine holdout；Bacetti 不在 corpus。正式候選須 current
evaluation contract；失敗模型不採用。預先分組：馬群大小、首仗、二仗、三仗。

這是 component 可信程度研究，不把長休等同傷患，也不把試閘有跑直接當作狀態好。
若無候選過閘，仍交付可重現的週期識別及風險說明，不聲稱排名已改善。

建立語料時的資料契約核對（未讀 ablation 結果）：FORM 只數實際有名次、會入分的
原始近四仗，保留跳過缺名次後的原位置權重；PQ 必須有自己的 dated runs，不能把
consistency fallback 的分數冒認為有完整 PQ 日期。日期不足時不作可信程度收縮。

## 結果：三個評分候選均拒絕

固定 corpus 共 1822 場／18216 匹，先讀 1310 場 dev，512 場 terminal **本次未開**。
以下是相對 baseline 的百分點差，無重新調參或另挑窗口：

| 固定干預 | dev Gold | dev Good |
|---|---:|---:|
| F：只降低休前近績的可信程度 | -0.8410 | -0.1529 |
| Q：只降低休前 PQ 的可信程度 | +0.1529 | -0.3823 |
| FQ：兩者同時處理 | -0.5352 | -0.4587 |

全部至少一項 primary 退步，沒有候選進入 terminal。分組檢驗不會救回已失敗候選，
故本次亦不再展開分組選優。收縮程式只保留於 scratch 實驗腳本，不留在 production
engine；沒有新增長休扣分、總分修正或排名特例。這不證明長休沒有影響，只表示
此固定編碼未能改善既有模型。

整批日期識別：首仗 2427、二仗 2302、三仗 2044、本輪四仗或以上 5405、
unknown 6038。unknown 只代表現有正式賽日期不足以定位久休邊界，不推論狀態正常。

## 保留的正確性修正

- 從嚴格早於目標賽日的正式賽日期識別週期，排除試閘、重複日、未來／無效日期。
- `preparation_cycle` 保存 as-of、休賽日數、本輪已跑場數、復出日期和證據日期。
  正式名次缺失時保持未知，不能從輸距或舊 `-` token 發明名次。
- 引擎核心分析、備戰說明、報告總覽及矩陣事實段共用同一週期。
- 評分、權重、grade、排名仍沿用原式；六個測試包含逐項 feature／ability 不變。

Gunroom：2025-12-12 → 2026-08-08 相隔 **239 日**；08-08 → 08-22 相隔
**14 日**，所以是休後第二仗。154 日是 Bacetti 的 04-01 → 09-02 首仗。
[Racing NSW 08-08 官方賽果](https://mdata.racingnsw.com.au/FreeFields/Results.aspx?Key=2026Aug08,NSW,Kembla+Grange)
確認 Gunroom 當日 4/8、輸 1.5L。08-22 原始賽前模型排名第一、實際第九，見
EXP-20260824-01 的 immutable prediction 記錄；不以不完整 archived Logic
重算出來的排名聲稱已解決 Gunroom。

## 重現與限制

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_preparation_cycle_20260902.py build
PYTHONDONTWRITEBYTECODE=1 python3 scratch/au_preparation_cycle_20260902.py dev
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest .agents/skills/au_racing/au_wong_choi_auto/tests/test_preparation_cycle.py -q
```

評分 baseline 為 `/tmp/au-feedback-main-final` 的 EXP-06 候選（main parent
`926eac54de7f67f78a8f6f7a5c3632a7d95b0cce`）；同 EXP-06 鎖定資料
`/tmp/au-matrix-feedback-after.json`，SHA256
`495b9d439a59981bf46813822d36406206d29712a96a2790300a0e340fe7f31a`。
結果詳見 `EXP-20260902-09-evidence.json`。08-05 前 archive 有賽後重建限制，
Gunroom 所在 terminal 亦曾曝光，不聲稱此語料是 pristine holdout。

本機修正待發佈；之前 public push 自動批准審查仍未獲用戶所需的明確公開授權。
沒有 commit／push／merge，也沒有啟用於 production automation。

## 獨立版本驗證（2026-09-03）

`/tmp/au-preparation-release`，main parent `926eac54`，只含週期識別／解說修正。
六個專項測試、`./檢查.sh --quick`、`./檢查.sh` 全部通過；AU suite 579 項，
其餘九個 suite 亦通過。120 匹 AU golden 分數全部不變。
本機資料合約與生成說明已更新。11 檔 exact-scope Central dry-run 成功，
分類 code、full gate、需批准後 merge／activate；沒有實際 commit／push。
日誌 `/tmp/au-prep-release-{quick,full}.log`；scope `/tmp/au-preparation-release-scope.json`。

## 整合發佈版本

`/tmp/au-feedback-release-20260903` 合併 EXP-06 C、EXP-08 定磅識別、
本次純週期修正；25 個專項測試、quick 及完整十個 suite 全綠。
已保留 main `926eac54` 原始 golden，檔案為
`EXP-20260903-au-pre-feedback-golden.json`。另外用其完全相同的 120 組輸入核對：
ability／grade 無變，115 組只有不入排名的 form_line 解說矩陣改動。
新 record 因語料新增而換了抽樣，不能把「新 120 組通過」當成舊樣本無變；
舊樣本逐項比較的證據另存於本實驗 evidence。Golden 不涵蓋原始資料抽取，
馬群大小／定磅的實际排名評估仍以 EXP-06／08 的鎖定語料為準。
完整日誌 `/tmp/au-feedback-release-20260903-full.log`。尚未 commit／push。

最新候選已接上 main `165f923a`（新增 Dashboard 更新，評分來源不變）：
`/tmp/au-feedback-ready-20260903`。quick／full 再次全部通過，十個 suite 全綠，
598 項 AU 測試通過；26 檔 Central dry-run 通過。公開發佈仍等待用戶明確授權，
沒有 commit／push／merge／activation。
