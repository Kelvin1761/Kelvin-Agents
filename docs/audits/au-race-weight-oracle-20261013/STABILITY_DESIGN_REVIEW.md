# AU stability：訊號、設計同測試覆核

日期2026-10-13；baseline main a0bf0f38；本輪只研究，live維持FORM60／PQ40。

## 結論

原dev淨多5場Good係樣本內進步，唔應該抹殺；但固定40／60全期Good−2、
後段−7，不能當穩定改善。完整PQ有排序訊號，fallback弱好多。
最小來源分流候選全期Gold+4／Good+5，後段Good−1，值得凍結後再測。
呢個係同一批資料啟發嘅探索結果，不係新盲測。

## 已完成嘅測試改進

- 用現行main完整production projection重算baseline，逐匹exact核對；保持整個賽前field正規化、overlays、rounding、tie-break及安全換位，之後先join結果。
- 用引擎實際provenance區分完整PQ與fallback，不靠賠率、結果或者分數是否中性猜來源。SP只作診斷cohort。
- 分開單項AUC、整個模型增量、配對衝突、gain/loss、日期塊及後段；按日bootstrap保持同日相關。
- 原snapshot→現行matrix→現行features分步控制，解釋+14→+9→+5；不跨版本比較絕對命中數。

## 下一版設計應處理乜

stability而家混合近績FORM同表現質素PQ；先區分資料來源，避免consistency fallback
被當成真正PQ。最小候選只對完整PQ用40／60，其餘60／40，已量過結果，
不加sample-count、馬齡或場地門檻去追本輪得失。以前缺FORM→全PQ、fallback→全FORM
及n/3速度收縮已有失敗記錄，不能直接重用當改善。

往後若要更完整設計，分開三件事：預期能力、估計不確定性、今日適用程度。
正式有效往績數、距離／級數相似度、時間及試閘來源可以作可靠度資料；
但『資料少』不直接等於『能力差』，『有一課快試閘』亦不等於稳定。
這些尚未實作或證明，須逐項ablation；同class已有信用是否重複，須用增量測試，
不能只憑相關係數就扣分或再加分。

## 凍結後嘅驗證條件

1. 候選定義、baseline SHA、來源字串、語料名單、命令及判決按現行model-evaluation-contract v3凍結；不得改指標、窗口、top-K救候選。
2. 現有2533場全部視為已曝光research資料；禁止再叫後段holdout，亦不可用佢揀ratio或可靠度門檻。
3. 新日期賽前保存不可改prediction同原始來源快照；baseline與candidate同行同field、同賽前可得資訊。未有快照嘅舊archive只可重播診斷，不能聲稱歷史無洩漏。
4. 若擬合可靠度，所有參數只由各時間fold之前資料估計；做train-only walk-forward，保持未碰最終確認段。沒有學習參數嘅來源候選亦要未曝光日期確認。
5. Gold／Good仍是primary；按日bootstrap、現行日期塊與多候選校正照舊。同時檢查排名、完整／fallback來源、field及日期一致性。AUC係機制診斷，不替代primary。
6. 未通過以上條件不改live；不因本輪Good轉正就release。今輪沒有新增排程或自動追蹤。

## 數字與重現

| 全期2533場，相對60／40 | Gold | Good | 後段771場Good |
|---|---:|---:|---:|
| uniform40／60 | +5 | −2 | −7 |
| 完整PQ40／60，其餘60／40 | +4 | +5 | −1 |

來源候選全期Gold及Good day95% CI仍跨零；平均top3模型排名與NDCG仍稍差。
完整PQ AUC .6455，fallback .5403；後段FORM與完整PQ AUC約同為.645。

完整操作記錄：[EXP06](../../experiments/EXP-20261013-06-au-fixed-40-60-review.md)、
[EXP07](../../experiments/EXP-20261013-07-au-source-aware-stability-mix.md)。
診斷scripts在docs/experiments/patches/；結果在scratch/au_fixed_40_60_20261013/。
scripts明示PRIMARY資料位置與MAIN引擎位置，避免兩個版本無聲混用。

## 交付檢查

production `/usr/bin/python3` 3.9.6；於main a0bf0f38 managed worktree只複製本輪研究檔案，
`PYTHON_BIN=/usr/bin/python3 RUFF_CACHE_DIR=/private/tmp/au-stability-ruff ./檢查.sh --quick`
及完整`./檢查.sh`均全綠。ruff、AU/HKJC golden、模型說明、數據合約、全suite通過。
測試log：`/private/tmp/au_stability_review_quick.log`、`/private/tmp/au_stability_review_full.log`。
沒有修改production模型、沒有commit/push。PRIMARY其餘session工作保持原狀。
