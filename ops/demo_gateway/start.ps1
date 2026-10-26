param([switch]$ValidateOnly)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontendDist = Join-Path $repoRoot "frontend\dist"
$caddyfile = Join-Path $PSScriptRoot "Caddyfile"
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $localAppData) { throw "Windows LocalAppData folder could not be resolved." }
$gatewayPasswordHashPath = Join-Path $localAppData "CityResponder\config\demo-gateway\password.hash"
$healthUrl = "http://127.0.0.1:8020/health"

if (-not (Test-Path -LiteralPath (Join-Path $frontendDist "index.html") -PathType Leaf)) {
    throw "Frontend build missing. Run npm run build in the frontend directory first."
}

$caddyCommand = Get-Command caddy -ErrorAction SilentlyContinue
$caddyPath = if ($caddyCommand) { $caddyCommand.Source } else { $null }
if (-not $caddyPath) {
    $linksPath = Join-Path $localAppData "Microsoft\WinGet\Links\caddy.exe"
    if (Test-Path -LiteralPath $linksPath -PathType Leaf) {
        $caddyPath = $linksPath
    }
}
if (-not $caddyPath) {
    $packagesPath = Join-Path $localAppData "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $packagesPath -PathType Container) {
        $package = Get-ChildItem -LiteralPath $packagesPath -Directory -Filter "CaddyServer.Caddy_*" | Select-Object -First 1
        if ($package) {
            $binary = Get-ChildItem -LiteralPath $package.FullName -File -Filter "caddy.exe" -Recurse | Select-Object -First 1
            if ($binary) { $caddyPath = $binary.FullName }
        }
    }
}
if (-not $caddyPath) {
    throw "Caddy executable not found. Install CaddyServer.Caddy with winget and restart PowerShell."
}

if (-not (Test-Path -LiteralPath $gatewayPasswordHashPath -PathType Leaf)) {
    throw "Demo gateway authentication is not configured. Create the LocalAppData Caddy password hash before starting the gateway."
}
$gatewayPasswordHash = (Get-Content -LiteralPath $gatewayPasswordHashPath -Raw).Trim()
if ($gatewayPasswordHash -notmatch '^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$') {
    throw "Demo gateway password hash is invalid; the gateway will not start without valid authentication."
}

if ($ValidateOnly) {
    $previousFrontendDist = $env:CITYRESPONDER_FRONTEND_DIST
    $previousGatewayPasswordHash = $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH
    try {
        $env:CITYRESPONDER_FRONTEND_DIST = $frontendDist.Replace("\", "/")
        $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $gatewayPasswordHash
        & $caddyPath validate --config $caddyfile --adapter caddyfile | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Caddy configuration validation failed." }
        Write-Host "Gateway startup validation: PASS."
    } finally {
        if ($null -eq $previousFrontendDist) { Remove-Item Env:CITYRESPONDER_FRONTEND_DIST -ErrorAction SilentlyContinue }
        else { $env:CITYRESPONDER_FRONTEND_DIST = $previousFrontendDist }
        if ($null -eq $previousGatewayPasswordHash) { Remove-Item Env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH -ErrorAction SilentlyContinue }
        else { $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $previousGatewayPasswordHash }
    }
    return
}

try {
    $health = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -UseBasicParsing
    if ($health.StatusCode -ne 200) { throw "FastAPI health check returned HTTP $($health.StatusCode)." }
} catch {
    throw "FastAPI must be running on 127.0.0.1:8020 before the gateway starts. $($_.Exception.Message)"
}

$portProbe = [System.Net.Sockets.TcpClient]::new()
try {
    $portProbe.Connect("127.0.0.1", 8080)
    throw "Port 8080 is already in use; refusing to replace an existing listener."
} catch [System.Net.Sockets.SocketException] {
    # An unreachable loopback port is the expected state before startup.
} finally {
    $portProbe.Dispose()
}

$previousFrontendDist = $env:CITYRESPONDER_FRONTEND_DIST
$previousGatewayPasswordHash = $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH
try {
    $env:CITYRESPONDER_FRONTEND_DIST = $frontendDist.Replace("\", "/")
    $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $gatewayPasswordHash
    & $caddyPath validate --config $caddyfile --adapter caddyfile
    if ($LASTEXITCODE -ne 0) { throw "Caddy configuration validation failed." }

    Write-Host "Starting CityResponder demo gateway on http://127.0.0.1:8080"
    Write-Host "Press Ctrl+C in this window to stop the gateway."
    & $caddyPath run --config $caddyfile --adapter caddyfile
    if ($LASTEXITCODE -ne 0) { throw "Caddy exited with code $LASTEXITCODE." }
} finally {
    if ($null -eq $previousFrontendDist) {
        Remove-Item Env:CITYRESPONDER_FRONTEND_DIST -ErrorAction SilentlyContinue
    } else {
        $env:CITYRESPONDER_FRONTEND_DIST = $previousFrontendDist
    }
    if ($null -eq $previousGatewayPasswordHash) {
        Remove-Item Env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH -ErrorAction SilentlyContinue
    } else {
        $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $previousGatewayPasswordHash
    }
}
