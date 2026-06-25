# One-shot setup for a NEW Windows machine (PowerShell).
# Run from the repo root after: git clone https://github.com/Kelvin1761/Kelvin-Agents.git
#
#   cd Kelvin-Agents
#   powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
#
# Idempotent — safe to re-run.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Use UTF-8 so the Chinese folder/path names behave
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

Write-Host "==> 1/5  Python virtual environment (.venv)"
if (-not (Test-Path ".venv")) { py -3.10 -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install --quiet --upgrade pip setuptools wheel

Write-Host "==> 2/5  Python dependencies"
pip install --quiet -r requirements.txt
if (Test-Path "requirements-optional.txt") {
  try { pip install --quiet -r requirements-optional.txt } catch { Write-Host "   (optional deps skipped)" }
}

Write-Host "==> 3/5  Playwright Chromium (for scrapers)"
try { python -m playwright install chromium } catch { Write-Host "   (playwright install skipped)" }

Write-Host "==> 4/5  Data location (WONGCHOI_DATA_ROOT)"
if (Test-Path ".wongchoi_data_root") {
  Write-Host "   .wongchoi_data_root already set: $(Get-Content .wongchoi_data_root -Raw)"
} else {
  Write-Host "   The big 'Wong Choi ... Analysis' data folders usually live on Google Drive,"
  Write-Host "   separate from this code repo. Paste the path to the folder that CONTAINS them"
  Write-Host "   (e.g. G:\My Drive\...\Antigravity). Leave blank to use this repo dir."
  $dr = Read-Host "   DATA_ROOT path"
  if ($dr) {
    Set-Content -Path ".wongchoi_data_root" -Value $dr -Encoding UTF8
    Write-Host "   wrote .wongchoi_data_root"
  } else {
    Write-Host "   (left unset — DATA_ROOT defaults to this repo folder)"
  }
}

Write-Host "==> 5/5  Verify resolved paths"
python wongchoi_paths.py

Write-Host ""
Write-Host "OK. Each new shell: .\.venv\Scripts\Activate.ps1"
Write-Host "   Next, read SETUP.md to run HKJC / AU / NBA / tennis Wong Choi."
