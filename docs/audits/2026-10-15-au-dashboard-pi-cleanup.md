# AU dashboard PI 顯示清理（2026-10-15）

用戶要求更新dashboard，移除冇用嘅PI。AU PI只進入report-only sectional_score，
不在現役排名公式；HKJC沙田仍透過走位匹配計分，故只清理明確AU meeting。
參照 EXP-20261013-12；今次不改任何模型分數或評估規則。

`services/au_display_policy.py`於projection生成時移除PI段落、句子及表格欄。
同一政策適用新建、快取、from-snapshot、JSON刷新與lazy analysis bundles；
保留原始source報告、L400/L600、試閘備戰背景、horse identity、grades、scores及picks。
未知region不當AU處理。清理具idempotency，HKJC不變。

驗證：

- Dashboard frontend 69 tests PASS。
- Dashboard Python 183 PASS／2 SKIP，包括4項新guard。
- Scoped ruff、diff check、`./檢查.sh --quick` PASS；Central發佈另跑完整gate及clean-clone recheck。
- 已發佈快照5個meetings：280匹AU馬raw_text嘅PI提述620→0；全部horse number／name／rank／
  ability／grade、每場Top picks完全一致；100匹HKJC馬objects逐項相等。
- AU lazy bundles亦無PI；本機瀏覽器驗證完整分析及速度背景可開啟，L600資料仍在。
- Build HTML約3.86MiB、JSON8.70MiB，5個analysis bundles合共5.53MiB，逐檔低於25MiB。
- 不重算已發佈賽事；新六場試閘performance規則已由Central commit `21f15a05`啟用，
  四線production alignment PASS。未通過嘅refit權重維持不套用。

本次dashboard deploy保留live race projection，不full-rescan archive；不寫D1 betting ledger。
部署結果以Central release manifest／activation events及Cloudflare回讀為準。
