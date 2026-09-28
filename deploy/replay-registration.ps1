# Replay the canonical geo lift test to the live registry from a separate client.
#
# The build sandbox could not reach the API, so the pipeline registered the design locally under
# its plan hash. This script posts the same design under the same hash to the live API, then
# posts the result the pipeline found, and writes what the registry answered to
# results\experiments\live_registry.json, marked "replayed" (the registration happened after the
# data existed, so it is a replay, not a pre-registration).
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\marginal\deploy\replay-registration.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim()
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }

$design = Get-Content (Join-Path $repo "results\experiments\geo_design.json") -Raw | ConvertFrom-Json
$result = Get-Content (Join-Path $repo "results\experiments\geo_result.json") -Raw | ConvertFrom-Json
$registration = $design.registration

$registered = Invoke-RestMethod -Method Post -Uri "$base/v1/experiments" -Headers $headers -ContentType "application/json" -TimeoutSec 90 -Body (@{
    name = $registration.name; kind = $registration.kind; plan_hash = $registration.plan_hash; design = $design.design
} | ConvertTo-Json -Depth 8)
$experimentId = $registered.experiment_id
Write-Host "live registry holds experiment $experimentId under plan hash $($registered.plan_hash)"

$did = $result.did
$posted = Invoke-RestMethod -Method Post -Uri "$base/v1/experiments/$experimentId/result" -Headers $headers -ContentType "application/json" -TimeoutSec 90 -Body (@{
    plan_hash = $registration.plan_hash; method = "did"; channel = $design.design.channel
    incremental_revenue = $did.incremental_revenue; standard_error = $did.standard_error
    lower = $did.lower; upper = $did.upper; level = $did.level
    geos = @($design.design.treated_geos); start_week = $design.design.start_week; end_week = $design.design.end_week
    truth = $result.truth
} | ConvertTo-Json -Depth 8)
Write-Host "posted result $($posted.result_id) at $($posted.posted_at)"

$readBack = Invoke-RestMethod -Uri "$base/v1/experiments/$experimentId" -TimeoutSec 60
$record = [ordered]@{
    base_url = $base
    replayed = $true
    replayed_at = (Get-Date).ToUniversalTime().ToString("o")
    client = "$env:COMPUTERNAME, Windows, PowerShell $($PSVersionTable.PSVersion)"
    experiment_id = $experimentId
    plan_hash = $registered.plan_hash
    plan_hash_matches_pipeline = ($registered.plan_hash -eq $registration.plan_hash)
    registered_at_on_live = $registered.registered_at
    registered_locally_at = $registration.registered_at
    results_on_live = $readBack.results.Count
    result_read_back = $readBack.results[0].incremental_revenue
}
$record | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "results\experiments\live_registry.json")
$record | ConvertTo-Json -Depth 5
if (-not $record.plan_hash_matches_pipeline) { throw "the live registry returned a different plan hash" }
Write-Host "replayed: the canonical experiment and its result are on the live registry"
