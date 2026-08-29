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

## 日常命令

唔使記其他嘢，呢幾條就夠：

| 命令 | 做咩 | 幾時跑 |
|---|---|---|
| `./檢查.sh` | code 有冇壞：ruff、評分 golden、模型說明新鮮度、數據合約、單元測試。加 `--quick` 跳過單元測試。 | 改完 code、交嘢之前 |
| `./健康.sh` | 營運有冇斷：磁碟、排程退出碼、資料時效、日誌報錯。加 `--tg` 推去 Telegram。 | 每週，或者覺得有嘢唔妥 |
| `./保存.sh --path … "訊息"` | Central exact-scope release：自動 gate、commit、push、manifest、Telegram；高風險改動等 `/approve SHA` 先 merge／activate。 | 想安全保存改動 |
| `./備份.sh` | 備份 repo + 賽果資料去外置碟。加 `--verify` 只核對唔複製。 | 每週，或者做大改動之前 |
| `./整理.sh` | 列出可以安全刪嘅分支同工作副本（只刪已完全合併入 `main` 嘅）。加 `--做` 先會真係刪。 | 覺得分支太亂 |

**`檢查.sh` 同 `健康.sh` 嘅分別**：前者問「我啲 code 有冇壞」，後者問「今日啲嘢有冇正常跑」。兩個問題唔同，答案唔互相覆蓋。

## 想睇個模型而家係點

打開 **[`Wong Choi 模型說明/`](Wong%20Choi%20模型說明/)** 入面兩份 `.html`（雙擊就得）。

呢兩份文件由 live code 自動生成，唔係人手寫，所以永遠唔會同真實模型講唔同嘅嘢
（上一份人手寫嘅過期咗兩個月都冇人發現）。更新：`./Wong\ Choi\ 模型說明/更新模型說明.sh`

### 五道防線分別捉咩

| 防線 | 捉邊種問題 |
|---|---|
| 清 bytecode cache | macOS 系統 Python 淨係靠 (mtime, 檔案大細) 判斷要唔要重新編譯。改個權重由 `0.08037` → `0.09037` 位元組數一樣，同一秒內改完再跑 = **靜靜行返舊 code**。呢個係「A/B 結果同 baseline 一模一樣」嘅其中一個成因。 |
| `ruff` | undefined name、語法錯。第一次跑就捉到 `generate_meeting_intel.py` 一個 live `NameError`（場地狀況成年攞唔到）。 |
| 評分 golden | 凍結 120 匹真馬嘅每個維度分。改一行 code 意外郁到第三個維度，會逐匹馬印出嚟。 |
| 模型說明新鮮度 | 引擎改咗但文件冇重新生成 → 紅燈。 |
| 數據合約 | 欄位靜靜變空／變常數／單位飛咗。基準由真實語料庫量出嚟，唔係估。 |

## Start Here

如果你啱啱 clone 完 repo，請按以下次序睇：

1. [SETUP.md](SETUP.md)
   安裝 Python、建立 venv、裝依賴、驗證環境，並了解點跑 HKJC / AU / NBA / tennis / reflectors
   —— **Windows 用戶請改睇 [WINDOWS_SETUP.md](WINDOWS_SETUP.md)**（由零開始，包埋
   Google Drive「可離線使用」、Git Bash 換行符、Cloudflare 認證同已知限制）
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
- `WINDOWS_SETUP.md` 係 Windows workstation 嘅完整安裝指南
- Windows 如要 deploy dashboard，建議用 `Git Bash`、`WSL` 或 `bash deploy.sh`
- 驗證安裝：`./run_tests.sh`（macOS/Linux）或 `.\run_tests.ps1`（Windows）——
  每個 suite 開獨立 process，因為 AU 同 HKJC 都有叫 `scoring` 嘅 module，同一個
  process 入面會互相蓋過

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
