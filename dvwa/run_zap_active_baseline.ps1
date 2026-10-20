param(
    [ValidateSet("low", "medium", "high", "impossible")]
    [string[]]$SecurityLevels = @("low", "medium", "high", "impossible"),
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
$templatePath = Join-Path $PSScriptRoot "zap-active-sqli.template.yaml"
$resultsDirectory = Join-Path $PSScriptRoot "..\results\zap"
$summaryDirectory = Join-Path $PSScriptRoot "..\results\raw\u06-zap-active-baseline-v3-20261016"
$pythonExecutable = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $resultsDirectory -Force | Out-Null

$previousPlan = $env:ZAP_PLAN_FILE
$previousLevel = $env:DVWA_SECURITY_LEVEL
try {
    foreach ($level in $SecurityLevels) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $stem = "u06-zap-active-sqli-$level-$stamp"
        $planFile = "$stem.yaml"
        $reportFile = "$stem.json"
        $harFile = "$stem.har"
        $logFile = "$stem.log"
        $planPath = Join-Path $resultsDirectory $planFile
        $logPath = Join-Path $resultsDirectory $logFile

        $plan = Get-Content -LiteralPath $templatePath -Raw
        $plan = $plan.Replace("__DVWA_SECURITY_LEVEL__", $level)
        $plan = $plan.Replace("__ZAP_REPORT_FILE__", $reportFile)
        $plan = $plan.Replace("__ZAP_HAR_FILE__", $harFile)
        $inputSeeds = switch ($level) {
            { $_ -in @("low", "impossible") } {
                @'
  - type: requestor
    parameters:
      user: dvwa-local-user
    requests:
      - name: Seed GET SQLi module input
        url: http://dvwa/vulnerabilities/sqli/?id=1&Submit=Submit
        method: GET
      - name: Seed GET blind SQLi module input
        url: http://dvwa/vulnerabilities/sqli_blind/?id=1&Submit=Submit
        method: GET
'@
            }
            "medium" {
                @'
  - type: requestor
    parameters:
      user: dvwa-local-user
    requests:
      - name: Seed POST SQLi module input
        url: http://dvwa/vulnerabilities/sqli/
        method: POST
        headers:
          - "Content-Type: application/x-www-form-urlencoded"
        data: id=1&Submit=Submit
      - name: Seed POST blind SQLi module input
        url: http://dvwa/vulnerabilities/sqli_blind/
        method: POST
        headers:
          - "Content-Type: application/x-www-form-urlencoded"
        data: id=1&Submit=Submit
'@
            }
            "high" {
                @'
  - type: requestor
    parameters:
      user: dvwa-local-user
    requests:
      - name: Seed high-level SQLi session helper input
        url: http://dvwa/vulnerabilities/sqli/session-input.php
        method: POST
        headers:
          - "Content-Type: application/x-www-form-urlencoded"
        data: id=1&Submit=Submit
      - name: Seed high-level blind SQLi cookie helper input
        url: http://dvwa/vulnerabilities/sqli_blind/cookie-input.php
        method: POST
        headers:
          - "Content-Type: application/x-www-form-urlencoded"
        data: id=1&Submit=Submit
'@
            }
        }
        $plan = $plan.Replace("__DVWA_INPUT_SEEDS__", $inputSeeds)
        $scanPaths = switch ($level) {
            { $_ -in @("low", "medium", "impossible") } {
                @("/vulnerabilities/sqli/", "/vulnerabilities/sqli_blind/")
            }
            "high" {
                @("/vulnerabilities/sqli/session-input.php",
                  "/vulnerabilities/sqli_blind/cookie-input.php")
            }
        }
        $scanJobs = @()
        for ($scanIndex = 0; $scanIndex -lt $scanPaths.Count; $scanIndex++) {
            $tests = ""
            if ($scanIndex -eq ($scanPaths.Count - 1)) {
                $tests = @'
    tests:
      - name: Generic SQL injection rule sent requests
        type: stats
        statistic: stats.ascan.40018.urls
        operator: '>='
        value: 1
        onFail: error
      - name: MySQL timing SQL injection rule sent requests
        type: stats
        statistic: stats.ascan.40019.urls
        operator: '>='
        value: 1
        onFail: error
'@
            }
            $scanJobs += @"
  - type: activeScan
    parameters:
      context: dvwa-sqli-active
      user: dvwa-local-user
      url: http://dvwa$($scanPaths[$scanIndex])
      policy: dvwa-sqli-only-low
      maxRuleDurationInMins: 3
      maxScanDurationInMins: 5
      delayInMs: 100
      threadPerHost: 1
      maxAlertsPerRule: 20
      handleAntiCSRFTokens: true
      injectPluginIdInHeader: true
$tests
"@
        }
        $plan = $plan.Replace("__DVWA_ACTIVE_SCAN_JOBS__", ($scanJobs -join "`n"))
        [System.IO.File]::WriteAllText($planPath, $plan, $utf8NoBom)

        $env:DVWA_SECURITY_LEVEL = $level
        $env:ZAP_PLAN_FILE = $planFile

        if (-not $ValidateOnly) {
            # Recreate only DVWA's web container. Keep the local DB service and volume.
            docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile up -d --force-recreate dvwa | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not prepare local DVWA at level $level."
            }

            $ready = $false
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                try {
                    $response = Invoke-WebRequest -Uri "http://127.0.0.1:4280/login.php" -TimeoutSec 3
                    if ($response.StatusCode -eq 200) { $ready = $true; break }
                }
                catch { Start-Sleep -Seconds 2 }
            }
            if (-not $ready) { throw "Local DVWA did not become ready at level $level." }
        }

        if ($ValidateOnly) {
            docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile run --no-deps --rm zap `
                zap.sh -cmd -autocheck "/zap/out/$planFile"
            if ($LASTEXITCODE -ne 0) {
                throw "ZAP rejected the automation plan for level $level."
            }
            Write-Output "Validated plan: $planPath"
            continue
        }

        docker compose --project-directory $PSScriptRoot --profile zap -f $composeFile run --rm zap *> $logPath
        if ($LASTEXITCODE -ne 0) {
            throw "ZAP active baseline failed at level $level. Inspect local log $logPath."
        }

        if (-not (Test-Path -LiteralPath $pythonExecutable)) {
            $pythonExecutable = "python"
        }
        $summaryPath = Join-Path $summaryDirectory "$stem-summary.json"
        & $pythonExecutable (Join-Path $PSScriptRoot "summarize_zap_active.py") `
            (Join-Path $resultsDirectory $reportFile) `
            (Join-Path $resultsDirectory $harFile) `
            $logPath `
            --security-level $level --plan $planPath --output $summaryPath
        if ($LASTEXITCODE -ne 0) {
            throw "ZAP completed at level $level, but its local coverage summary failed."
        }

        Write-Output "Completed SQLi active baseline for $level. Report: $(Join-Path $resultsDirectory $reportFile)"
        Write-Output "Local-only HAR: $(Join-Path $resultsDirectory $harFile)"
        Write-Output "Coverage summary: $summaryPath"
        Write-Output "Plan: $planPath"
    }
}
finally {
    if ($null -eq $previousPlan) {
        Remove-Item Env:ZAP_PLAN_FILE -ErrorAction SilentlyContinue
    }
    else { $env:ZAP_PLAN_FILE = $previousPlan }

    if ($null -eq $previousLevel) {
        Remove-Item Env:DVWA_SECURITY_LEVEL -ErrorAction SilentlyContinue
    }
    else { $env:DVWA_SECURITY_LEVEL = $previousLevel }
}
