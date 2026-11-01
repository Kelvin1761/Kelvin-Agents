# EXP-20261102-02：身份修正後 Elo cache 重播

工程診斷；沒有修改 live DB、正式評分或下注政策，亦沒有測 LL／Brier／accuracy／ROI。接續 [統一計劃](../../tennis-research-execution-plan-20261028.md) 的身份及 Elo lineage 工作。

## 事前固定範圍

固定 main `f0c7f36d1faa80465a2b293bb98834d360499a5c` 的實際 `build_sackmann_elo`，保持 production legacy pre-match 計算與 shadow v2 分離。候選只是假設將 history IDs `24211,24212,29943,29944,29983,29984,204373,204374` 內的 Christian 身份由2110改成19626；沒有移動其他history／fixture，沒有把這個 SQL 當成有效正式修復，canonical event key／mapping／availability 均未完整處理。

原始 public normalized cluster 90 perspectives／45 events，42名players；從 frozen DB 只讀補齊公開對手名稱，初始 current Elo／排名為空。原始來源 raw ID 是歷史引用，沒有複製其原文，不能因此追認來源或 PIT 資格。隔離 DB 使用全新路徑並 assert DATABASE_URL，來源 capture 不變。

## Cluster 結果

| 輸出 | 未修正 cold → 修正 warm | 修正 warm → 同輸入 cold |
|---|---|---|
| legacy cache | 102→110；原102 key全保留，新8 | 110→102；移除8，47個共同key值不同 |
| shadow v2 | 102→102；加8／移8，90共同key不同 | 全部102相同 |
| current players | 42中41值不同 | 全部42相同 |
| history opponent Elo | 90中49值不同 | 全部90相同 |

這證明相同已修正輸入在 warm／cold legacy cache 下可返回不同值，且殘留舊身份key。它沒有量度全量 live 影響或預測效果。builder 的 v2 102次寫入在本例也是102唯一key；不能一般化假設寫入次數等於最終rows。

## 全 frozen provider 對照

完整 frozen DB SHA `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`；三個 Elo eligible providers 共401046 perspectives／20372 players，builder實際處理200389個ACTIVE winner rows。逐一核對八行的身份／來源／日期／場地／勝負／ACTIVE／source reference 與既有proposal相同。排除fixture、market、prediction、ledger及所有原始私有payload。

不修正資料重跑的warm control，legacy／v2／current players／history opponent Elo四個完整投影全部與cold baseline相同。八行假設身份修正後：

| 輸出 | 未修正cold → 修正warm | 修正warm → 同輸入cold |
|---|---|---|
| legacy cache | 391099→391107；原391099 key及值全保留，新8 | 移除8，313739共同key的rating或match count不同 |
| shadow v2 | 加8／移8；335262共同key不同 | 391099 rows全相同 |
| current players | 20372中5542的overall／surface欄位不同 | 全相同 |
| history opponent Elo | 401046中328594值不同 | 全相同 |

每輪v2 summary的560330次寫入，最終都是391099個唯一key；沒有把寫入次數當成rows。上述精確差異數包含微小數值傳播，不能當成受害prediction數、顯著差異或模型進步。

外置碟v1在不修正的warm control中因隨機寫入緩慢而以SIGINT中斷（exit130），原protocol／baseline／script及interruption紀錄全部保留，沒有完成四臂結果。v2只把約252MB工作DB移至本機SSD（開始有21GB空間），完成後複製外置碟並刪工作DB；固定input、四臂及判定完全相同。v2四臂完整通過，不用未完成的v1取代結果。

## 差值幅度與驗證

完成後另做純描述性差幅盤點，沒有改候選判定或新增performance gate。修正warm對修正cold的391099個共同legacy rating，中位絕對差約0.000064 Elo、95百分位約0.00638；1398個key大於0.1、175個大於1、34個大於10，最大27.87048。即大部分精確差異很小，不能用313739直接描述實際預測損害。比較未修正cold與修正cold的共同overall player rating，5528個非零差異中只有4個大於1，最大9.156；5542是overall或surface整行差異數，兩者口徑不同。

`identity-elo-cache-magnitudes-v1/`保留描述protocol、result及script，manifest SHA `dc8538103e5bcd8cd9e23be5b9140d1ffb9c26808b3fe71f824fb2261653e80d`。新身份key、被移除key及NULL不能拿來做數值差，另按row-flow報告；沒有用差幅門檻挑資料。

以本輪起點`f0c7f36d`跑repo `./檢查.sh` exit0；16個suite全部通過，unit suites869秒，Tennis1080 passed（24.92秒）。交付前快進至`23380430`（其他session的儲存維護改動），Tennis計算source未變；docs exact-scope另跑release quick gate。本輪repo只有四份研究／計劃文件改動，local links及`git diff --check`通過。上述是工程驗證，沒有正式資料apply或模型promotion。

## 獨立官方身份證據補充

本輪另行擷取[丹麥網球總會 Davis Cup 頁面](https://tennis.dk/nyheder-presse/davis-cup/)，actual fetch `2026-11-01T14:29:25.314231+00:00`，HTTP200、110945 bytes、body SHA `078ec42f332c9b692c5301485f3ff9978d1ed194121fb8704c084ad585bfcd88`。頁面姓名旁列出生日期1997-03-14，三場 Davis Cup 對手、勝負及比分與本輪待修的 Jeff 三場相符：2021對Wishaya勝，2022對Ramkumar負、對Marcelo Arévalo負。這補強獨立人名／賽事證據，並不建立該資訊在舊決策前已知的時間，也沒有自動證明內部19626的完整registry／alias合約。

ITF `800337251` profile 在 web reader 有姓名及國家，但直接HTTP擷取雖返回200，只有212 bytes的Incapsula challenge、沒有球員內容。保留失敗body，**不將HTTP200當成成功profile receipt**；不從動態年齡反推出生日期。[ATP Tallahassee 2025 archive](https://www.atptour.com/en/scores/archive/tallahassee/692/2025/results)的web reader另見R32 Nava勝Sigsgaard、兩盤6-4，並連到SY00；直接HTTP擷取返回403，因此仍未有這頁的成功原文receipt，不把web展示等同已保存HTTP來源。frozen history這場日期為2025-04-14（賽事起始日），未當成精確開賽時計；target registry／alias合約仍待完成。

原件在 `official-identity-v2/`，含事前protocol、兩份HTTP body gzip／實際時間／hash／normalized flags、執行script及manifest；manifest SHA `3ad640c2da7f59ba015669111454f85ca9520feee7296f95f899884b35d8bd13`。另存`official-tallahassee-v1/`的403失敗紀錄及script，manifest SHA `c0a416080d2efd0d46bc9cf788f95a0ffdc6acca17a5706f293f47c7d8370773`。初次兩輪在import時因缺requests／bs4停止，沒有連線或建立artifact；最終使用標準庫，未安裝套件或繞過challenge。這些原文是本輪才保存，沒有倒填歷史fetch時間。

## 證據及後續

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `identity-elo-cache-v1/`：事前 protocol、只含公開欄位的 projection、isolated SQLite、三臂逐項輸出、result、source.py；manifest SHA `932e0e7b19d1b535243668a9e1e3c9c1609040fa92dcedb8f5feae174f6156b4`。
- `identity-elo-cache-full-v1/`：中斷紀錄及第一輪baseline；`identity-elo-cache-full-v2/`：完整四臂、unchanged control、DB／projection／result／source及manifest，SHA `aad58231f91ec580360ea13bcf7899c6bd122caa7f6253ba8f6495eaed3c3151`。
- 指令：在上述 code SHA 的 repo root，以 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <artifact>/source.py` 執行；重播要改成全新 OUT，原目錄存在會拒絕。原 script 亦在 `/private/tmp/tennis-identity-elo-cache-20261102.py` 、`tennis-identity-elo-cache-full-20261102.py`及`tennis-identity-elo-cache-full-v2-20261102.py`。

下一步依 [generation 執行合約](../plans/tennis-identity-elo-generation-20261102.md) 實作隔離版，再驗證完整來源、歷史知悉時間及四條衍生輸出。單加 history availability guard 不足。十五個 REJECT_DEV、frozen ruler 及 v2 shadow 判決均維持。
