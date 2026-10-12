# AU 結果 reader：精確 venue 身份修訂

狀態：**CORRECTNESS／SOURCE IDENTITY；G2 PARTIAL**。Baseline commit 0328f13a9564c787837e3c4aa1cfff19235c9b0c，所有修訂在隔離worktree。沒有候選績效、調參、WIN、production apply、commit或release。

Archive calibrator 的 loose substring selector 可接受空／generic target；reflector獨立副本還會刪 Heath／Hillside／Lakeside，未匹配時回傳全部venue。16個回歸fixture舊版13 failed／3 passed，新版16 passed。來源及失敗記錄保留 `archive_before_venue_identity.py.snapshot`、`reflector_before_venue_identity.py.snapshot`、`venue_identity_before.log`。

`au_result_identity.py` 統一AU的normalize/select；只去case、punctuation及明確meeting decoration，保留所有venue語義tokens（Gardens／Heath／Hillside／Lakeside／Parks／Synthetic／Acton／Scarpside等）。空／generic／不相關target不猜alias，exact layout只選該layout；有raw track就優先於可能已collapsed的舊slug。兩個legacyAPI名稱仍保留，既有callers接同一boundary。沒有合併AU與HKJC模型。

凍結metadata-only CSV34410列與original-source serving3385個profile比較（未計模型ranking或KPI）：兩個reader各3202 selections相同、183舊selection變unmatched。183組成：Rosehill→Rosehill Gardens47、Morphettville→Parks36、Sandown→Hillside35、Devonport→Synthetic29、Canberra→Acton14、Randwick-Kensington→Kensington14、Sandown→Lakeside8。這些是配對差異，不是績效改善，也不能說183全部是錯資料。

獨立source binding回復診斷：要求exact captured meeting key、source Logic hash相同、Logic/reported roster identical、complete reported field、CSV source venue/runner identities/positions完全相同。183中140可source-bound metadata recovery；11 Logic/reported roster不同、5 CSV/reported roster不同、27無exact captured meeting binding。沒有造global alias、修改production Logic或授予PIT。Legacy callers尚未consume此獨立binding，仍fail closed；不能直接拿post-race資料改pre-race features。

第一版diagnostic誤用compared entry的context identity查reported roster，誤報145 NO_COMPLETE。`venue_binding_recovery_v1_invalidated.json`明確INVALIDATED該結果並保留hash；v2用 `binding.identity`，才是有效本輪診斷。另覆核既有baseline description確實已用 `binding.identity`，沒有此錯。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/compare_venue_identity_bindings.py
PYTHONDONTWRITEBYTECODE=1 python3 docs/audits/au-full-model-20261011/audit_venue_binding_recovery_v2.py
```

Scripts保留input hashes、每個race的before/after source row IDs／venue、排除及recovery原因；拒絕覆寫v1/v2既有outputs。`venue_identity_check_manifest.json`記錄code/log hashes。Quick/full均exit0，AU798、Shared1240 tests通過；stale AU data-contract baseline warning與isolated HKJC data-contract skip仍保留，不能當PIT或field health PASS。

剩餘：43 unresolved metadata bindings及140外部binding的安全consumer接駁、全部reader語義／runtime/end-to-end核證、raw/effective draw、source historical availability、完整eligible corpus。這是兩個reader identity boundary的修正，不是完整G2或全模型審計完成。
