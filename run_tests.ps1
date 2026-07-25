# Run every Wong Choi test suite — Windows PowerShell.
#
#   powershell -ExecutionPolicy Bypass -File .\run_tests.ps1
#
# WHY each suite gets its OWN python process:
# AU and HKJC each ship a top-level module named `scoring` (and `draw`,
# `trainer`, ...) and each inserts its own scripts/ dir into sys.path. Import
# them in one process and whichever loads first poisons the other:
#   ImportError: cannot import name 'DEBUT_MATRIX_WEIGHTS' from 'scoring'
# So a single pytest call covering both can NEVER work. Do not "simplify" this
# script by collapsing the suites into one invocation.
Set-Location -Path $PSScriptRoot
$RepoRoot = $PSScriptRoot

# Chinese meeting names / markdown output need UTF-8 on Windows.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

if (Test-Path ".venv\Scripts\Activate.ps1") { & .\.venv\Scripts\Activate.ps1 }

$passed = New-Object System.Collections.Generic.List[string]
$failed = New-Object System.Collections.Generic.List[string]

function Invoke-Suite {
  param([string]$Label, [string]$WorkDir, [string[]]$Targets)
  Write-Host ""
  Write-Host "=============================================================="
  Write-Host "  $Label"
  Write-Host "=============================================================="
  Push-Location $WorkDir
  try {
    & python -m pytest @Targets -q -p no:cacheprovider
    if ($LASTEXITCODE -eq 0) { $script:passed.Add($Label) } else { $script:failed.Add($Label) }
  } finally {
    Pop-Location
  }
}

Invoke-Suite "AU Wong Choi"       $RepoRoot @(".agents/skills/au_racing/au_wong_choi_auto/tests")
Invoke-Suite "HKJC Wong Choi"     $RepoRoot @(".agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests")
Invoke-Suite "Shared racing"      $RepoRoot @(".agents/skills/shared_racing/tests")
Invoke-Suite "Race compliance QA" $RepoRoot @(".agents/skills/race_compliance_qa/tests")
Invoke-Suite "NBA Wong Choi"      $RepoRoot @(".agents/skills/nba/nba_wong_choi/tests")
Invoke-Suite "Agent scripts"      $RepoRoot @(".agents/scripts/tests")
Invoke-Suite "Dashboard (python)" $RepoRoot @("Horse_Racing_Dashboard/tests", "Horse_Racing_Dashboard/backend/tests")
Invoke-Suite "Tennis Wong Choi"   (Join-Path $RepoRoot "tennis-wong-choi") @("tests")

# Dashboard Cloudflare Functions + static template are node:test, not pytest.
if (Get-Command node -ErrorAction SilentlyContinue) {
  Write-Host ""
  Write-Host "=============================================================="
  Write-Host "  Dashboard (node)"
  Write-Host "=============================================================="
  $nodeOk = $true
  Get-ChildItem "Horse_Racing_Dashboard\tests\*.mjs" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "--- $($_.Name)"
    & node $_.FullName | Select-String -Pattern "^# (pass|fail)"
    if ($LASTEXITCODE -ne 0) { $nodeOk = $false }
  }
  if ($nodeOk) { $passed.Add("Dashboard (node)") } else { $failed.Add("Dashboard (node)") }
} else {
  Write-Host "!! node not found — skipped Dashboard (node) suite"
}

Write-Host ""
Write-Host "=============================================================="
Write-Host "  SUMMARY"
Write-Host "=============================================================="
foreach ($s in $passed) { Write-Host "  PASS  $s" }
foreach ($s in $failed) { Write-Host "  FAIL  $s" -ForegroundColor Red }

if ($failed.Count -gt 0) {
  Write-Host ""
  Write-Host "$($failed.Count) suite(s) failed." -ForegroundColor Red
  exit 1
}
Write-Host ""
Write-Host "All suites passed." -ForegroundColor Green
