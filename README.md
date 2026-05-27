# Antigravity

Antigravity 係一個 prediction / analysis workspace，現時主線最重要嘅賽馬流程包括：

- `HKJC Wong Choi`
- `AU Wong Choi`
- `HKJC Reflector`
- `AU Reflector`

另外 repo 亦包含：

- `NBA Wong Choi`
- `tennis-wong-choi`

`HKJC Wong Choi` 同 `AU Wong Choi` 呢兩條 pre-race 主線都已經係 **full Python pipeline**，**唔需要 Gemini**，亦**唔需要任何 LLM**先可以運行。`HKJC Reflector` 同 `AU Reflector` 目前則以 Python unified orchestrator 做主入口。

## Start Here

如果你啱啱 clone 完 repo，請按以下次序睇：

1. [SETUP.md](SETUP.md)
   安裝 Python、建立 venv、裝依賴、驗證環境，並了解點跑 HKJC / AU / NBA / tennis / reflectors
2. [AGENTS.md](AGENTS.md)
   了解目前 agent / pipeline 架構，同 HKJC / AU / NBA / tennis / reflector 入口
3. [.agents/ARCHITECTURE.md](.agents/ARCHITECTURE.md)
   高層 folder map 參考
4. [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md)
   如要由另一部機 deploy snapshot 去 Cloudflare

## What A New User Should Do

clone 完 repo 之後，建議直接跟呢個流程：

1. 安裝 `Python 3.10+`
2. 建立 `.venv`
3. 執行 `pip install -r requirements.txt`
4. 執行 `python -m playwright install chromium`
5. 跑以下 command 驗證環境：

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py --help
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py --help
python .agents/skills/nba/nba_orchestrator.py --help
cd tennis-wong-choi && PYTHONPATH=src python -m tennis_wc.cli --help
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py --help
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py --help
python Horse_Racing_Dashboard/generate_static.py --help
```

6. 根據你想跑嘅流程，揀其中一個：

### Run HKJC Wong Choi

```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py "<HKJC racecard URL or meeting folder>"
```

### Run AU Wong Choi

```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<Racenet URL, meeting folder, or Race_X_Logic.json>"
```

### Run NBA Wong Choi

```bash
python .agents/skills/nba/nba_orchestrator.py --date YYYY-MM-DD
```

### Run HKJC / AU Reflector

```bash
python .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_reflector_orchestrator.py "<meeting_dir>"
python .agents/skills/au_racing/au_reflector/scripts/au_reflector_orchestrator.py "<meeting_dir>"
```

### Run tennis-wong-choi

```bash
cd tennis-wong-choi
PYTHONPATH=src python -m tennis_wc.cli --help
```

## Important Notes

- repo 已提供 `requirements.txt` 同 `requirements-optional.txt`
- `SETUP.md` 係目前最準確嘅安裝指南
- `AGENTS.md` 係目前最準確嘅 HKJC / AU / NBA / tennis / reflector 架構導覽
- `.agents/rules/GEMINI.md` 已 deprecated，只係為舊工具相容而保留
- `CLOUDFLARE_DEPLOYMENT.md` 係目前最準確嘅 Cloudflare setup 指南
- Windows 如要 deploy dashboard，建議用 `Git Bash`、`WSL` 或 `bash deploy.sh`

## Common Next Steps

- 想跑 HKJC：
  睇 `SETUP.md` 入面 `Run HKJC Wong Choi`
- 想跑 AU：
  睇 `SETUP.md` 入面 `Run AU Wong Choi`
- 想跑 NBA：
  睇 `SETUP.md` 入面 `Run NBA Wong Choi`
- 想跑 tennis：
  睇 `SETUP.md` 入面 `Run tennis-wong-choi`
- 想跑 race reflector：
  睇 `SETUP.md` 入面 `Run HKJC / AU Reflector`
- 想 deploy dashboard：
  跑 repo root `./deploy.sh`
