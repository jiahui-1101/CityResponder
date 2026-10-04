$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backendRoot = Join-Path $repoRoot "backend"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logRoot = Join-Path $repoRoot "data\runtime_logs"
$stdoutLog = Join-Path $logRoot "fastapi.stdout.log"
$stderrLog = Join-Path $logRoot "fastapi.stderr.log"

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8020/health" -UseBasicParsing -TimeoutSec 2
    if ($health.StatusCode -eq 200) {
        exit 0
    }
} catch {
    # The listener is not ready; start the user-session instance below.
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "CityResponder Python runtime not found: $python"
}

Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8020") `
    -WorkingDirectory $backendRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden
