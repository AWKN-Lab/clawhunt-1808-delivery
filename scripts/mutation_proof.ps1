param()

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
$env:PYTHONPATH = $RepoRoot
$Target = Join-Path $RepoRoot "app\agent\minor.py"
$Test = "tests/test_rules.py::test_age_gate_by_month"
$Original = [System.IO.File]::ReadAllText($Target)
$Mutated = $Original.Replace("return age_at(birth_ym, today) < 18", "return False")
$Utf8 = New-Object System.Text.UTF8Encoding($false)

if ($Mutated -eq $Original) {
    Write-Host "MUTATION SETUP FAIL: target line not found"
    exit 2
}

$red = $false
$green = $false
try {
    [System.IO.File]::WriteAllText($Target, $Mutated, $Utf8)
    Push-Location $RepoRoot
    & $Python -m pytest $Test -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "MUTATION SURVIVED (bad): 18-year gate test stayed green"
        $red = $false
    }
    else {
        Write-Host "MUTATION RED (expected): 18-year gate test failed under mutation"
        $red = $true
    }
}
finally {
    [System.IO.File]::WriteAllText($Target, $Original, $Utf8)
}

& $Python -m pytest $Test -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "MUTATION GREEN (restored): 18-year gate test passed"
    $green = $true
}
else {
    Write-Host "MUTATION GREEN FAIL: restored source does not pass the test"
    $green = $false
}
Pop-Location

if ($red -and $green) {
    Write-Host "MUTATION PROOF PASS"
    exit 0
}
Write-Host "MUTATION PROOF FAIL"
exit 1
