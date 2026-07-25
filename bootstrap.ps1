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
# Nothing in the codebase needs 3.10+ syntax (the live Mac runs 3.9), so accept
# any 3.9+ interpreter instead of hard-pinning `py -3.10` — that pin fails
# outright on a box that only has 3.11 / 3.12 / 3.13 installed.
if (-not (Test-Path ".venv")) {
  $exe = $null
  $exeArgs = @()
  # Prefer the Windows launcher, newest sensible version first.
  foreach ($v in @("3.13", "3.12", "3.11", "3.10", "3.9")) {
    & py "-$v" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $exe = "py"; $exeArgs = @("-$v"); break }
  }
  if (-not $exe) {
    # No launcher match — fall back to `python` on PATH if it is 3.9+.
    try {
      & python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { $exe = "python" }
    } catch { }
  }
  if (-not $exe) {
    throw "No Python 3.9+ found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then re-run this script."
  }
  Write-Host "   using: $exe $exeArgs"
  & $exe @exeArgs -m venv .venv
}
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

Write-Host "==> 5/5  Verify resolved paths + data preflight"
python wongchoi_paths.py

Write-Host ""
Write-Host "==> Per-machine MCP config"
if (Test-Path ".agents\mcp_config.json") {
  Write-Host "   .agents\mcp_config.json already present"
} else {
  Write-Host "   Not present. It is gitignored (each machine keeps its own)."
  Write-Host "   Copy the template and edit the placeholder paths:"
  Write-Host "     copy .agents\mcp_config.json.template .agents\mcp_config.json"
}

Write-Host ""
Write-Host "OK. Each new shell: .\.venv\Scripts\Activate.ps1"
Write-Host "   Next, read SETUP.md to run HKJC / AU / NBA / tennis Wong Choi."
