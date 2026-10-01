param(
    [ValidateSet("low", "medium", "high", "impossible")]
    [string]$SecurityLevel = "high"
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportFile = "zap-discovery-$SecurityLevel-$timestamp.json"
$planFile = "zap-discovery-$SecurityLevel-$timestamp.yaml"
$resultsDirectory = Join-Path $PSScriptRoot "..\results\zap"
$templatePath = Join-Path $PSScriptRoot "zap-auth.template.yaml"
$planPath = Join-Path $resultsDirectory $planFile

# Materialize runtime values before ZAP parses regex tests and request bodies.
$plan = Get-Content -LiteralPath $templatePath -Raw
$plan = $plan.Replace("__DVWA_SECURITY_LEVEL__", $SecurityLevel)
$plan = $plan.Replace("__ZAP_REPORT_FILE__", $reportFile)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($planPath, $plan, $utf8NoBom)

$previousPlan = $env:ZAP_PLAN_FILE
$previousLevel = $env:DVWA_SECURITY_LEVEL
try {
    # Recreate only the DVWA web container so new ZAP sessions start at the
    # requested level. The database container and its volume are left intact.
    $env:DVWA_SECURITY_LEVEL = $SecurityLevel
    $env:ZAP_PLAN_FILE = $planFile

    docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile up -d --force-recreate dvwa
    if ($LASTEXITCODE -ne 0) {
        throw "Could not prepare DVWA at level $SecurityLevel."
    }

    docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile run --rm zap
    if ($LASTEXITCODE -ne 0) {
        throw "ZAP automation failed with exit code $LASTEXITCODE. No successful run should be recorded."
    }

    Write-Output "ZAP report: $PSScriptRoot\..\results\zap\$reportFile"
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
}
