# Tennis rank reference：正式交付及原始新 card 核對

2026-11-03；接續[EXP-20261102-06](../experiments/EXP-20261102-06-tennis-rank-reference-contract.md)。**格式修正已交付，模型準確度未證實改善。** 十五個REJECT_DEV、frozen ruler及source qualification規則不變。

## 交付的直接證據

- commit `1011c649b14a649d2427a00d8530b8109205cd7b`，rollback target `348049dc6a7812c4189b9e1683eb0cfec19c999f`。只含原定7檔；未帶入研究generation／capture engine。
- Central immutable candidate full gate exit0，853.938秒；16 suites通過，Tennis **1096 passed／26.95秒**。這是main獨立gate，不冒用研究分支1166項（該分支另含未合併研究測試）。批准時重用同SHA的full receipt並重跑quick gate。
- `approval_granted` 2026-11-02T01:11:03.719144Z，hash `f79c3feac48bce242885ad17cfa10bee489045b21197247a1d64095ef8f44148`。
- `merged` 01:11:05.595616Z，hash `42e1f28f466626367fd65fcdad83ea8f53aaa1feb15611a1667bcaec2b455db3`。
- `activation_succeeded` 01:11:08.176471Z，hash `6ee49b0a6148e36e7ce27eb91deafc5e045f8242b1b444524ee7ac94d2e659de`；只sync Tennis，無installer或Dashboard deploy。Telegram結果已發送。
- release ID：`wc-release:1011c649b14a:2026-11-02T011049.981588_0000`，原manifest位於`~/WongChoiData/WongChoiControl/releases/`，上述events在同根`release-events/`。沒有重寫immutable manifest。

## 已安裝程式的唯讀 smoke

2026-11-03T11:14:48–11:14:50Z，runtime已隨其他改動前進至`710b42974ed5a38f08d59550d0e65392c8f9a535`；`1011c649`仍為ancestor。Tennis feature_builder、data_quality、rank_reference、probability_model及research_evidence五檔與已發佈commit逐byte相同。

只以實際runtime package及production env路徑做診斷，所有257個SQLite connections強制mode=ro／query_only，單句SQL有5秒cooperative deadline。沒有執行run-daily、store_prediction、settlement或ledger寫入。

原三個positive-format controls 22538／22541／22574各有兩份canonical rank references；逆轉annotation位置後，完整pricing及同clock quality皆相同。22616仍為DISPUTED，原guard繼續拒絕。這四個是預先指定的接線smoke，不能當accuracy cohort或forward樣本。

## 部署後的真實凍結 card

原生`inspect_tennis_feature_provenance`於2026-11-03T11:21:56.992483Z唯讀檢查：134個Tennis prediction records，132個bundle完整；qualified cards及predictions仍為0。並非133或134場獨立比賽。

以activation UTC至該as_of為固定範圍，**所有三份**部署後card bundle完整，但都沒有正式feature artifact。直接讀原本保存的diagnostics、核對manifest／status／gzip hashes及原prediction IDs；不從今日DB重建、不移除warning、不挑成功subset。整批原writer replay與原始失敗reason完全相同：

| event／source cutoff UTC | expected／observed | 原有整批攔截 |
|---|---:|---|
| 2026-11-03／2026-11-02T07:26:50.314142 | 0／0 | empty card；coverage不成立，沒有可計forecast |
| 2026-11-03／2026-11-02T22:27:39.628722 | 55／55 | prediction16211：incomplete Tennis component set |
| 2026-11-04／2026-11-03T07:27:45.638202 | 0／0 | empty card；coverage不成立，沒有可計forecast |

唯一非空card保存齊55個observations、55個unique match IDs；65個rank points已是新canonical格式，45個仍保留不合資格／不完整reference的extra欄位，沒有偷偷移除。原始55個component predicates分為28個incomplete與27個active unresolved warnings：

- 28個輸入有一邊或兩邊overall／surface Elo缺失（12個兩邊都缺、16個一邊缺）；同組沒有完整active component set。
- 27個有有效component warning；missing_surface涉及26個，elo_not_as_of／rank_seed_elo涉及11個，可重疊。沒有把warning neutralize來造合格紀錄。

初版診斷script錯誤假定新card必非空，在0／0 card停於assert；原失敗script/log保留。修正診斷為忠實記錄empty/incomplete狀態，仍在writer前拒絕，沒有將empty card或partial observations算合格。

這證明格式修正已在實際保存的輸入生效；它不會補出欠缺的Elo／surface、恢復舊原文，亦未產生新qualified forward。最新canonical prediction仍連到shadow baseline `tennis-pricing:8b149c85aafa`，不是新candidate promotion；baseline migration的0／0 forward欄位亦不代表本研究所需N已完成。

## 證據、限制及下一步

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/rank-reference-release-proof-20261103/`。10個proof／script／log／metadata frame及manifest均唯讀封存、逐檔再驗；manifest SHA256 `baa74c08276187fe794af9e1d920c8bdb1886fa68c48170ca86974dc99582b28`。

沒有匯出原始私人snapshot、價格、raw body、env或credentials；原native report留本機，外置只存hash-bound去路徑metadata projection。smoke原私人輸入只在記憶體；真實三份card的原輸入仍留原本受保護immutable bundle，沒有改寫。

本輪只驗Tennis程式交付／證據，不將其當其他domain營運健康、D1或完整HOT/WARM/COLD審計；release沒有對Dashboard／D1／投注資料做變更。下一步先以55個原輸入及預測前已保存公開資料，分清缺Elo是資料不足、source／identity routing還是衍生cache問題；再核實missing surface來源。不能用調權重、補假值、改窗或放寬qualified條件代替。


2026-11-03接續：[缺 Elo 全量輸入、routing 及真實 TE receipt 審計](tennis-missing-elo-inputs-20261103.md)已完成診斷；結果與下一個固定39-player coverage／identity pilot見該文。沒有回填舊forecast、改whole-card資格或宣稱準確度提升。
