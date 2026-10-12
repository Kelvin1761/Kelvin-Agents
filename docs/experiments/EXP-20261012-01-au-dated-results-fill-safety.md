# AU CSV 補值修訂與實際 CLI 驗收

狀態：**CORRECTNESS／REPAIR DIAGNOSTIC；G2仍PARTIAL**。凍結 baseline commit 0328f13a9564c787837e3c4aa1cfff19235c9b0c。沒有模型績效判決、候選 WIN、production apply、commit 或 release。

舊 `build_fill_map` 只用日期／場次／馬名，跨馬場會撞 key；`fill_missing` 又會改寫現有 Barrier 及整數格式；`--fill-missing --sb-csv` 直接進 legacy branch，實際忽略 --sb-csv。8 個最初案例在舊版本 5 failed／3 passed，失敗記錄保留 `results_fill_before.log`。新案例另覆蓋 venue／日期矛盾、衝突保留、raw draw語義、報告目的地、來源hash、mandatory lineage、dry-run／backup／idempotence。43 scoped tests PASS，見 `results_fill_dated_scoped.log`。

Legacy Logic metadata 路徑按 reflector exact header date／venue綁定，不用folder alias猜馬場。衝突欄位不按first file勝出；已有值完全保留。stored Logic barrier 可能已被 serving densify，故不拿它填原始 draw，也不在 fill時densify result CSV。Legacy corpus copy34410列保留所有非空值、Barrier、identity／order，Weight及Distance各14170 fills，14554 conflicts、550 flags；不是完整資料清理或PIT PASS。

`au_dated_results_repair.py` 整合已保留研究版v2的純repair；actual CLI `--fill-missing --sb-csv --sb-lineage` 強制lineage與來源hash一致。資料三問／source projection correctness仍由獨立來源審計負責，hash匹配不證明欄位真值或歷史available-at。只補 exact dated-run 同身份同 Pos 的空值；Trainer、runner Time、WinningTime及市場欄位不新造。

實際frozen CSV研究副本34410列：Margin18944、Jockey18354、Barrier15551、Weight15551、Distance15551，合計83951 fills；20880 conflicts保留、80非exact track source旗標隔離；2281 source inputs校驗。dry-run不改CSV，apply備份逐byte一致，第二次apply零changes；所有原有非placeholder值、identity／order／count保持，與舊v2 repaired CSV非市場欄位完全相同。

原CSV SHA256 94cd1d7acea4d03ed75927f0893dd6c643c61a28e07b9552483a7e14a3b0c296；CLI副本 fc77778ba91ce03c4bb9da1fc49d62969e4797cdf1642050b7f4d755b0176a15。完整argv、backup、source hashes及逐欄diff在 `dated_fill_cli_summary.json`、`dated_fill_cli_{dry_run,apply,second_apply}.json`。既有opaque欄位原樣保留，沒有市場統計。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/verify_results_fill_copy.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/verify_dated_fill_cli.py
```

兩個驗收script刻意拒絕覆寫既有v1 output folder。重現時要新version output並保留舊manifest，不刪baseline。執行前載入audit environment.json。現有summary保存exact argv及各來源hash。

第一輪full檢查 exit1：shared timeout test的一秒ready條件失敗（1239 shared tests passed）；獨立完整 test_process_runner.py重跑exit0，失敗歷史保留。dated integration之後 quick/full另在 `results_fill_dated_{quick,full}.log`，terminal結果未到前不當PASS。AU stale-baseline warning／isolated HKJC skip仍不等於field-health或PIT驗證。

未完成：raw／dense原有Barrier語義、Trainer／runner Time可恢復來源、逐個reader相容性、新鮮度／PIT lineage與eligible corpus、完整模型／19 leaf verdict矩陣。這項證據證明repair邊界與接駁，不是整個G2或全審計完成。

## Terminal 驗證補充

新quick／full均exit0；AU 782 tests、Shared1240 tests通過。原full的一秒ready失敗保留；沒有改timeout來救測試。`results_fill_revision_check_manifest.json`保存code／log hashes與stale-baseline／HKJC skip限制。

Reader補充：`results_reader_candidates_v1.json`盤點32個static候選，並fixture重現generic Sandown／空venue selector混入兩種layout，仍FLAG。`repaired_reader_parsing_v1.json`在去掉市場欄位的metadata-only前後副本跑canonical loader及draw／distance parser：34410 CSV列、34218 retained identities／positions次序相同；Barriers parse非空18711→34262、Distance18721→34272。這只證明代表性parser相容；不證明所有readers、完整人口、raw／dense語義或PIT。
