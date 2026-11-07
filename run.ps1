param(
    [int]$Port = 8000
)

$RepoRoot = $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$env:PYTHONPATH = $RepoRoot
$env:DB_MODE = "sqlite"
$env:LLM_MODE = "mock"

Push-Location $RepoRoot
try {
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
