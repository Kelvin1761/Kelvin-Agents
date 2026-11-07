# 重現比較及資料證據

本 dossier 保存完整 Sol 初選、逐駒分析、揭盲後覆盤及比較。原始輸入／完整旺財 attribution 不入 git，保存在已掛載的外置碟；檔案 hash 見 `archive_receipt.json`、archive 的 `archive_manifest.json`。

Archive：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-sol-flemington-20261107/`

- `dossier/inputs/R1.md` ... `R9.md`：Sol 當時唯一馬匹證據，含 R/F 行號。
- `dossier/`：所有初選、覆盤、JSON、source/hash receipts。
- `snapshot/`：原始 Racecard / Formguide、九份 Logic、Meeting_Auto_Scoring.csv 及 manifest。
- `Race_Results_Reflector.md`：凍結完整賽果。
- `scripts/`：實際使用的 prepare / compare scripts。
- `verification/`：quick/full 原始輸出。

LLM 生成不是可保證逐字重複的運算。此處保存的是當次實際輸出及 configured model `gpt-6.1-sol` / fresh-context agent task；沒有 API sampling seed 或供應商 response ID 可供宣稱。重跑模型不能取代原先鎖定選擇。

以下可以用已凍結輸入**重算相同比較指標**。先 checkout 本研究分支／commit 到 worktree，沿用 `.wongchoi_au_data_root` marker；確認外置碟真的掛載。將 `AU_SOL_REPO_DIR` 設成該 worktree：

```bash
A='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/au-sol-flemington-20261107'
R='/private/tmp/au-sol-flemington-replay'
mkdir -p "$R"
cp "$A/dossier/Sol_Predictions.json" "$A/dossier/Sol_Analysis.md" "$A/dossier/input_receipt.json" "$A/dossier/prediction_lock.json" "$R/"
cp -R "$A/dossier/inputs" "$R/"
export AU_SOL_REPO_DIR=/private/tmp/au-sol-flemington-20261107
export AU_SOL_DOSSIER_DIR="$R"
export AU_SOL_SNAPSHOT_DIR="$A/snapshot"
export AU_SOL_RESULTS_FILE="$A/Race_Results_Reflector.md"
export PYTHONDONTWRITEBYTECODE=1
/Users/imac/Antigravity-repo/.venv/bin/python3 "$A/scripts/au-sol-flemington-compare.py"
```

交付前已以外置碟 frozen snapshot/results 重播：**九場全部 metric objects 及全日 summary 完全相同**；不是只對最後幾個總數。
Script 先驗 prediction lock 及 input hash，才載入賽果；沒有把缺結果自動當作退賽，亦沒有重評／改模型。

Prepared-input script 用原 snapshot 的十八份來源再清理，不用來覆蓋本次凍結輸入。所有 source 路徑經 repo 的 `prediction_snapshot_dir`；不存在／外置碟離線時不能當空資料。
