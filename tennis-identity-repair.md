# Tennis 身份修補：隔離遷移機制

延續 EXP-20261101-27；完整目標仍是有證據的分析準確度改善。本階段先驗證來源雙側 generation 遷移，不能冒充 live repair 或 accuracy gain。

- [x] 建立只接受 memory SQLite 的研究 API，proposal 綁 raw hash、完整 before-images、target metadata 及版本。
- [x] 驗同一 response 的雙側 closure、來源姓名／tour policy 及 target collision；不認證人物身份或歷史發布時鐘。
- [x] 原子退役雙側、新建帶 supersedes 的 generation，保留實際 observation 時鐘及 append-only receipt。
- [x] 驗冪等、before/after-image 失效停止及 rollback；保留原觀察，不改 live pipeline。
- [x] 用合成反例及 EXP-27 固定來源 pair 做隔離重播，28 targeted tests、quick 及完整 repo checks（Tennis 1093 passed）通過；按未完成研究規則 exact-scope commit／push 自己分支，未 release／接 live。

正式 live apply 仍依賴獨立 provider-ID 身份證明、mapping／fixture 全範圍 closure、歷史 reader clock 合約；大型模型 A/B 仍受 ≥10GB 空間門檻限制。
