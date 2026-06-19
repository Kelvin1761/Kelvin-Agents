---
name: HKJC Wong Choi Legacy
description: HKJC Wong Choi 舊版快照已封存，只供手動比對或考古使用。
skills: hkjc_racing, betting_accountant
---
# HKJC Wong Choi Legacy

當用戶明確要求 `hkjc wong choi legacy`、舊版 HKJC pipeline、或需要比對 legacy 輸出時，使用以下封存快照：

```bash
python3 .agents/archive/wong_choi_legacy_snapshot_20260526/hkjc/hkjc_orchestrator_legacy_snapshot_20260526.py <URL或資料夾>
```

除非用戶明確要求 legacy，否則 `HKJC Wong Choi` 一律使用 full Python 主線：

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```
