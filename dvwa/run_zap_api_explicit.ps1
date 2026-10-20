param(
    [ValidateSet("low", "medium", "high", "impossible")]
    [string]$SecurityLevel = "medium"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
$templatePath = Join-Path $PSScriptRoot "zap-active-sqli.template.yaml"
$resultsDirectory = Join-Path $PSScriptRoot "..\results\zap"
$summaryDirectory = Join-Path $PSScriptRoot "..\results\raw\u06-zap-api-explicit-20261016"
$summaryScript = Join-Path $PSScriptRoot "summarize_zap_api_active.py"
$pythonExecutable = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$contextName = "dvwa-sqli-active"
$apiPortInContainer = 8080
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $resultsDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $summaryDirectory -Force | Out-Null

$previousPlan = $env:ZAP_PLAN_FILE
$previousLevel = $env:DVWA_SECURITY_LEVEL
$previousApiKey = $env:ZAP_API_KEY
$planPath = $null
$containerStarted = $false

function ConvertTo-ZapQueryString([hashtable]$Parameters) {
    $parts = foreach ($key in $Parameters.Keys) {
        "{0}={1}" -f [Uri]::EscapeDataString([string]$key), [Uri]::EscapeDataString([string]$Parameters[$key])
    }
    return ($parts -join "&")
}

function Invoke-ZapApi([string]$Path, [hashtable]$Parameters = @{}, [switch]$Raw, [switch]$AllowEmpty) {
    $query = @{} + $Parameters
    $queryString = ConvertTo-ZapQueryString $query
    $uri = "http://127.0.0.1:8080/$Path/?"
    $queryPrefix = if ($queryString) { "$queryString&" } else { "" }
    # Keep the API key inside the container environment, off the host command line.
    $command = 'wget -qO- "' + $uri + $queryPrefix + 'apikey=$ZAP_API_KEY"'
    $rawResponse = docker exec $script:zapContainerId sh -c $command
    if ($LASTEXITCODE -ne 0) {
        $requestExitCode = $LASTEXITCODE
        $diagnosticCommand = 'curl -sS --max-time 10 "' + $uri + $queryPrefix + 'apikey=$ZAP_API_KEY"'
        $diagnosticResponse = docker exec $script:zapContainerId sh -c $diagnosticCommand 2>$null
        $apiError = $diagnosticResponse -join "`n"
        throw "ZAP API request failed for $Path (wget exit $requestExitCode): $apiError"
    }
    $body = $rawResponse -join "`n"
    if ($Raw) { return [pscustomobject]@{ Content = $body } }
    if ([string]::IsNullOrWhiteSpace($body)) {
        if ($AllowEmpty) { return $null }
        throw "ZAP API returned an empty response for $Path."
    }
    $result = $body | ConvertFrom-Json
    if ($result.PSObject.Properties.Name -contains "code") {
        throw "ZAP API returned $($result.code): $($result.message)"
    }
    return $result
}

function Wait-ZapPlan([string]$PlanId, [int]$TimeoutSeconds = 900) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $poll = 0
    $missingPlanChecks = 0
    do {
        Start-Sleep -Seconds 2
        $poll++
        if (($poll % 15) -eq 0) { Write-Host "Waiting for ZAP setup plan $PlanId..." }
        try {
            $result = Invoke-ZapApi "JSON/automation/view/planProgress" @{ planId = $PlanId }
        }
        catch {
            if ($_.Exception.Message -match 'does_not_exist|no_implementor' -and $missingPlanChecks -lt 30) {
                $missingPlanChecks++
                if (($missingPlanChecks % 10) -eq 0) { Write-Host "Waiting for ZAP Automation progress view for plan $PlanId..." }
                continue
            }
            throw
        }
        $progress = if ($result.PSObject.Properties.Name -contains "planProgress") { $result.planProgress } else { $result }
        if ($progress.finished) {
            if (@($progress.error).Count -gt 0) {
                throw "ZAP setup plan reported errors: $(@($progress.error) -join '; ')"
            }
            return $progress
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for ZAP automation plan $PlanId."
}

function Wait-ZapScan([string]$ScanId, [int]$TimeoutSeconds = 900) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $poll = 0
    do {
        Start-Sleep -Seconds 3
        $poll++
        if (($poll % 10) -eq 0) { Write-Host "ZAP scan $ScanId is still running..." }
        $result = Invoke-ZapApi "JSON/ascan/view/status" @{ scanId = $ScanId }
        $status = [int]$result.status
        if ($status -ge 100) { return $status }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for ZAP active scan $ScanId."
}

function Start-ZapAutomationPlan([string]$ContainerPlanPath) {
    # The runPlan action accepts the mounted absolute path directly. Keeping its
    # slashes literal matches ZAP's working API request form for filePath.
    $command = 'wget -qO- "http://127.0.0.1:8080/JSON/automation/action/runPlan/?filePath=' +
        $ContainerPlanPath + '&apikey=$ZAP_API_KEY"'
    $raw = @()
    $requestExitCode = -1
    $requestError = ""
    for ($attempt = 0; $attempt -lt 6; $attempt++) {
        $raw = docker exec $script:zapContainerId sh -c $command
        $requestExitCode = $LASTEXITCODE
        if ($requestExitCode -eq 0) { break }
        $diagnosticCommand = 'curl -sS --max-time 10 "http://127.0.0.1:8080/JSON/automation/action/runPlan/?filePath=' +
            $ContainerPlanPath + '&apikey=$ZAP_API_KEY"'
        $diagnosticResponse = docker exec $script:zapContainerId sh -c $diagnosticCommand 2>$null
        $requestError = $diagnosticResponse -join "`n"
        if ($env:ZAP_API_KEY) { $requestError = $requestError.Replace($env:ZAP_API_KEY, "[redacted]") }
        if ($requestError -notmatch '"code"\s*:\s*"no_implementor"' -or $attempt -eq 5) { break }
        Start-Sleep -Seconds 3
    }
    $body = $raw -join "`n"
    $started = if ([string]::IsNullOrWhiteSpace($body)) { $null } else { $body | ConvertFrom-Json }
    $planId = if ($started) { $started.planId } else { $null }
    if ($null -eq $planId) {
        # Some Automation add-on builds return an empty action body. Recover the
        # asynchronous plan ID from the documented progress view when possible.
        foreach ($candidate in 0..20) {
            try {
                $progress = Invoke-ZapApi "JSON/automation/view/planProgress" @{ planId = [string]$candidate }
                $progressData = if ($progress.PSObject.Properties.Name -contains "planProgress") { $progress.planProgress } else { $progress }
                if ($null -ne $progressData.planId) { $planId = [string]$progressData.planId; break }
            }
            catch { }
        }
    }
    if ($null -eq $planId) {
        throw "ZAP runPlan did not yield a plan ID (request exit $requestExitCode); no matching plan progress was available. $requestError"
    }
    Write-Host "Started ZAP setup plan $planId."
    return Wait-ZapPlan ([string]$planId)
}

function Start-ZapExplicitScan([hashtable]$Target, [string]$ContextId, [string]$UserId) {
    $before = Invoke-ZapApi "JSON/ascan/view/scans"
    $beforeIds = @($before.scans | ForEach-Object { [string]$_.id })
    $targetUrl = "http://dvwa$($Target.path)"
    if ($Target.method -eq "GET") { $targetUrl += "?$($Target.query)" }
    $parameters = @{
        url = $targetUrl
        contextId = $ContextId
        userId = $UserId
        recurse = "false"
        scanPolicyName = "dvwa-sqli-only-low"
        method = $Target.method
    }
    if ($Target.method -eq "POST") { $parameters.postData = $Target.post_data }
    $started = Invoke-ZapApi "JSON/ascan/action/scanAsUser" $parameters -AllowEmpty
    $scanId = if ($started) { [string]$started.scan } else { $null }
    if ([string]::IsNullOrWhiteSpace($scanId)) {
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Seconds 1
            $after = Invoke-ZapApi "JSON/ascan/view/scans"
            $newScans = @($after.scans | Where-Object { $beforeIds -notcontains [string]$_.id })
            if ($newScans.Count -gt 0) {
                $scanId = [string]($newScans | Sort-Object { [int]$_.id } -Descending | Select-Object -First 1).id
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($scanId)) { throw "ZAP did not return a scan ID for $($Target.path)." }
    return $scanId
}

function Export-ZapHar([string]$FileName, [string]$HostPath) {
    $query = ConvertTo-ZapQueryString @{ baseurl = "http://dvwa"; start = "0"; count = "100000" }
    $containerPath = "/zap/out/$FileName"
    $uri = "http://127.0.0.1:8080/OTHER/exim/other/exportHar/?$query&apikey=`$ZAP_API_KEY"
    $command = 'curl -sS --fail-with-body --max-time 180 --output "' + $containerPath + '" "' + $uri + '"'
    docker exec $script:zapContainerId sh -c $command
    if ($LASTEXITCODE -ne 0) { throw "ZAP HAR export failed (docker exec exit $LASTEXITCODE)." }
    if (-not (Test-Path -LiteralPath $HostPath)) { throw "ZAP HAR export did not create $FileName." }
}

function Get-InputTargets([string]$Level) {
    if ($Level -eq "low") {
        return @(
            @{ path = "/vulnerabilities/sqli/"; method = "GET"; query = "id=1&Submit=Submit"; post_data = $null; name = "S1 low SQLi" },
            @{ path = "/vulnerabilities/sqli_blind/"; method = "GET"; query = "id=1&Submit=Submit"; post_data = $null; name = "S2-S3 low blind SQLi" }
        )
    }
    if ($Level -eq "medium") {
        return @(
            @{ path = "/vulnerabilities/sqli/"; method = "POST"; query = $null; post_data = "id=1&Submit=Submit"; name = "S4 medium SQLi" },
            @{ path = "/vulnerabilities/sqli_blind/"; method = "POST"; query = $null; post_data = "id=1&Submit=Submit"; name = "S5-S6 medium blind SQLi" }
        )
    }
    if ($Level -eq "high") {
        return @(
            @{ path = "/vulnerabilities/sqli/session-input.php"; method = "POST"; query = $null; post_data = "id=1&Submit=Submit"; name = "S7 high SQLi session helper" },
            @{ path = "/vulnerabilities/sqli_blind/cookie-input.php"; method = "POST"; query = $null; post_data = "id=1&Submit=Submit"; name = "S8-S9 high blind SQLi cookie helper" }
        )
    }
    return @(
        @{ path = "/vulnerabilities/sqli/"; method = "GET"; query = "id=1&Submit=Submit"; post_data = $null; name = "S10 impossible SQLi" },
        @{ path = "/vulnerabilities/sqli_blind/"; method = "GET"; query = "id=1&Submit=Submit"; post_data = $null; name = "S11-S12 impossible blind SQLi" }
    )
}

try {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stem = "u06-zap-api-explicit-$SecurityLevel-$stamp"
    $planFile = "$stem.yaml"
    $reportFile = "$stem.json"
    $harFile = "$stem.har"
    $apiEvidenceFile = "$stem-api-evidence.json"
    $summaryFile = "$stem-summary.json"
    $planPath = Join-Path $resultsDirectory $planFile
    $reportPath = Join-Path $resultsDirectory $reportFile
    $harPath = Join-Path $resultsDirectory $harFile
    $apiEvidencePath = Join-Path $summaryDirectory $apiEvidenceFile
    $summaryPath = Join-Path $summaryDirectory $summaryFile

    $seedJobs = if ($SecurityLevel -in @("low", "impossible")) {
@'
  - type: requestor
    parameters:
      user: dvwa-local-user
    requests:
      - name: Seed SQLi GET module input
        url: http://dvwa/vulnerabilities/sqli/?id=1&Submit=Submit
        method: GET
      - name: Seed blind SQLi GET module input
        url: http://dvwa/vulnerabilities/sqli_blind/?id=1&Submit=Submit
        method: GET
'@
    }
    elseif ($SecurityLevel -eq "medium") {
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
    else {
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
    $plan = Get-Content -LiteralPath $templatePath -Raw
    $plan = $plan.Replace("__DVWA_SECURITY_LEVEL__", $SecurityLevel)
    $plan = $plan.Replace("__ZAP_REPORT_FILE__", $reportFile)
    $plan = $plan.Replace("__ZAP_HAR_FILE__", $harFile)
    $plan = $plan.Replace("__DVWA_INPUT_SEEDS__", $seedJobs)
    # Setup runs auth, scoped seed requests, spidering, and scanner configuration.
    # Active scans themselves use the API with an explicit method and input.
    $plan = $plan.Replace("__DVWA_ACTIVE_SCAN_JOBS__", "")
    [System.IO.File]::WriteAllText($planPath, $plan, $utf8NoBom)

    $env:DVWA_SECURITY_LEVEL = $SecurityLevel
    $env:ZAP_PLAN_FILE = $planFile
    $env:ZAP_API_KEY = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
    $env:ZAP_API_PORT = [string]$apiPortInContainer

    docker compose --project-directory $PSScriptRoot --profile zap-api -f $composeFile up -d --force-recreate dvwa | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare local DVWA at level $SecurityLevel." }
    $ready = $false
    $lastDvwaError = "no HTTP 200 response yet"
    Write-Output "Waiting for the local DVWA HTTP service..."
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        $statusCode = & curl.exe --noproxy "*" --silent --show-error --output NUL `
            --write-out "%{http_code}" --max-time 3 "http://127.0.0.1:4280/login.php" 2>$null
        if ($LASTEXITCODE -eq 0 -and [string]$statusCode -eq "200") { $ready = $true; break }
        $lastDvwaError = "curl exit $LASTEXITCODE, HTTP $statusCode"
        if (($attempt % 15) -eq 14) { Write-Output "DVWA is still starting... ($lastDvwaError)" }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "Local DVWA did not become ready at level $SecurityLevel. Last response: $lastDvwaError" }

    docker compose --project-directory $PSScriptRoot --profile zap-api -f $composeFile up -d --force-recreate zap-api | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not start the loopback-only ZAP API container." }
    $containerStarted = $true
    $script:zapContainerId = docker compose --project-directory $PSScriptRoot --profile zap-api -f $composeFile ps -q zap-api
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:zapContainerId)) {
        throw "Could not resolve the temporary ZAP API container ID."
    }

    $apiReady = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        try {
            $version = Invoke-ZapApi "JSON/core/view/version"
            if ($version.version) { $apiReady = $true; break }
        }
        catch {
            if (($attempt % 15) -eq 14) { Write-Output "ZAP API is still starting... $($_.Exception.Message)" }
            Start-Sleep -Seconds 2
        }
    }
    if (-not $apiReady) { throw "ZAP API did not become ready on its private container loopback." }

    $containerPlanPath = "/zap/out/$planFile"
    $setupProgress = Start-ZapAutomationPlan $containerPlanPath
    $contextResponse = Invoke-ZapApi "JSON/context/view/context" @{ contextName = $contextName }
    $context = $contextResponse.context
    if ($null -eq $context -or $null -eq $context.id) {
        throw "Could not resolve the configured ZAP context ID."
    }
    $contextId = [string]$context.id
    $usersResponse = Invoke-ZapApi "JSON/users/view/usersList" @{ contextId = $contextId }
    $users = if ($usersResponse.PSObject.Properties.Name -contains "usersList") {
        @($usersResponse.usersList)
    }
    else { @($usersResponse.users) }
    $user = $users | Where-Object { $_.name -eq "dvwa-local-user" } | Select-Object -First 1
    if ($null -eq $user -or $null -eq $user.id) { throw "Could not resolve the authenticated DVWA ZAP user ID." }
    $userId = [string]$user.id

    $null = Invoke-ZapApi "JSON/ascan/action/setOptionInjectPluginIdInHeader" @{ Boolean = "true" } -AllowEmpty
    $tagSetting = Invoke-ZapApi "JSON/ascan/view/optionInjectPluginIdInHeader"
    if ([string]$tagSetting.InjectPluginIdInHeader -ne "true") {
        throw "ZAP did not enable X-ZAP-Scan-ID request attribution."
    }

    $scanEvidence = @()
    foreach ($target in (Get-InputTargets $SecurityLevel)) {
        Write-Output "Starting explicit $($target.method) active scan: $($target.name)"
        $scanId = Start-ZapExplicitScan $target $contextId $userId
        $status = Wait-ZapScan $scanId
        $scanRecord = @{
            target_name = $target.name
            path = $target.path
            method = $target.method
            scan_id = $scanId
            final_status_percent = $status
        }
        if ($target.method -eq "POST") { $scanRecord.seed_post_data = $target.post_data }
        else { $scanRecord.seed_url_query = $target.query }
        $scanEvidence += $scanRecord
    }

    $statsResponse = Invoke-ZapApi "JSON/stats/view/stats" @{ keyPrefix = "stats.ascan." }
    $stats = if ($statsResponse.PSObject.Properties.Name -contains "stats") {
        $statsResponse.stats
    }
    else { $statsResponse }
    $ruleStats = @{}
    foreach ($ruleId in @("40018", "40019")) {
        $statValue = $null
        if ($stats -is [System.Collections.IDictionary]) {
            foreach ($key in $stats.Keys) {
                if ([string]$key -match "stats\.ascan\.$ruleId\.urls$") { $statValue = [int]$stats[$key]; break }
            }
        }
        elseif ($stats) {
            $property = $stats.PSObject.Properties | Where-Object { $_.Name -match "stats\.ascan\.$ruleId\.urls$" } | Select-Object -First 1
            if ($property) { $statValue = [int]$property.Value }
        }
        $ruleStats[$ruleId] = $statValue
    }

    $reportResponse = Invoke-ZapApi "JSON/reports/action/generate" @{
        title = "DVWA $SecurityLevel Explicit SQLi Active Scan"
        template = "traditional-json"
        sites = "http://dvwa"
        reportDir = "/zap/out"
        reportFileName = $reportFile
        display = "false"
    }
    $reportDeadline = (Get-Date).AddSeconds(60)
    while (-not (Test-Path -LiteralPath $reportPath) -and (Get-Date) -lt $reportDeadline) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Path -LiteralPath $reportPath)) { throw "ZAP completed but did not create its JSON report." }

    Export-ZapHar $harFile $harPath

    $apiEvidence = [ordered]@{
        schema_version = "1.0.0"
        runner = "zap-api-explicit-method-postdata"
        security_level = $SecurityLevel
        target_origin = "http://dvwa"
        api_binding = "private Docker network; no host port published"
        automation_plan = $planFile
        automation_plan_finished = $setupProgress.finished
        automation_plan_errors = @($setupProgress.error)
        context_name = $contextName
        context_id = $contextId
        user_name = "dvwa-local-user"
        user_id = $userId
        scanner_id_header_enabled = $true
        active_scans = $scanEvidence
        zap_rule_request_stats_by_rule = $ruleStats
        report_file = $reportFile
        har_file = $harFile
        created_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    [System.IO.File]::WriteAllText($apiEvidencePath, ($apiEvidence | ConvertTo-Json -Depth 12), $utf8NoBom)

    if (-not (Test-Path -LiteralPath $pythonExecutable)) { $pythonExecutable = "python" }
    & $pythonExecutable $summaryScript $reportPath $harPath $apiEvidencePath `
        --security-level $SecurityLevel --plan $planPath --output $summaryPath
    if ($LASTEXITCODE -ne 0) { throw "ZAP API scan finished, but the evidence summary could not be written." }

        $methods = (@($scanEvidence | ForEach-Object { $_.method }) | Select-Object -Unique) -join "/"
        Write-Output "Completed explicit $methods active scan for $SecurityLevel. Report: $reportPath"
    Write-Output "Local-only HAR: $harPath"
    Write-Output "API evidence: $apiEvidencePath"
    Write-Output "Coverage summary: $summaryPath"
    Write-Output "Plan: $planPath"
}
finally {
    if ($containerStarted) {
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        docker compose --project-directory $PSScriptRoot --profile zap-api -f $composeFile stop zap-api 2>$null | Out-Null
        docker compose --project-directory $PSScriptRoot --profile zap-api -f $composeFile rm --force zap-api 2>$null | Out-Null
        $ErrorActionPreference = $savedErrorActionPreference
    }
    if ($null -eq $previousPlan) { Remove-Item Env:ZAP_PLAN_FILE -ErrorAction SilentlyContinue }
    else { $env:ZAP_PLAN_FILE = $previousPlan }
    if ($null -eq $previousLevel) { Remove-Item Env:DVWA_SECURITY_LEVEL -ErrorAction SilentlyContinue }
    else { $env:DVWA_SECURITY_LEVEL = $previousLevel }
    if ($null -eq $previousApiKey) { Remove-Item Env:ZAP_API_KEY -ErrorAction SilentlyContinue }
    else { $env:ZAP_API_KEY = $previousApiKey }
    Remove-Variable -Name zapContainerId -Scope Script -ErrorAction SilentlyContinue
}
