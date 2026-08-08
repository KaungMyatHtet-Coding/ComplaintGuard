$ErrorActionPreference = "Stop"

$firebaseDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $firebaseDirectory
$localState = Join-Path $firebaseDirectory ".firebase"
$configHome = Join-Path $localState "config"
$emulatorCache = Join-Path $localState "emulators"
$firebaseCli = Join-Path $firebaseDirectory "node_modules\firebase-tools\lib\bin\firebase.js"
$vitestCli = Join-Path $firebaseDirectory "node_modules\.bin\vitest.cmd"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$stdoutLog = Join-Path $localState "firebase-cli.stdout.log"
$stderrLog = Join-Path $localState "firebase-cli.stderr.log"
$emulatorPort = 8185

New-Item -ItemType Directory -Force -Path $configHome, $emulatorCache | Out-Null
$env:FIREBASE_CLI_DISABLE_UPDATE_CHECK = "true"
$env:FIREBASE_EMULATORS_PATH = $emulatorCache
$env:XDG_CONFIG_HOME = $configHome

$launcher = $null
$testExitCode = 1
try {
    $launcher = Start-Process `
        -FilePath (Get-Command node.exe).Source `
        -ArgumentList @(
            $firebaseCli,
            "emulators:start",
            "--project", "demo-complaintguard",
            "--only", "firestore"
        ) `
        -WorkingDirectory $repositoryRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
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
        $details = if (Test-Path $stderrLog) { Get-Content $stderrLog -Raw } else { "" }
        throw "Firestore Emulator did not listen on 127.0.0.1:$emulatorPort. $details"
    }

    $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:$emulatorPort"
    $env:GCLOUD_PROJECT = "demo-complaintguard"
    Push-Location $firebaseDirectory
    try {
        & $vitestCli run --reporter verbose
        $testExitCode = $LASTEXITCODE
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
    } finally {
        Pop-Location
    }
} finally {
    $listenerLine = netstat.exe -ano |
        Select-String -Pattern "127\.0\.0\.1:$emulatorPort\s+0\.0\.0\.0:0\s+LISTENING\s+(\d+)" |
        Select-Object -First 1
    if ($listenerLine -and $listenerLine.Matches.Count -gt 0) {
        $emulatorPid = [int]$listenerLine.Matches[0].Groups[1].Value
        Stop-Process -Id $emulatorPid -Force -ErrorAction SilentlyContinue
    }
    if ($launcher -and -not $launcher.HasExited) {
        Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
    }
}

exit $testExitCode
