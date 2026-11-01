# Tennis 身份修補：隔離遷移機制

延續 EXP-20261101-27；完整目標仍是有證據的分析準確度改善。本階段先驗證來源雙側 generation 遷移，不能冒充 live repair 或 accuracy gain。

- [x] 建立只接受 memory SQLite 的研究 API，proposal 綁 raw hash、完整 before-images、target metadata 及版本。
- [x] 驗同一 response 的雙側 closure、來源姓名／tour policy 及 target collision；不認證人物身份或歷史發布時鐘。
- [x] 原子退役雙側、新建帶 supersedes 的 generation，保留實際 observation 時鐘及 append-only receipt。
- [x] 驗冪等、before/after-image 失效停止及 rollback；保留原觀察，不改 live pipeline。
- [x] 用合成反例及 EXP-27 固定來源 pair 做隔離重播，28 targeted tests、quick 及完整 repo checks（Tennis 1093 passed）通過；按未完成研究規則 exact-scope commit／push 自己分支，未 release／接 live。

正式 live apply 仍依賴獨立 provider-ID 身份證明、mapping／fixture 全範圍 closure、歷史 reader clock 合約；大型模型 A/B 仍受 ≥10GB 空間門檻限制。

## 接續：recorded history clock（EXP-20261101-29）

- [x] 新增獨立 research projector，只採 cutoff 前 immutable after-images，不填今日可變欄位。
- [x] 28 新測試及原 pair apply／rollback 均阻止倒填2025；所有424823 IDs／6515 observations完整盤點。
- [x] 明列4980 recorded snapshots不等於runtime parity；130 hold rows全Challenger，main-tour serve資格未補足；132 opponent Elo drift保留原值。
- [x] 完整 repo gate通過（Tennis 1121 passed），連同測試／證據 exact-scope保存研究分支，未接live。

開工free已約16GiB，上一階段磁碟阻擋不再適用；資料／身份／prediction lineage閘保持。新的當下snapshot只能支援未來可用性，不能回填歷史資格。

下一步身份線索：`primary-identity-bridge-v1/`保存UTS `playerProfile?playerId=44614` 的 Christian Sigsgaard／DEN header，對上target19626的`composite/uts:44614`；ATP SY00頁可讀姓名但直接DOB等欄位仍動態placeholder，Jumpei H2H直接頁大部分亦是placeholder。這是部分獨立namespace／name證據，不是完整DOB、mapping／fixture closure或live apply授權；勿將搜尋節錄當完整原文。

EXP-20261101-44已建立四個Christian來源pair／八視角＋兩個mapping的review-only proposal；五個fixtures的match scope有10 predictions／26 feature snapshots，未判受污染／改寫。78行TE查證暴露原文缺口，完整240146行TE的來源232766空、7380僅summary；現行runtime ingester相同。**下一步先修未來按日HTML／fetch時計保存及parse-failure留證，不能用重抓追認舊來源**，再完成persistent identity clock／collision／derived Elo遷移。原live fixture原文匯出被auto-review拒絕，安全替代只存引用counts／IDs／hashes，已完成彙總。

2026-11-02接續：未來TE history按日原文保存已由獨立fresh-main worktree交付41cad292（main full gate Tennis1080，runtime source bytes相同）。報告EXP-20261102-01從已合併f0c7f36d原件同步到本研究筆記；本研究分支的未完成identity／clock工具未隨該release發佈。實際首批新receipt仍待run驗證，舊summary不追認。

`christian-fixture-label-audit-v1/`再以in-memory normalized DTO檢查五個fixture的exact event ID及兩方姓名欄，5/5有完整Jumpei標籤支持；只輸出分類／hash，沒有原文／價格／注碼匯出。此結果支持保持fixture IDs而非整體rename為Christian，但不是原HTTP回應身份、報價有效性或完整人物認證。下一步回到四個source pairs的persistent availability／collision與衍生Elo遷移，不改寫舊predictions／ledger。
