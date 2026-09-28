# Verify the live API from a separate client (a Windows machine, not the server, not the
# build sandbox): register an experiment, post a result against its plan hash, save a plan,
# read all three back through the API, and check the audit row was written before the
# registration response was served. Writes what it saw to deploy\verify-log.txt and
# deploy\verify-result.json so the build can quote it.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\marginal\deploy\verify.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path $repo "deploy\verify-log.txt"
Start-Transcript -Path $log -Force | Out-Null

$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim()
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }
$planHash = ([guid]::NewGuid().ToString("N")).Substring(0, 16)

Write-Host "client: $env:COMPUTERNAME ($([Environment]::OSVersion.VersionString)), PowerShell $($PSVersionTable.PSVersion)"
Write-Host "server: $base"

$health = Invoke-RestMethod -Uri "$base/v1/health" -TimeoutSec 60
Write-Host "health: status=$($health.status) database=$($health.database) model=$($health.model_version)"

$registered = Invoke-RestMethod -Method Post -Uri "$base/v1/experiments" -Headers $headers -ContentType "application/json" -TimeoutSec 60 -Body (@{
    name = "verification from a separate client"; kind = "geo_lift"; plan_hash = $planHash; design = @{ client = $env:COMPUTERNAME }
} | ConvertTo-Json -Depth 5)
$experimentId = $registered.experiment_id
$servedAt = [DateTime]::Parse($registered.served_at).ToUniversalTime()
Write-Host "registered experiment $experimentId with plan hash $planHash at $($registered.registered_at)"

$posted = Invoke-RestMethod -Method Post -Uri "$base/v1/experiments/$experimentId/result" -Headers $headers -ContentType "application/json" -TimeoutSec 60 -Body (@{
    plan_hash = $planHash; method = "did"; channel = "display_retargeting"; incremental_revenue = 123456.0; standard_error = 1000.0
    lower = 121800.0; upper = 125100.0; level = 0.9; geos = @(1, 2, 3); start_week = 148; end_week = 155
} | ConvertTo-Json -Depth 5)
Write-Host "posted result $($posted.result_id) at $($posted.posted_at)"

$saved = Invoke-RestMethod -Method Post -Uri "$base/v1/plans" -Headers $headers -ContentType "application/json" -TimeoutSec 120 -Body (@{
    total_budget = 500000.0; note = "verification from a separate client"; apply_allowance = $false
} | ConvertTo-Json -Depth 5)
$planId = $saved.plan_id
Write-Host "saved plan $planId, expected weekly profit $($saved.plan.expected_profit)"

$experiment = Invoke-RestMethod -Uri "$base/v1/experiments/$experimentId" -TimeoutSec 60
$plan = Invoke-RestMethod -Uri "$base/v1/plans/$planId" -TimeoutSec 60
$audit = Invoke-RestMethod -Uri "$base/v1/audit?limit=50" -TimeoutSec 60
$registration = $audit.entries | Where-Object { $_.action -eq "register" -and $_.resource_id -eq $experimentId } | Select-Object -First 1
$auditAt = [DateTime]::Parse($registration.at).ToUniversalTime()
$auditBefore = $auditAt -le $servedAt

$ok = ($experiment.plan_hash -eq $planHash) -and ($experiment.results.Count -ge 1) -and ($experiment.results[0].incremental_revenue -eq 123456.0) -and ($plan.plan_id -eq $planId) -and $auditBefore
$result = [ordered]@{
    base_url = $base
    client = "$env:COMPUTERNAME, Windows, PowerShell $($PSVersionTable.PSVersion)"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    health = @{ status = $health.status; database = $health.database; model_version = $health.model_version }
    experiment_id = $experimentId
    plan_hash = $planHash
    result_read_back = $experiment.results[0].incremental_revenue
    plan_id = $planId
    plan_expected_profit = $plan.expected_profit
    audit_entries = $audit.entries.Count
    audit_before_response = $auditBefore
    statement_present = ($experiment.statement.Length -gt 100)
    passed = $ok
}
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "deploy\verify-result.json")
$result | ConvertTo-Json -Depth 5
if (-not $ok) { throw "verification failed" }
Write-Host "verified: the experiment, its result and the plan were read back from a separate client"
Stop-Transcript | Out-Null
