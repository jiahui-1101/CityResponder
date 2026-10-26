param(
    [switch]$SelfTest,
    [switch]$VerifyOnly,
    [string]$TunnelOrigin
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if (-not $localAppData) { throw 'Windows LocalAppData folder could not be resolved.' }
$gatewayDir = Join-Path $localAppData 'CityResponder\config\demo-gateway'
$hashPath = Join-Path $gatewayDir 'password.hash'
$dpapiPath = Join-Path $gatewayDir 'password.dpapi'
$caddyfile = Join-Path $PSScriptRoot 'Caddyfile'
$caddyPath = Join-Path $localAppData 'Microsoft\WinGet\Links\caddy.exe'
$frontendDist = Join-Path $repoRoot 'frontend\dist'
$utf8 = [Text.UTF8Encoding]::new($false)
$id = [guid]::NewGuid().ToString('N')
$hashTemp = Join-Path $gatewayDir "password.hash.$id.tmp"
$dpapiTemp = Join-Path $gatewayDir "password.dpapi.$id.tmp"
$hashBackup = Join-Path $gatewayDir "password.hash.$id.rollback"
$dpapiBackup = Join-Path $gatewayDir "password.dpapi.$id.rollback"
$hashFailedVersion = Join-Path $gatewayDir "password.hash.$id.failed"
$dpapiFailedVersion = Join-Path $gatewayDir "password.dpapi.$id.failed"
$hashReplaced = $false
$dpapiReplaced = $false
$dpapiExisted = $false
$success = $false
$newCaddy = $null
$oldPassword = $null
$failureMessage = $null

function ConvertFrom-SecureStringInMemory([securestring]$value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Get-GatewayStatus([string]$path, [string]$password) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("cityresponder-team:$password"))
    $headers = @{ Authorization = "Basic $encoded" }
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8080$path" -Headers $headers -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 8
    return [int]$response.StatusCode
}

function Get-PreviousGatewayPassword([string]$recordPath) {
    if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) { return $null }
    try {
        $secure = (Get-Content -LiteralPath $recordPath -Raw).Trim() | ConvertTo-SecureString
        $candidate = ConvertFrom-SecureStringInMemory $secure
        if ((Get-GatewayStatus '/login' $candidate) -eq 200) { return $candidate }
    } catch { }
    return $null
}

function Start-Gateway([string]$passwordHash) {
    $env:CITYRESPONDER_FRONTEND_DIST = $frontendDist.Replace('\', '/')
    $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $passwordHash
    return Start-Process -FilePath $caddyPath -ArgumentList @('run', '--config', $caddyfile, '--adapter', 'caddyfile') -WindowStyle Hidden -PassThru
}

function Wait-Gateway {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction Stop)
            if ($listener.Count -eq 1 -and $listener[0].LocalAddress -eq '127.0.0.1') { return }
        } catch { }
    }
    throw 'Caddy did not return on loopback port 8080.'
}

function Protect-GatewayFile([string]$path) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $path /inheritance:r /grant:r "*$($sid):(F)" '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict gateway file permissions.' }
}

if ($SelfTest) {
    $testRoot = Join-Path $localAppData ('CityResponder\test_tmp\gateway-reset-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $testHash = Join-Path $testRoot 'password.hash'
    $testRecord = Join-Path $testRoot 'password.dpapi'
    $testTemp = Join-Path $testRoot 'password.hash.tmp'
    $testBackup = Join-Path $testRoot 'password.hash.rollback'
    $testFailed = Join-Path $testRoot 'password.hash.failed'
    $testRecordTemp = Join-Path $testRoot 'password.dpapi.tmp'
    try {
        [IO.File]::WriteAllText($testHash, 'old-disposable-hash', $utf8)
        if (Test-Path -LiteralPath $testRecord) { throw 'Missing-record fixture is invalid.' }
        if ($null -ne (Get-PreviousGatewayPassword $testRecord)) { throw 'Missing record incorrectly required the old password.' }
        [IO.File]::WriteAllText($testTemp, 'new-disposable-hash', $utf8)
        Protect-GatewayFile $testTemp
        [IO.File]::Replace($testTemp, $testHash, $testBackup)
        [IO.File]::WriteAllText($testRecordTemp, 'disposable-dpapi-fixture', $utf8)
        Protect-GatewayFile $testRecordTemp
        [IO.File]::Move($testRecordTemp, $testRecord)
        if ((Get-Content $testRecord -Raw) -ne 'disposable-dpapi-fixture') { throw 'Missing-record bootstrap failed.' }
        if ($null -ne (Get-PreviousGatewayPassword $testRecord)) { throw 'Unreadable optional record incorrectly required the old password.' }
        Copy-Item -LiteralPath $testBackup -Destination $testTemp
        [IO.File]::Replace($testTemp, $testHash, $testFailed)
        if ((Get-Content $testHash -Raw) -ne 'old-disposable-hash') { throw 'Rollback fixture failed.' }
        Write-Host 'Isolated missing-DPAPI bootstrap and rollback: PASS.'
    } finally {
        $resolved = [IO.Path]::GetFullPath($testRoot)
        $allowed = [IO.Path]::GetFullPath((Join-Path $localAppData 'CityResponder\test_tmp'))
        if (-not $resolved.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path.' }
        Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

if ($VerifyOnly) {
    if (-not (Test-Path -LiteralPath $dpapiPath -PathType Leaf)) { throw 'Gateway DPAPI password record is missing in this PowerShell context.' }
    $verifiedPassword = Get-PreviousGatewayPassword $dpapiPath
    if (-not $verifiedPassword) { throw 'Locally stored gateway password was not accepted on loopback.' }
    $origins = @('http://127.0.0.1:8080')
    if ($TunnelOrigin) {
        $uri = [uri]$TunnelOrigin
        if ($uri.Scheme -ne 'https' -or $uri.AbsolutePath -ne '/' -or $uri.Query -or $uri.Fragment) {
            throw 'TunnelOrigin must be an exact HTTPS origin.'
        }
        $origins += $uri.GetLeftPart([UriPartial]::Authority)
    }
    $credential = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("cityresponder-team:$verifiedPassword"))
    foreach ($origin in $origins) {
        $anonymous = Invoke-WebRequest -Uri "$origin/login" -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 20
        $login = Invoke-WebRequest -Uri "$origin/login" -Headers @{ Authorization = $credential } -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 20
        $asset = [regex]::Match($login.Content, '/assets/[^" ]+\.js').Value
        if (-not $asset) { throw 'Frontend JavaScript asset was not found.' }
        $javascript = Invoke-WebRequest -Uri ($origin + $asset) -Headers @{ Authorization = $credential } -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 20
        if ($anonymous.StatusCode -ne 401 -or $login.StatusCode -ne 200 -or $login.RawContentLength -lt 100 -or $javascript.StatusCode -ne 200) {
            throw "Gateway verification failed for $origin."
        }
        $scope = if ($origin.StartsWith('https://')) { 'PUBLIC' } else { 'LOCAL' }
        Write-Host "$scope gateway: anonymous 401, new password 200, JavaScript 200."
    }
    $fastapi = Invoke-WebRequest -Uri 'http://127.0.0.1:8020/health' -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 8
    if ($fastapi.StatusCode -ne 200) { throw 'FastAPI health check failed.' }
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction Stop)
    if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw 'Caddy is not bound only to loopback.' }
    if ($TunnelOrigin -and @(Get-Process cloudflared -ErrorAction SilentlyContinue).Count -lt 1) { throw 'Cloudflare tunnel process is not running.' }
    Write-Host 'Gateway verification: PASS. FastAPI healthy; Caddy loopback-only.'
    Remove-Variable verifiedPassword,credential -ErrorAction SilentlyContinue
    exit 0
}

try {
    if (-not (Test-Path -LiteralPath $caddyPath -PathType Leaf)) { throw 'Installed Caddy executable not found.' }
    if (-not (Test-Path -LiteralPath $hashPath -PathType Leaf)) { throw 'Gateway hash file not found.' }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDist 'index.html') -PathType Leaf)) { throw 'Frontend build not found.' }
    if (@(Get-Process cloudflared -ErrorAction SilentlyContinue).Count -ne 1) { throw 'Expected exactly one running cloudflared process.' }
    $fastapi = Invoke-WebRequest -Uri 'http://127.0.0.1:8020/health' -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 8
    if ($fastapi.StatusCode -ne 200) { throw 'FastAPI health check failed.' }

    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction Stop)
    if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw 'Caddy listener is not uniquely bound to loopback.' }
    $oldCaddyId = $listener[0].OwningProcess
    if ((Get-Process -Id $oldCaddyId -ErrorAction Stop).ProcessName -ne 'caddy') { throw 'Port 8080 is not owned by Caddy.' }

    $oldHash = (Get-Content -LiteralPath $hashPath -Raw).Trim()
    if ($oldHash -notmatch '^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$') { throw 'Current Caddy hash is invalid.' }
    # A missing or unreadable DPAPI record must never prevent a password reset.
    # It is optional evidence for testing the old password after restart.
    $dpapiExisted = Test-Path -LiteralPath $dpapiPath -PathType Leaf
    $oldPassword = Get-PreviousGatewayPassword $dpapiPath

    Write-Host 'Choose a new password that has not been used for this gateway.'
    $newSecure = Read-Host 'New gateway password (hidden)' -AsSecureString
    $confirmSecure = Read-Host 'Confirm new gateway password (hidden)' -AsSecureString
    if ($newSecure.Length -lt 20) { throw 'Use at least 20 characters.' }
    $newPassword = ConvertFrom-SecureStringInMemory $newSecure
    $confirmation = ConvertFrom-SecureStringInMemory $confirmSecure
    if ($newPassword -cne $confirmation) { throw 'Password confirmation did not match.' }
    if ($newPassword -cnotmatch '[A-Z]' -or $newPassword -cnotmatch '[a-z]' -or
        $newPassword -notmatch '[0-9]' -or $newPassword -notmatch '[^A-Za-z0-9]') {
        throw 'Use uppercase, lowercase, a number, and a symbol.'
    }
    if ($oldPassword -and $newPassword -ceq $oldPassword) { throw 'Choose a different password.' }

    # Caddy reads the secret from redirected stdin. It is never an argument,
    # environment variable, temporary plaintext file, or console output.
    $processInfo = [Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $caddyPath
    $processInfo.ArgumentList.Add('hash-password')
    $processInfo.ArgumentList.Add('--algorithm')
    $processInfo.ArgumentList.Add('bcrypt')
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $hashProcess = [Diagnostics.Process]::Start($processInfo)
    try {
        # Caddy reads through LF. PowerShell/.NET WriteLine emits CRLF on
        # Windows, causing Caddy to hash an unintended trailing CR byte.
        $hashProcess.StandardInput.Write($newPassword + "`n")
        $hashProcess.StandardInput.Close()
        $newHash = $hashProcess.StandardOutput.ReadToEnd().Trim()
        $null = $hashProcess.StandardError.ReadToEnd()
        $hashProcess.WaitForExit()
        if ($hashProcess.ExitCode -ne 0 -or $newHash -notmatch '^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$') { throw 'Caddy bcrypt hashing failed.' }
    } finally { $hashProcess.Dispose() }

    $env:CITYRESPONDER_FRONTEND_DIST = $frontendDist.Replace('\', '/')
    $env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH = $newHash
    & $caddyPath validate --config $caddyfile --adapter caddyfile | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Caddy configuration validation failed.' }

    [IO.File]::WriteAllText($hashTemp, "$newHash`n", $utf8)
    Protect-GatewayFile $hashTemp
    [IO.File]::Replace($hashTemp, $hashPath, $hashBackup)
    $hashReplaced = $true
    Protect-GatewayFile $hashPath

    Stop-Process -Id $oldCaddyId -ErrorAction Stop
    try { Wait-Process -Id $oldCaddyId -Timeout 10 -ErrorAction Stop } catch { }
    $newCaddy = Start-Gateway $newHash
    Wait-Gateway
    if ((Get-GatewayStatus '/login' $newPassword) -ne 200) { throw 'New gateway password was not accepted.' }
    if ($oldPassword -and (Get-GatewayStatus '/login' $oldPassword) -ne 401) { throw 'Old gateway password was not rejected.' }
    if ((Get-GatewayStatus '/health' $newPassword) -ne 200) { throw 'Gateway health check failed.' }

    $newDpapi = ConvertFrom-SecureString $newSecure
    [IO.File]::WriteAllText($dpapiTemp, "$newDpapi`n", $utf8)
    Protect-GatewayFile $dpapiTemp
    if ($dpapiExisted) {
        [IO.File]::Replace($dpapiTemp, $dpapiPath, $dpapiBackup)
    } else {
        [IO.File]::Move($dpapiTemp, $dpapiPath)
    }
    $dpapiReplaced = $true
    Protect-GatewayFile $dpapiPath
    if (@(Get-Process cloudflared -ErrorAction SilentlyContinue).Count -ne 1) { throw 'Cloudflare tunnel process is no longer running.' }
    if ((Invoke-WebRequest -Uri 'http://127.0.0.1:8020/health' -UseBasicParsing -SkipHttpErrorCheck -TimeoutSec 8).StatusCode -ne 200) { throw 'FastAPI health check failed after reset.' }
    $success = $true
    $oldCheck = if ($oldPassword) { 'old password: HTTP 401' } else { 'old password: unavailable for direct test' }
    Write-Host "Gateway password reset: PASS. New login: HTTP 200; $oldCheck. Caddy and FastAPI: healthy. Tunnel process: running."
} catch {
    $failureMessage = $_.Exception.Message
} finally {
    if (-not $success -and $hashReplaced) {
        try {
            if ($newCaddy -and -not $newCaddy.HasExited) { Stop-Process -Id $newCaddy.Id -ErrorAction Stop }
            if (Test-Path -LiteralPath $hashBackup) {
                Copy-Item -LiteralPath $hashBackup -Destination $hashTemp -ErrorAction Stop
                [IO.File]::Replace($hashTemp, $hashPath, $hashFailedVersion)
            }
            if ((Get-Content -LiteralPath $hashPath -Raw).Trim() -cne $oldHash) {
                throw 'Hash rollback did not restore the original value.'
            }
            if ($dpapiReplaced) {
                if ($dpapiExisted -and (Test-Path -LiteralPath $dpapiBackup)) {
                    Copy-Item -LiteralPath $dpapiBackup -Destination $dpapiTemp -ErrorAction Stop
                    [IO.File]::Replace($dpapiTemp, $dpapiPath, $dpapiFailedVersion)
                } elseif (-not $dpapiExisted) {
                    Remove-Item -LiteralPath $dpapiPath -ErrorAction Stop
                }
            }
            if (-not @(Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue)) {
                $null = Start-Gateway $oldHash
                Wait-Gateway
            }
            $restoredListener = @(Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction Stop)
            if ($restoredListener.Count -ne 1 -or $restoredListener[0].LocalAddress -ne '127.0.0.1') {
                throw 'Caddy rollback listener was not verified.'
            }
            Write-Host 'Original gateway hash and loopback listener restored after failure.'
        } catch {
            $failureMessage = 'Automatic rollback could not be verified. Preserve rollback files and inspect Caddy before retrying.'
        }
    }
    if ($success) {
        Remove-Item -LiteralPath $hashBackup, $dpapiBackup -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $hashTemp, $dpapiTemp, $hashFailedVersion, $dpapiFailedVersion -ErrorAction SilentlyContinue
    Remove-Variable oldPassword,newPassword,confirmation,newDpapi,newHash,oldHash -ErrorAction SilentlyContinue
    Remove-Item Env:CITYRESPONDER_DEMO_GATEWAY_PASSWORD_HASH,Env:CITYRESPONDER_FRONTEND_DIST -ErrorAction SilentlyContinue
}

if (-not $success) {
    Write-Error "Gateway password reset failed: $failureMessage"
    exit 1
}
