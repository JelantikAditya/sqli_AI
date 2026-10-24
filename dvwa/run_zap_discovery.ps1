param(
    [ValidateSet("low", "medium", "high", "impossible")]
    [string]$SecurityLevel = "high",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportFile = "zap-discovery-$SecurityLevel-$timestamp.json"
$harFile = "zap-discovery-$SecurityLevel-$timestamp.har"
$planFile = "zap-discovery-$SecurityLevel-$timestamp.yaml"
$resultsDirectory = Join-Path $PSScriptRoot "..\results\zap"
$templatePath = Join-Path $PSScriptRoot "zap-auth.template.yaml"
$planPath = Join-Path $resultsDirectory $planFile
$logPath = Join-Path $resultsDirectory "zap-discovery-$SecurityLevel-$timestamp.log"
New-Item -ItemType Directory -Path $resultsDirectory -Force | Out-Null
if (-not $PythonExecutable) {
    $localPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}

# Materialize runtime values before ZAP parses regex tests and request bodies.
$plan = Get-Content -LiteralPath $templatePath -Raw
$plan = $plan.Replace("__DVWA_SECURITY_LEVEL__", $SecurityLevel)
$plan = $plan.Replace("__ZAP_REPORT_FILE__", $reportFile)
$plan = $plan.Replace("__ZAP_HAR_FILE__", $harFile)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($planPath, $plan, $utf8NoBom)

$previousPlan = $env:ZAP_PLAN_FILE
$previousLevel = $env:DVWA_SECURITY_LEVEL
$previousZapApiKey = $env:ZAP_API_KEY
$previousErrorActionPreference = $ErrorActionPreference
try {
    # Recreate only the DVWA web container so new ZAP sessions start at the
    # requested level. The database container and its volume are left intact.
    $env:DVWA_SECURITY_LEVEL = $SecurityLevel
    $env:ZAP_PLAN_FILE = $planFile
    # Compose validates inactive services too. Supply an inert interpolation
    # value only when no ZAP API key is configured; the zap-api profile is not
    # selected by this discovery command and this value is never used as a key.
    if (-not $env:ZAP_API_KEY) {
        $env:ZAP_API_KEY = "unused-zap-profile-" + [guid]::NewGuid().ToString("N")
    }

    $ErrorActionPreference = "Continue"
    $composeOutput = docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile up -d --force-recreate dvwa 2>&1
    $composeExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $composeOutput | Out-File -LiteralPath $logPath -Encoding utf8
    if ($composeExitCode -ne 0) {
        throw "Could not prepare DVWA at level $SecurityLevel."
    }

    $ErrorActionPreference = "Continue"
    $zapOutput = docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile run --rm zap 2>&1
    $zapExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $zapOutput | Out-File -LiteralPath $logPath -Append -Encoding utf8
    if ($zapExitCode -ne 0) {
        throw "ZAP automation failed with exit code $zapExitCode. Inspect the local log $logPath."
    }

    & $PythonExecutable (Join-Path $PSScriptRoot "parse_zap_report.py") `
        (Join-Path $resultsDirectory $reportFile) `
        --har-report (Join-Path $resultsDirectory $harFile) `
        --security-level $SecurityLevel --scan-mode passive --require-complete-inputs
    if ($LASTEXITCODE -ne 0) {
        throw "ZAP completed but verified input coverage is incomplete. See the normalized report."
    }
    Write-Output "ZAP report: $PSScriptRoot\..\results\zap\$reportFile"
    Write-Output "ZAP HAR (local only): $PSScriptRoot\..\results\zap\$harFile"
    Write-Output "ZAP plan: $PSScriptRoot\..\results\zap\$planFile"
}
finally {
    if ($null -eq $previousPlan) {
        Remove-Item Env:ZAP_PLAN_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:ZAP_PLAN_FILE = $previousPlan
    }

    if ($null -eq $previousLevel) {
        Remove-Item Env:DVWA_SECURITY_LEVEL -ErrorAction SilentlyContinue
    }
    else {
        $env:DVWA_SECURITY_LEVEL = $previousLevel
    }

    if ($null -eq $previousZapApiKey) {
        Remove-Item Env:ZAP_API_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:ZAP_API_KEY = $previousZapApiKey
    }

    $ErrorActionPreference = $previousErrorActionPreference
}
