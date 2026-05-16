---
name: HKJC Wong Choi Legacy
description: 保留舊版 HKJC Wong Choi LangGraph / LLM-assisted pipeline 的入口，供過渡期或比對使用。
skills: hkjc_racing, betting_accountant
---
# HKJC Wong Choi Legacy

當用戶明確要求 `hkjc wong choi legacy`、舊版 HKJC pipeline、或需要比對 legacy 輸出時，使用以下入口：

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator_legacy.py <URL或資料夾>
```

除非用戶明確要求 legacy，否則 `HKJC Wong Choi` 一律使用 full Python 主線：

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```
