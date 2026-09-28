# The reset half of reset and rederive, from a Windows machine: delete the plans and experiments
# the site recording and the separate client verification created in the live registry, by their
# stated notes and names, and leave the audit log and the canonical experiment alone.
#
# Uses Neon's HTTP SQL endpoint (https://<host>/sql with the connection string in the
# Neon-Connection-String header), because this machine has no psql. Reads DATABASE_URL from the
# .env beside the repository, the same file deploy.ps1 reads. Writes what it removed to
# deploy\reset-result.json.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\marginal\deploy\reset-registry.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Read-DotEnv($path) {
    if (Test-Path $path) {
        Get-Content $path | ForEach-Object {
            if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
                $name = $matches[1]; $value = $matches[2].Trim().Trim('"').Trim("'")
                if (-not [string]::IsNullOrEmpty($value)) { [Environment]::SetEnvironmentVariable($name, $value, "Process") }
            }
        }
    }
}
Read-DotEnv (Join-Path (Split-Path -Parent $repo) ".env")
Read-DotEnv (Join-Path $repo ".env")
if (-not $env:DATABASE_URL) { throw "DATABASE_URL is not set" }

# psycopg's scheme is not what Neon's HTTP endpoint expects.
$connection = $env:DATABASE_URL -replace '^postgresql\+psycopg://', 'postgresql://'
$hostName = ([Uri]$connection).Host
$endpoint = "https://$hostName/sql"
$headers = @{ "Neon-Connection-String" = $connection; "Neon-Raw-Text-Output" = "true"; "Neon-Array-Mode" = "false" }

function Invoke-Sql($query, $params) {
    $body = @{ query = $query; params = @($params) } | ConvertTo-Json -Depth 5
    return Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -ContentType "application/json" -TimeoutSec 90 -Body $body
}

$notes = @("recorded session for the site's fallback bundle", "persistence check", "verification from a separate client")
$names = @("verification from a separate client", "persistence check")

$plans = Invoke-Sql "delete from plans where note = any(`$1::text[]) returning plan_id" @(, $notes)
$results = Invoke-Sql "delete from experiment_results where experiment_id in (select experiment_id from experiments where name = any(`$1::text[])) returning id" @(, $names)
$experiments = Invoke-Sql "delete from experiments where name = any(`$1::text[]) returning experiment_id" @(, $names)
$remaining = Invoke-Sql "select experiment_id, name, plan_hash from experiments order by registered_at" @()

$record = [ordered]@{
    reset_at = (Get-Date).ToUniversalTime().ToString("o")
    client = "$env:COMPUTERNAME, Windows, PowerShell $($PSVersionTable.PSVersion)"
    plans_removed = @($plans.rows).Count
    results_removed = @($results.rows).Count
    experiments_removed = @($experiments.rows).Count
    experiments_remaining = @($remaining.rows | ForEach-Object { @{ experiment_id = $_.experiment_id; name = $_.name; plan_hash = $_.plan_hash } })
}
$record | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "deploy\reset-result.json")
$record | ConvertTo-Json -Depth 5
Write-Host "reset: the recording's plans and experiments are gone; the audit log is untouched"
