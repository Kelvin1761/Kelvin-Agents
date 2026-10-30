# Tennis card 賽事配對衝突診斷

2026-10-30 澳洲悉尼時間，Tennis card 的 09:00 run 和 10:30 recovery 均在當日排名來源修正部署**之前**結束，分別處理 51 和 48 個有效 feature snapshot，但完整性閘因 fixture `22294` 已是 `DISPUTED` 而擋住完整報告／dashboard。兩次 run 亦記錄 ATP／WTA 排名、低級別歷史及 slate integrity 來源錯誤；當時的 WTA 發球模型資料已有 165 日，屬另一項未解決限制。新排名修正於其後部署，不能推斷這次 card 已被修好。

該 fixture 的已保存原始建立紀錄顯示 `Sijia Wei` 對 `Priska Madelyn Nugroho`；同一 Sportsbet event ID 的衝突 odds 資料寫作 `Sijia Wei` 對 `Priska Nugroho`。現役 `_pair_matches` 對兩邊姓名做正規化後要求完全相同，因而記錄 `EVENT_PAIR_CONFLICT`。WTA 和 ITF 分別有 [Priska Nugroho](https://www.wtatennis.com/players/328797/priska-nugroho/matches) 及 [Priska Madelyn Nugroho](https://www.itftennis.com/en/players/priska-madelyn-nugroho/800451820/ina/wt/S/overview/) 官方球員頁；這是核實線索，不單憑姓名聲稱不同來源必然指同一人。

對 live SQLite 開啟單一**只讀 transaction**，取出全部 44 筆 retained `EVENT_PAIR_CONFLICT` 觀察及各自先前的 `CREATED` 記錄，完整原文與腳本保存於外置 `WongChoi-Archive/scratch/tennis-unified-20261028/fixture-conflict-diagnostic-20261030/`；案例資料 SHA-256 `d865b32dc494579bb79812eabd1f7ead3cc2251f49014f52a0c595f84fb3778e`。44 筆均找到建立記錄；只有兩筆建立記錄和 incoming odds 的 event ID 相同。事後描述性比對發現這兩筆均是一邊姓名完全相同，另一邊可由保序省略中間名得到；其餘 42 筆 event ID 不同，不能一概以名字簡寫解釋。

沒有修改 live DB、解除爭議或放寬配對規則。這是事後診斷，並非已驗證的身份、模型表現或正式消融。後續若要修復，先核對來源原文及球員 identifiers，對完整同類語料預先登記正反例、事件重用／同名及對調兩邊的測試，避免將不同賽事的價格連到同一預測；已有爭議紀錄要另行備份及逐項處理。當日 card 仍以實際 run 狀態為準，不能把部署完成當成 card 已恢復。
