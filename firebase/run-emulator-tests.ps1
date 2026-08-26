$ErrorActionPreference = "Stop"

# Some Windows launchers supply both `Path` and `PATH`. PowerShell's
# Start-Process treats those as duplicate environment keys and refuses to
# launch child services, so normalize the process environment first.
$processPath = $env:Path
Remove-Item Env:Path -ErrorAction SilentlyContinue
Remove-Item Env:PATH -ErrorAction SilentlyContinue
$env:Path = $processPath

$firebaseDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $firebaseDirectory
$localState = Join-Path $firebaseDirectory ".firebase"
$configHome = Join-Path $localState "config"
$ownerCacheRoot = $env:USERPROFILE
$emulatorCache = Join-Path $ownerCacheRoot ".cache\firebase\emulators"
$firebaseCli = Join-Path $firebaseDirectory "node_modules\firebase-tools\lib\bin\firebase.js"
$emulatorInfo = Join-Path $firebaseDirectory "node_modules\firebase-tools\lib\emulator\downloadableEmulatorInfo.json"
$vitestCli = Join-Path $firebaseDirectory "node_modules\.bin\vitest.cmd"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$emulatorStdoutLog = Join-Path $localState "emulator.stdout.log"
$emulatorStderrLog = Join-Path $localState "emulator.stderr.log"
$apiStdoutLog = Join-Path $localState "api.stdout.log"
$apiStderrLog = Join-Path $localState "api.stderr.log"
$frontendStdoutLog = Join-Path $localState "frontend.stdout.log"
$frontendStderrLog = Join-Path $localState "frontend.stderr.log"
$emulatorPort = 8185
$authPort = 9099

New-Item -ItemType Directory -Force -Path $configHome | Out-Null
$env:FIREBASE_CLI_DISABLE_UPDATE_CHECK = "true"
$env:XDG_CONFIG_HOME = $configHome

if (-not $ownerCacheRoot -or -not (Test-Path -LiteralPath $emulatorInfo -PathType Leaf)) {
    throw "Firebase Emulator compatibility manifest is unavailable; refusing to launch."
}
$emulatorManifest = Get-Content -LiteralPath $emulatorInfo -Raw | ConvertFrom-Json
$requiredFirestore = $emulatorManifest.firestore
$requiredFirestoreJar = Join-Path $emulatorCache $requiredFirestore.downloadPathRelativeToCacheDir
if (-not (Test-Path -LiteralPath $requiredFirestoreJar -PathType Leaf)) {
    throw "Required compatible Firestore Emulator $($requiredFirestore.version) is absent from the standard cache; refusing to launch."
}
if ((Get-Item -LiteralPath $requiredFirestoreJar).Length -le 0) {
    throw "Required compatible Firestore Emulator $($requiredFirestore.version) is empty; refusing to launch."
}
$env:FIREBASE_EMULATORS_PATH = $emulatorCache

$launcher = $null
$apiProcess = $null
$frontendProcess = $null
$testExitCode = 1
$preexistingEmulatorPids = @(
    netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$emulatorPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        ForEach-Object { [int]$_.Matches[0].Groups[1].Value }
)
$preexistingAuthPids = @(
    netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$authPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        ForEach-Object { [int]$_.Matches[0].Groups[1].Value }
)

function Get-SanitizedLogTail([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return "[log unavailable]"
    }
    $tail = Get-Content -LiteralPath $path -Tail 40 -ErrorAction SilentlyContinue
    if (-not $tail) {
        return "[log empty]"
    }
    return (($tail | ForEach-Object {
        $_ -replace '(?i)(password|token|secret|private[_-]?key|client[_-]?email)(\s*[:=]\s*)\S+', '$1$2[REDACTED]'
    }) -join [Environment]::NewLine)
}

function Stop-WithLauncherDiagnostics([string]$message) {
    $stdoutTail = Get-SanitizedLogTail $emulatorStdoutLog
    $stderrTail = Get-SanitizedLogTail $emulatorStderrLog
    throw "$message`n--- emulator stdout tail ---`n$stdoutTail`n--- emulator stderr tail ---`n$stderrTail"
}

try {
    if ($preexistingEmulatorPids.Count -gt 0 -or $preexistingAuthPids.Count -gt 0) {
        throw "Local Emulator ports are already in use; refusing to manage owner-started services."
    }
    Set-Content -LiteralPath $emulatorStdoutLog -Value "" -NoNewline
    Set-Content -LiteralPath $emulatorStderrLog -Value "" -NoNewline
    $launcher = Start-Process `
        -FilePath (Get-Command node.exe).Source `
        -ArgumentList @(
            $firebaseCli,
            "emulators:start",
            "--project", "demo-complaintguard",
            "--only", "auth,firestore"
        ) `
        -WorkingDirectory $repositoryRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $emulatorStdoutLog `
        -RedirectStandardError $emulatorStderrLog `
        -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($launcher.HasExited) {
            Stop-WithLauncherDiagnostics "Firebase Emulator launcher exited with code $($launcher.ExitCode) before Firestore became ready."
        }
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $client.Connect("127.0.0.1", $emulatorPort)
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        } finally {
            $client.Dispose()
        }
    }
    if (-not $ready) {
        Stop-WithLauncherDiagnostics "Firestore Emulator did not listen on 127.0.0.1:$emulatorPort."
    }

    $authDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $authReady = $false
    while ([DateTime]::UtcNow -lt $authDeadline) {
        if ($launcher.HasExited) {
            Stop-WithLauncherDiagnostics "Firebase Emulator launcher exited with code $($launcher.ExitCode) before Auth became ready."
        }
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $client.Connect("127.0.0.1", $authPort)
            $authReady = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        } finally {
            $client.Dispose()
        }
    }
    if (-not $authReady) {
        Stop-WithLauncherDiagnostics "Auth Emulator did not listen on 127.0.0.1:$authPort."
    }

    $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:$emulatorPort"
    $env:FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:$authPort"
    $env:APP_ENV = "local-emulator"
    $env:GCLOUD_PROJECT = "demo-complaintguard"
    Push-Location $firebaseDirectory
    try {
        & (Get-Command node.exe).Source (Join-Path $firebaseDirectory "seed-emulator.mjs")
        if ($LASTEXITCODE -ne 0) { throw "Emulator seeding failed." }
        & $vitestCli run "auth-emulator.test.js" --reporter verbose
        $testExitCode = $LASTEXITCODE
        if ($testExitCode -eq 0) {
            & $vitestCli run "firestore.rules.test.js" --reporter verbose
            $testExitCode = $LASTEXITCODE
        }
        if ($testExitCode -eq 0) {
            $env:PYTHONDONTWRITEBYTECODE = "1"
            Push-Location (Join-Path $repositoryRoot "ml-api")
            try {
                & $python -m pytest `
                    -p no:cacheprovider `
                    "tests\test_firestore_emulator_adapters.py" `
                    -q
                $testExitCode = $LASTEXITCODE
            } finally {
                Pop-Location
            }
        }
        if ($testExitCode -eq 0) {
            Push-Location (Join-Path $repositoryRoot "ml-api")
            try {
                & $python -m pytest `
                    -p no:cacheprovider `
                    "tests\test_admin_lifecycle_emulator.py" `
                    -q
                $testExitCode = $LASTEXITCODE
            } finally {
                Pop-Location
            }
        }
        if ($testExitCode -eq 0) {
            $env:FIREBASE_CONFIG = '{"projectId":"demo-complaintguard"}'
            $env:GOOGLE_CLOUD_PROJECT = "demo-complaintguard"
            $env:NEXT_PUBLIC_FIREBASE_API_KEY = "emulator-only"
            $env:NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN = "demo-complaintguard.firebaseapp.com"
            $env:NEXT_PUBLIC_FIREBASE_PROJECT_ID = "demo-complaintguard"
            $env:NEXT_PUBLIC_FIREBASE_APP_ID = "1:000:web:emulator"
            $env:NEXT_PUBLIC_APP_ENV = "local-emulator"
            $env:NEXT_PUBLIC_USE_FIREBASE_EMULATORS = "true"
            $env:NEXT_PUBLIC_ML_API_URL = "http://127.0.0.1:8000"
            $env:COMPLAINTGUARD_EMULATOR_IDENTITIES = Join-Path $localState "seeded-identities.json"

            $apiProcess = Start-Process `
                -FilePath $python `
                -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
                -WorkingDirectory (Join-Path $repositoryRoot "ml-api") `
                -WindowStyle Hidden `
                -RedirectStandardOutput $apiStdoutLog `
                -RedirectStandardError $apiStderrLog `
                -PassThru
            $frontendProcess = Start-Process `
                -FilePath (Get-Command node.exe).Source `
                -ArgumentList @((Join-Path $repositoryRoot "frontend\node_modules\next\dist\bin\next"), "dev", "-H", "127.0.0.1", "-p", "3000") `
                -WorkingDirectory (Join-Path $repositoryRoot "frontend") `
                -WindowStyle Hidden `
                -RedirectStandardOutput $frontendStdoutLog `
                -RedirectStandardError $frontendStderrLog `
                -PassThru

            foreach ($service in @(@("127.0.0.1", 8000), @("127.0.0.1", 3000))) {
                $serviceReady = $false
                $serviceDeadline = [DateTime]::UtcNow.AddSeconds(60)
                while ([DateTime]::UtcNow -lt $serviceDeadline) {
                    $client = [System.Net.Sockets.TcpClient]::new()
                    try {
                        $client.Connect($service[0], $service[1])
                        $serviceReady = $true
                        break
                    } catch {
                        Start-Sleep -Milliseconds 500
                    } finally {
                        $client.Dispose()
                    }
                }
                if (-not $serviceReady) { throw "Service port $($service[1]) did not start." }
            }

            Push-Location (Join-Path $repositoryRoot "frontend")
            try {
                & npm.cmd run test:e2e
                $testExitCode = $LASTEXITCODE
            } finally {
                Pop-Location
            }
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $listenerLine = netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$emulatorPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        Select-Object -First 1
    if ($listenerLine -and $listenerLine.Matches.Count -gt 0) {
        $emulatorPid = [int]$listenerLine.Matches[0].Groups[1].Value
        if ($preexistingEmulatorPids -notcontains $emulatorPid) {
            Stop-Process -Id $emulatorPid -Force -ErrorAction SilentlyContinue
        }
    }
    $authListenerLine = netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$authPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        Select-Object -First 1
    if ($authListenerLine -and $authListenerLine.Matches.Count -gt 0) {
        $authPid = [int]$authListenerLine.Matches[0].Groups[1].Value
        if ($preexistingAuthPids -notcontains $authPid) {
            Stop-Process -Id $authPid -Force -ErrorAction SilentlyContinue
        }
    }
    if ($launcher -and -not $launcher.HasExited) {
        Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
    }
}

exit $testExitCode
