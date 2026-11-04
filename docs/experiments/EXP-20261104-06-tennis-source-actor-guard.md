# EXP-20261104-06：來源 actor namespace 隔離對照

2026-11-04。**RESEARCH_ONLY／NOT_DEPLOY_READY**。這是輸入身份實驗，沒有量度預測準確度、批准 binding、寫正式庫或新增合格 forward。候選保存在 `codex-tennis-source-owner-guard-20261104`，不走模型 release。

## 假設及固定範圍

承接 EXP-04 的 Shaurya／Siddharth 反例及 EXP-05 的兩人 proposal：TE actor URL 必須先於全域姓名 alias；沒有來源 binding 的既有球員不能單靠首字母接入。事前協議 SHA256 `44ffab0f366d5420f2e5d848d31137584489129f524c51b5b3db9658163d6a66`；baseline 為 `8e940e157ca802fdf14b131b2060b270f0c3b2de`。

四臂使用同一份來源封存、原全39人及2026-10-01至11-02的33個完整 calendar days；14249個 parsed 版本、316個 parse skipped。原34版 parser 比較沒有刪改，只在按日入庫沿用既定完整日版本，不使用同日尚未完成的額外版本。沒有私人 fixture／odds／finance DB 複製；book tour 只用前輪已封存的21個公開 ID／分類 flags。

| 臂 | 入口及種子 | 入庫賽事 | 雙側 history 行 | 留置版本 | 錯接21144行 | 原39人 history 行 |
|---|---|---:|---:|---:|---:|---:|
| C0 | 原 writer、原 UNKNOWN tour | 11356 | 22712 | 2893 | 0 | 0 |
| C1 | 原 writer、21人明示 tour | 11405 | 22810 | 2844 | 6 | 51 |
| C2 | source actor writer、同21人 tour | 11559 | 23118 | 2690 | 0 | 0 |
| C3 | C2＋兩個未批准 proposal，僅隔離 shadow | 11570 | 23140 | 2679 | 0 | 11 |

每臂均滿足 `accepted + held = 14249`、每場兩行及一勝一負，SQLite quick_check 通過。C2／C3的 history 全有 source binding，私人業務表全空；每臂 metadata／DB hash 保存後刪除該臂 public native DB，沒有同時保留多份語料。C3的11行為21247九行、1865兩行，**不是兩人已獲批准或原card已合格**。

C2仍留置95個 unknown tour、2537個雙打、49個 unbound actor、7個 source label conflict、2個 fixture ambiguity；C3只有 unbound actor 降至38。未將未知或衝突強行補值。C2接受更多來源行涉及不同 actor key 的同名分離，不能從行數增長推論身份全對或模型更準。

## 候選行為及限制

只接受官方 HTTPS `/player/.../` actor URL，正規化尾斜線。來源 key 唯一、目標存在且未 merge、明示 tour 相符、binding clocks 有效及不在未來，才核對已選 actor 的 display label。首字母只可驗 label，不可選全域 owner；完整姓名矛盾留置。新來源 actor 及 binding 與雙側 history 同一 savepoint，不新增全域姓名 alias。不同已綁 TE actor 可以有同名 display label。

**此路徑不能直接部署。** 正式庫唯讀盤點：TE來源 actor binding為0；既有 TE history有244088行、19189位球員、304個 calendar dates（2026-01-01至11-02）。新 guard 放進舊庫會令未綁定的合法舊目標亦留置。隔離 fresh DB 通過不代表既有資料遷移安全。

目前事件 reference 仍沿用既有日期／姓名規則；未完成穩定 event ID 圖、舊混合身份 reconciliation、generation 原子切換及四份 Elo 衍生輸出一致性。不可只清 cache、補兩個 mapping 或推這個 guard 代替整體修補。沿用原 [generation 合約](../plans/tennis-identity-elo-generation-20261102.md)，Sigsgaard 原四場／八行假設不被兩人 proposal 取代。

## 驗證及保留失敗

新增17個身份測試，連既有入庫測試共80項通過；quick 全綠；`./檢查.sh` terminal exit0，全 suite 通過，Tennis1156，總測試段936秒。測試覆蓋來源 binding 優先、首字母反例、相同全名不足以跨來源綁定、clock／merge／key碰撞、同名不同 actor及雙側交易。

初版測試的 Python3.9 annotation／schema／fixture 前置條件及姓名順序錯誤都有原 red logs；沒有把失敗當通過。矩陣v1因 harness 誤用不存在的 `get_settings.cache_clear` 在入庫前停止；v2只移除此呼叫，未換輸入／候選／判準。v1保留為不完整失敗。

## 證據及下一步

外置共同根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `source-actor-guard-protocol-v1-20261104/`：事前協議、baseline及初版red證據。
- `source-actor-guard-ablation-v1-20261104/`：未完成 harness 失敗，不能計結果。
- `source-actor-guard-ablation-v2-20261104/`：20個payload檔／267040 bytes，manifest SHA256 `a13179f8cf1489a98800134e3f1a9d8bbc597db4f87863896f896808f22e55e1`；含固定程式、四臂逐日結果及完整gate log。

下一步按全部304個既有 calendar dates重建公開來源證據，再核對穩定 actor／event keys及 legacy beforeimages。這是新遷移研究，**不擴大或替換上述33日實驗及原模型評估窗**。新取得來源的 knowledge clock 保持實際取得時間，不倒填至舊預測前。15個 REJECT_DEV、frozen tennis-v1 及 Sportsbet 獨立 forward 要求不變。
