# 驗證及保存

- baseline：3083316d55fd35d798772514248ae2723e6b469b。
- HKJC production及shared scoring/harness與同session 2d7ec14c capture無code diff；只有AU data-contract資源有變。
- 325場 A/A raw ability及完整排名一致；A/A經既有v3判REJECT。
- winner／close_top3／neutral_trip，各8場direct production核對，共24組；raw ability及完整排名完全一致。
- 9項日期／parser安全檢查通過，包括勝出距離不當輸距、混合分數、缺XW、同日／未來紀錄排除。
- ./檢查.sh --quick：PASS。
- ./檢查.sh 最終版本：PASS，All suites passed。最初版本曾因研究helper漏import re而ruff失敗；已修復並重跑完整檢查。
- 所有production code、golden、contract calibration、模型說明均無改動。
- 日誌：/private/tmp/hkjc-trip-20261016-{study,validate,report,full-final,final-quick}.log。
- 同一候選家族三arm×六metrics Holm；close_top3原始RANKING_WIN經修正後未支持（ranking Holm p=0.648）。
- neutral_trip是用戶追加的固定消融；追加時未檢視其績效，原有arm與門檻保持不變，所有arm重新計Holm。
- 不開2026-10-11起forward；歷史artifact可用時間仍FLAG，不作promotion。
- 只保存研究及實驗記錄至獨立非main分支，不merge、不deploy、不啟用候選。
