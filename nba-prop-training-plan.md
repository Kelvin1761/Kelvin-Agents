# NBA prop training evidence

目標：讓逐prop挑戰模型能公平對C驗證；未有證據不替換主模型。

- [x] 凍結baseline、來源與label隔離協議。
- [x] normal snapshot按腿保存hash-bound prop inputs及80/80資格。
- [x] 最新published pretip資料與獨立Final targets匯出、保留原始ledger bytes。
- [x] 既有daily evaluation列逐prop樣本及缺來源狀態。
- [x] 正常接線、時間／身份／缺失、C metrics parity及全NBA測試。

exact-scope full release gate與正式runtime核對結果：見證據根Final_Verification.json。

Live forward資料、候選fit／消融、未見對C比較及SGM確認屬之後研究階段，不因工程完成標為已做到。
