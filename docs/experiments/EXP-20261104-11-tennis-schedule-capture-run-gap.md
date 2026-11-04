# EXP-20261104-11 賽程捕捉與排程中斷

官方仁川Order of Play在瀏覽器要求驗證，未能讀到逐場賽程。韓國網球協會日曆原文成功保存，確認仁川W100舉行範圍為11月1至8日，包括資格賽。[官方逐場賽程](https://www.world.tennis/en/tournament/w100-incheon/kor/2026/w-itf-kor-2026-007/order-of-play/) · [韓國網球協會日曆](https://www.kortennis.or.kr/cmpt/91/cmptList.do)

次級公開賽程於2026-11-04T06:04:44Z捕捉，HTTP 200／33345 bytes。13行的UTC欄及機器可讀時間一致，首爾時間換算亦逐行吻合。3場單打及4場雙打的預定時間晚於捕捉時計，另6場已過預定時間或標示live。球員仍是縮寫，屬預定時間。原11月3日7場對陣沒有從此新快照補回。首次腳本命名`inspect.py`遮蓋標準庫，重新命名後通過同一原文核對。[次級公開賽程](https://livetennisapi.com/tools/match-time/w100-incheon)

唯讀檢查當時11月4及5日ACTIVE Sportsbet fixture均為0。11月4日09:00卡的attempt-1 manifest自22:00:05 UTC維持running，無terminal時計及operation，兩次復原記錄`duplicate_active`。核對時launchd三個相關job均未運行，未找到已知runner或tennis CLI程序，對應run lock可取得及立即釋放。這證明核對當刻無鎖持有人，進程中斷原因仍待查。

用實際manifest的唯讀複本重播原生 `_next_request`，`--force` 在running時停在attempt 1，在隔離複本合法轉failed後才選attempt 2。現役manifest雜湊前後一致。下一步須建立可查證的中斷收尾程序，在保護同一run lock及檢查子程序後才可結束舊attempt。及時賽前入庫恢復後，再驗全卡對陣、身份、場地及時間。

外置證據 `incheon-schedule-run-gap-v1-20261104/`，manifest SHA256 `05b1ba74c062f0fcdcfae55a36f46ca945cf68dfad0e142e76f8bc24ea549a1e`。新增合格單打0，正式寫入0。
