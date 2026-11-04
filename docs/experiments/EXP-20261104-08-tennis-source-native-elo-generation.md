# EXP-20261104-08 Tennis 來源身份群組及 Elo 重建

2026-11-04。接續 EXP-07 全量來源核對，使用同一批304日原文及全部244088行舊資料的公開欄位。結果屬研究分支的隔離重建。來源資格、身份批准、整批賽前樣本及模型準確度仍待驗證。[EXP-07](EXP-20261104-07-tennis-legacy-source-reconstruction.md)

舊ID與來源actor連結共有12363個連通群組。其中11474個呈一對一，889個涉及多對一、一對多或多對多，合計1382個舊ID及1569個來源actor refs。最大群組由一個舊ID連到13個refs。這是來源連結盤點，跨來源真人身份須另核實。

28行配對異常屬2026-08-08同日的9個舊reference，各對到一個公開event。8組有3行，1組有4行。三行組可見舊全名與縮寫ID分開指向同一來源actor。四行組來自雙打，同一來源組合在舊資料亦曾連到個人ID。原9組及28行完整保留，批准mapping為0。

## 重建方法

固定全部123098個來源版本。維持原圖留置，另外留置同日同actor pair多個event及原生姓名排序key碰撞。新增8個留置版本，兩種原因分別涉及6及4個版本，其中2個重疊。投影得101527場及13198個來源actor，合計留置21571個版本。actor URI以可重現的獨立ID儲存，保留比賽來源URL、原文hash及實際抓取時間。

沿用現有原生Elo builder、初值1500、K衰減及同日排序。研究庫把不具備的賽事分類欄明示為UNKNOWN，場地留空。所需raw ID只連向本機投影metadata，原文來源從逐場lineage追溯。資料庫連線僅限當前隔離研究檔案。

v1在載入`init_db`時失敗。v2與v3分別在必填tour與history欄位停下，均早於Elo計算。修正schema後以同一批來源、排序、公式及驗收規則重跑。v4事前協議SHA256 `c00b951cc47eea0023ae0059ab8141f55c59f13acdce7d4ae2f2b1312de60e51`。

本次checkpoint時v4仍在運行，第一個隔離庫已進入 SQLite `quick_check`，程序採樣顯示正在讀取外置碟。完整驗收以兩次冷建置的terminal結果及四份邏輯hash為準。下一個實驗會用封存時計核對兩個尚未批准的來源actor proposal，保持原39人完整分母。正式來源資格與Sportsbet獨立forward另外驗證。

## 封存

共同根目錄為 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

- `te-legacy-cluster-closure-v1-20261104/` manifest `fe1de4ee21cd4ec069e61e9d9afb51d075faa9ee6501f699c11921b6b47a80ca`。
- `te-source-native-generation-v1-20261104/` manifest `02f457cdd1bf096cb70c180f314a7e8075d83e7c52c1e0302b7d8cb356fac546`。
- `te-source-native-generation-v2-20261104/` manifest `fe746b95c3b52ad8b17d62d6fcbef5dce238afa7ca178d64b894ebe47c4bdc13`。
- `te-source-native-generation-v3-20261104/` manifest `4ae2ee1b718463dd9573331eacbadd748732b9c5d6267efe5447d26c5539ac9b`。
- `te-source-native-generation-v4-20261104/` 正在執行，包含固定協議、原生程式hash、全部留置版本及actor registry。等待terminal結果後再封存。
