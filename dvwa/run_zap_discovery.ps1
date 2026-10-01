param(
    [ValidateSet("low", "medium", "high", "impossible")]
    [string]$SecurityLevel = "high"
)

$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportFile = "zap-discovery-$SecurityLevel-$timestamp.json"

$previousLevel = $env:DVWA_SECURITY_LEVEL
$previousReport = $env:ZAP_REPORT_FILE
try {
    # Compose reads dvwa/.env; these values choose this run's level and output name.
    $env:DVWA_SECURITY_LEVEL = $SecurityLevel
    $env:ZAP_REPORT_FILE = $reportFile

    docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile run --rm zap
    if ($LASTEXITCODE -ne 0) {
        throw "ZAP automation failed with exit code $LASTEXITCODE. No successful run should be recorded."
    }

    Write-Output "ZAP report: $PSScriptRoot\..\results\zap\$reportFile"
}
finally {
    if ($null -eq $previousLevel) {
        Remove-Item Env:DVWA_SECURITY_LEVEL -ErrorAction SilentlyContinue
    }
    else {
        $env:DVWA_SECURITY_LEVEL = $previousLevel
    }

    if ($null -eq $previousReport) {
        Remove-Item Env:ZAP_REPORT_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:ZAP_REPORT_FILE = $previousReport
    }
}
