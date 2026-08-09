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
$emulatorCache = Join-Path $localState "emulators"
$firebaseCli = Join-Path $firebaseDirectory "node_modules\firebase-tools\lib\bin\firebase.js"
$vitestCli = Join-Path $firebaseDirectory "node_modules\.bin\vitest.cmd"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$apiStdoutLog = Join-Path $localState "api.stdout.log"
$apiStderrLog = Join-Path $localState "api.stderr.log"
$frontendStdoutLog = Join-Path $localState "frontend.stdout.log"
$frontendStderrLog = Join-Path $localState "frontend.stderr.log"
$emulatorPort = 8185
$authPort = 9099

New-Item -ItemType Directory -Force -Path $configHome, $emulatorCache | Out-Null
$env:FIREBASE_CLI_DISABLE_UPDATE_CHECK = "true"
$env:FIREBASE_EMULATORS_PATH = $emulatorCache
$env:XDG_CONFIG_HOME = $configHome

$launcher = $null
$apiProcess = $null
$frontendProcess = $null
$testExitCode = 1
try {
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
        -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($launcher.HasExited) {
            throw "Firebase Emulator launcher exited with code $($launcher.ExitCode) before Firestore became ready."
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
        throw "Firestore Emulator did not listen on 127.0.0.1:$emulatorPort."
    }

    $authDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $authReady = $false
    while ([DateTime]::UtcNow -lt $authDeadline) {
        if ($launcher.HasExited) {
            throw "Firebase Emulator launcher exited with code $($launcher.ExitCode) before Auth became ready."
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
        throw "Auth Emulator did not listen on 127.0.0.1:$authPort."
    }

    $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:$emulatorPort"
    $env:FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:$authPort"
    $env:GCLOUD_PROJECT = "demo-complaintguard"
    Push-Location $firebaseDirectory
    try {
        & (Get-Command node.exe).Source (Join-Path $firebaseDirectory "seed-emulator.mjs")
        if ($LASTEXITCODE -ne 0) { throw "Emulator seeding failed." }
        $firstSeedUids = @(
            (Get-Content (Join-Path $localState "seeded-identities.json") -Raw |
                ConvertFrom-Json).identities.uid
        )
        & $vitestCli run "firestore.rules.test.js" --reporter verbose
        $testExitCode = $LASTEXITCODE
        if ($testExitCode -eq 0) {
            & (Get-Command node.exe).Source `
                (Join-Path $firebaseDirectory "seed-emulator.mjs") `
                "--reset-firestore"
            if ($LASTEXITCODE -ne 0) { throw "Emulator reseeding failed." }
            $secondSeedUids = @(
                (Get-Content (Join-Path $localState "seeded-identities.json") -Raw |
                    ConvertFrom-Json).identities.uid
            )
            if (Compare-Object $firstSeedUids $secondSeedUids) {
                throw "Emulator reseeding changed stable demo Auth UIDs."
            }
            & $vitestCli run "auth-emulator.test.js" --reporter verbose
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
        Stop-Process -Id $emulatorPid -Force -ErrorAction SilentlyContinue
    }
    $authListenerLine = netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$authPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        Select-Object -First 1
    if ($authListenerLine -and $authListenerLine.Matches.Count -gt 0) {
        $authPid = [int]$authListenerLine.Matches[0].Groups[1].Value
        Stop-Process -Id $authPid -Force -ErrorAction SilentlyContinue
    }
    if ($launcher -and -not $launcher.HasExited) {
        Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
    }
}

exit $testExitCode
