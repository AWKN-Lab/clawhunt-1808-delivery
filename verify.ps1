param(
    [switch]$SkipMutation
)

$RepoRoot = $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
$env:PYTHONPATH = $RepoRoot

Push-Location $RepoRoot
$failed = 0

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Host ""
    Write-Host "=== $Name ==="
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "STEP FAIL: $Name (exit $LASTEXITCODE)"
        $script:failed = 1
    }
    else {
        Write-Host "STEP PASS: $Name"
    }
}

Invoke-Step "pytest" { & $Python -m pytest -q }
Invoke-Step "eval (fail-closed thresholds)" { & $Python -m eval.run }
Invoke-Step "compose static check" { & $Python scripts/compose_check.py }
Invoke-Step "http smoke (7/7 booking + SSE latency)" { & $Python scripts/http_smoke.py }

if (-not $SkipMutation) {
    Invoke-Step "mutation proof (red then green)" {
        & (Join-Path $RepoRoot "scripts/mutation_proof.ps1")
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "VERIFY PASS"
}
else {
    Write-Host "VERIFY FAIL"
}
Pop-Location
exit $failed
