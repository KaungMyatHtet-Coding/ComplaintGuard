param(
    [switch]$IncludeEnvironmentDependent
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$frontendRoot = Join-Path $repositoryRoot "frontend"
$apiRoot = Join-Path $repositoryRoot "ml-api"
$firebaseRoot = Join-Path $repositoryRoot "firebase"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$mandatoryFailures = [System.Collections.Generic.List[string]]::new()
$environmentFailures = [System.Collections.Generic.List[string]]::new()

function Invoke-ProjectCheck {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$WorkingDirectory,
        [Parameter(Mandatory)] [scriptblock]$Command,
        [switch]$EnvironmentDependent
    )
    Write-Host "`n=== $Name ==="
    Push-Location $WorkingDirectory
    try {
        & $Command
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        $code = 1
    } finally {
        Pop-Location
    }
    if ($code -eq 0) {
        Write-Host "PASS: $Name"
        return
    }
    Write-Host "FAIL ($code): $Name"
    if ($EnvironmentDependent) {
        $environmentFailures.Add("$Name (exit $code)")
    } else {
        $mandatoryFailures.Add("$Name (exit $code)")
    }
}

function Test-ExactHash {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Expected,
        [switch]$Optional
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        if ($Optional) {
            Write-Host "SKIP: $Name is not present (ignored local artifact)."
            return
        }
        $mandatoryFailures.Add("$Name is missing")
        Write-Host "FAIL: $Name is missing."
        return
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -eq $Expected) {
        Write-Host "PASS: $Name SHA-256 $actual"
    } else {
        Write-Host "FAIL: $Name SHA-256 mismatch."
        $mandatoryFailures.Add("$Name SHA-256 mismatch")
    }
}

Write-Host "ComplaintGuard final verification"
Write-Host "Repository: $repositoryRoot"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Host "FAIL: repository virtual-environment Python is missing."
    exit 1
}

Invoke-ProjectCheck "Frontend tests" $frontendRoot { & npm.cmd test }
Invoke-ProjectCheck "TypeScript" $frontendRoot { & npm.cmd run typecheck }
Invoke-ProjectCheck "ESLint" $frontendRoot { & npm.cmd run lint }
Invoke-ProjectCheck "Production build" $frontendRoot { & npm.cmd run build }

Invoke-ProjectCheck "Focused Day 18 evaluation and similarity tests" $repositoryRoot {
    & $python -m pytest `
        "scripts/tests/test_evaluate_department_model.py" `
        "scripts/tests/test_historical_similarity.py" `
        -p no:cacheprovider
}
Invoke-ProjectCheck "Backend tests" $apiRoot {
    & $python -m pytest tests -p no:cacheprovider
}
Invoke-ProjectCheck "Ruff check" $repositoryRoot {
    & $python -m ruff check scripts ml-api/app ml-api/tests
}
Invoke-ProjectCheck "Ruff format check" $repositoryRoot {
    & $python -m ruff format --check scripts ml-api/app ml-api/tests
}

Write-Host "`n=== Complete root scripts suite dependency preflight ==="
& $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('matplotlib') else 1)"
if ($LASTEXITCODE -eq 0) {
    Invoke-ProjectCheck "Complete root scripts suite" $repositoryRoot {
        & $python -m pytest scripts/tests -p no:cacheprovider
    }
} else {
    Write-Host "SKIP: .venv cannot import matplotlib; no package was installed and no global Python was substituted."
}

if ($IncludeEnvironmentDependent) {
    Invoke-ProjectCheck "Firebase rules, adapters, and Playwright E2E" $firebaseRoot {
        & npm.cmd test
    } -EnvironmentDependent
} else {
    Write-Host "`nSKIP: Firebase/Playwright verification is environment-dependent. Rerun with -IncludeEnvironmentDependent after checking Java, Chrome, ports, local dependencies, and the ignored model."
}

Write-Host "`n=== Artifact integrity ==="
$evaluationSource = Join-Path $repositoryRoot "evaluation\day18\model_evaluation_v1.json"
$evaluationGenerated = Join-Path $frontendRoot "src\generated\model_evaluation_v1.json"
if ((Test-Path $evaluationSource) -and (Test-Path $evaluationGenerated)) {
    $sourceHash = (Get-FileHash $evaluationSource -Algorithm SHA256).Hash
    $generatedHash = (Get-FileHash $evaluationGenerated -Algorithm SHA256).Hash
    if ($sourceHash -eq $generatedHash) {
        Write-Host "PASS: source/generated evaluation SHA-256 $sourceHash"
    } else {
        Write-Host "FAIL: source/generated evaluation hashes differ."
        $mandatoryFailures.Add("evaluation hash mismatch")
    }
} else {
    Write-Host "FAIL: required evaluation source or generated artifact is missing."
    $mandatoryFailures.Add("required evaluation artifact missing")
}

Test-ExactHash "Frozen model" `
    (Join-Path $repositoryRoot "models\generated\cfpb_department_model_v1.joblib") `
    "BAFC086FE5B11BDCC5CBC4F04F3F3F222DE8CBAD27FE66D62A6685CC30F953D5" `
    -Optional
Test-ExactHash "Historical similarity index" `
    (Join-Path $repositoryRoot "models\generated\cfpb_similarity_test_v1.joblib") `
    "9DA4320600965C40FA8420E56B67FBBEB1EE8B93A0D285A3FA93FF7936B377C2" `
    -Optional

Write-Host "`n=== UTF-8 and tracked-file safety ==="
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$invalidUtf8 = [System.Collections.Generic.List[string]]::new()
$tracked = & git -C $repositoryRoot ls-files
foreach ($relative in $tracked) {
    if ($relative -notmatch '\.(md|txt|json|csv|ts|tsx|js|mjs|py|css|ps1|yml|yaml|toml)$') { continue }
    $path = Join-Path $repositoryRoot $relative
    try { $null = $utf8.GetString([System.IO.File]::ReadAllBytes($path)) }
    catch { $invalidUtf8.Add($relative) }
}
if ($invalidUtf8.Count -eq 0) { Write-Host "PASS: tracked text files are valid UTF-8." }
else {
    Write-Host "FAIL: invalid UTF-8 files: $($invalidUtf8 -join ', ')"
    $mandatoryFailures.Add("invalid UTF-8")
}

$forbiddenTracked = $tracked | Where-Object {
    ($_ -match '(^|/)\.env($|\.)' -and $_ -notmatch '\.env\.example$') -or
    $_ -match '\.(joblib|pkl|pickle|pem|key|p12|pfx)$' -or
    $_ -match '(^|/)(node_modules|\.next|\.venv|__pycache__|data/raw|data/interim|models/generated)/'
}
if ($forbiddenTracked.Count -eq 0) { Write-Host "PASS: no forbidden local artifacts are tracked." }
else {
    Write-Host "FAIL: forbidden tracked paths: $($forbiddenTracked -join ', ')"
    $mandatoryFailures.Add("forbidden tracked artifacts")
}

Push-Location $repositoryRoot
try {
    $secretFiles = & git grep -l -I -E `
        'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|firebase-adminsdk|client_secret|refresh_token' `
        -- . ':!.gitignore' ':!docs/final_test_report.md' ':!scripts/verify_final.ps1' 2>$null
    $grepCode = $LASTEXITCODE
} finally { Pop-Location }
if ($grepCode -eq 1) { Write-Host "PASS: tracked secret/private-key signature scan found no match." }
elseif ($grepCode -eq 0) {
    Write-Host "FAIL: secret-like signatures found in tracked files: $($secretFiles -join ', ')"
    $mandatoryFailures.Add("tracked secret-like signature")
} else {
    Write-Host "FAIL: tracked secret scan could not run."
    $mandatoryFailures.Add("tracked secret scan error")
}

Write-Host "`n=== Git integrity ==="
Push-Location $repositoryRoot
try {
    & git diff --check
    if ($LASTEXITCODE -ne 0) { $mandatoryFailures.Add("git diff --check") }
    & git status --short
    & git diff --stat
    & git diff --name-status
} finally { Pop-Location }

Write-Host "`n=== Summary ==="
if ($environmentFailures.Count -gt 0) {
    Write-Host "Environment-dependent failures: $($environmentFailures -join '; ')"
}
if ($mandatoryFailures.Count -gt 0) {
    Write-Host "Mandatory failures: $($mandatoryFailures -join '; ')"
    exit 1
}
Write-Host "All executed mandatory checks passed."
if (-not $IncludeEnvironmentDependent) {
    Write-Host "Firebase/Playwright was skipped by design; its direct result must be reported separately."
}
exit 0
