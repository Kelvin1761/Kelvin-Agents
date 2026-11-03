# EXP-20261104-01：先更正header來源審計，再修分類入口

2026-11-04悉尼；所有artifact內時計為UTC。這是獨立來源規格修正，先於候選v2改動保存。**未修改模型ruler、source qualification或live history。** 原十五個REJECT_DEV不變。

## 撤回原版錯誤歸因

[EXP-20261103-14](EXP-20261103-14-tennis-te-draw-tour-coverage.md)原source-shape helper只在head有anchor時更新URL；碰到無連結的`Futures 2026`標題時，沿用上一個賽事URL。故原版「14,325版本都有明示head URL／無unresolved」不成立，不能用舊helper證明來源或actor ownership。原始115檔包不改寫，錯誤、程式及其輸出照保留。

新URL-only候選會在每個head清除舊context，因此4958個generic-header賽果版本被正確留置，四臂比較在「全部應有tour」assert停下。**不能繞過assert、忽略4958個版本或沿用舊URL救候選。** 此候選未驗收，未合併或部署。

## 獨立重驗全部34版本

仍用同一source manifest `ace4fb34d970f1f26c43291052a534216d64efb5d5dbd60b4205525f8d7ba0d1`，不重抓、不換窗或縮小39人範圍。header每次清空URL及icons，雙側只能使用當前head。

| tour實際來源 | 賽果版本 |
|---|---:|
| 當前head的賽事URL | 9,367 |
| 當前無連結head的明示性別icon | 4,958 |
| 合計 | 14,325 |

來源class實際包含`type-men2`、`type-men4`、`type-women2`、`type-women4`。有URL兼上述icon的1857個head，所示男女分類1857／1857一致；85個head沒有link。2／4不拿來推斷單雙打，draw另以雙側`/player/`或`/doubles-team/`namespace核對，並在有賽事URL時核對`?type=double`。

中間審計v2只認men2／women2，正確將其餘895個版本列UNKNOWN；原v2保留。v3加入實際觀察並經已知URL核對的men4／women4四個字面值，未以姓名或前一個head猜測。

重算仍為ATP單打6462、WTA單打5321、ATP雙打1397、WTA雙打1145；tour推斷差異仍6215、單打部分5116。**數字相同不恢復原版URL歸因的有效性。** 這些仍是來源版本數，非獨立比賽、實際入庫或受影響投注數；沒有量準確度。

## 候選v2的事前來源規格

此規格是primary HTML解讀，非統計門檻調整；來源時計及整批qualification一律沿用原把尺：

1. 每個head重設URL、icons與label；無新證據就UNKNOWN。禁止沿用上一個head、從城市／球員名猜tour，或以ATP作預設。
2. URL只接受官方host、已知`atp-men`／`wta-women`路徑與既有query形式。URL及icon同時提供tour時必須一致；URL存在但不合法／不明，不准以icon掩蓋。
3. 只有當前head**沒有URL**而有唯一明示gender時，才可使用上述四個已驗證class值；男→ATP、女→WTA。未知class／男女互相矛盾一律留置。這不是從`Futures`字眼或缺值推斷。
4. 單雙打須有雙側同種類的來源連結；有已知head query時亦須一致。只有性別icon，沒有雙側actor namespace，仍不足以寫history。
5. `tournament_source_url`在icon-only案例必須保持None，另保留`tour_source_kind=header_icon`；URL來源亦明列kind。不捏造URL或具體tournament身份；未知surface／round等限制不因此解除。
6. 須增加真實generic-header形狀、前WTA→generic男、男／女2／4、head不帶證據、URL與icon矛盾、mixed actor refs等正反例。既有score parsing／結果API完整facts必須不變。
7. 用同一34版本重跑C／D／T／DT，保留所有rows與holds。原分類層預期數字維持，但**必須由新source-spec及全部facts比較真正驗證**；不是用舊failed matrix當成功。
8. identity／old-history碰撞、雙側transaction與source clock guards仍須通過；不能因此合併39個UNKNOWN tour目標或回填舊forward。驗收後另跑完整gate，才可考慮交付入口修正。

## 現有程式狀態及證據

獨立worktree `codex-tennis-te-source-classification-20261104`的URL-only研究候選已加optional metadata、history分流、未知／相反target tour留置、雙側savepoint及old-history collision guard。47項針對測試、Tennis1115項通過，但真實source矩陣未過，**不是已完成候選**。

完整repo檢查在新source-spec發現後已明確取消，terminal143；不當成full pass。只停止已驗證cwd屬此worktree的程序，沒有操作其他session。新候選改動後必須重跑full，不能重用此取消紀錄。live history／cache／模型、正式ruler與原prediction均未寫入。

新證據包：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/header-source-correction-v1-20261104/`。24檔／2,185,051 bytes唯讀封存；manifest SHA256 **`2f43fd88007c59775c8d5644cc2500c474faeca5a322a0994ff1f4c75652e609`**。

包內有failed URL-only matrix／4958-row診斷、兩版獨立source audit、v1候選實際四檔source、47／1115測試及取消full log。parser SHA256 `0fec5c7d7f791503eaeae2f76b3c5b487d955674f907a83b1026655ce39a4e57`綁定失敗比較；後續候選不得冒用此SHA的測試。原115檔原文包、offline parity及其錯誤helper皆保留，不改寫歷史證據。

整體目標仍未完成：這次更正來源審計，沒有新增合格forward，沒有證明分析準確度提升。其他book歷史資料的training-only及Sportsbet獨立forward要求不變。
