# Deploy the marginal API to Fly from a Windows machine.
#
# Reads FLY_APP_NAME, FLY_API_TOKEN, DATABASE_URL and MARGINAL_WRITE_TOKEN from a .env file next
# to the repository (C:\Project FullTime\.env by default) or from the environment, installs
# flyctl when it is missing, creates the app when it does not exist, stages the secrets, deploys
# with Fly's remote builder (no local Docker), then checks the live health endpoint and writes
# everything it saw to deploy\deploy-log.txt so the build can read the result back.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\marginal\deploy\deploy.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path $repo "deploy\deploy-log.txt"
Start-Transcript -Path $log -Force | Out-Null

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

if (-not $env:FLY_APP_NAME) { $env:FLY_APP_NAME = "marginal-alderquist-api" }
if (-not $env:DATABASE_URL) { throw "DATABASE_URL (the Neon connection string) is not set" }
if (-not $env:MARGINAL_WRITE_TOKEN) { $env:MARGINAL_WRITE_TOKEN = [guid]::NewGuid().ToString("N") }

$fly = Get-Command flyctl -ErrorAction SilentlyContinue
if (-not $fly) {
    $candidate = Join-Path $env:USERPROFILE ".fly\bin\flyctl.exe"
    if (-not (Test-Path $candidate)) {
        Write-Host "installing flyctl"
        Invoke-WebRequest -UseBasicParsing https://fly.io/install.ps1 | Invoke-Expression
    }
    $env:Path = "$env:USERPROFILE\.fly\bin;$env:Path"
}
flyctl version

$apps = flyctl apps list --json | ConvertFrom-Json
if (-not ($apps | Where-Object { $_.Name -eq $env:FLY_APP_NAME })) {
    Write-Host "creating app $env:FLY_APP_NAME"
    flyctl apps create $env:FLY_APP_NAME --org personal
}

Set-Location $repo
flyctl secrets set --app $env:FLY_APP_NAME --stage "DATABASE_URL=$env:DATABASE_URL" "MARGINAL_WRITE_TOKEN=$env:MARGINAL_WRITE_TOKEN"
flyctl deploy --app $env:FLY_APP_NAME --remote-only --ha=false

$base = "https://$($env:FLY_APP_NAME).fly.dev"
Write-Host "checking $base/v1/health"
$health = Invoke-RestMethod -Uri "$base/v1/health" -TimeoutSec 60
$health | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $repo "deploy\live-url.txt") -Value $base
Set-Content -Path (Join-Path $repo "deploy\write-token.txt") -Value $env:MARGINAL_WRITE_TOKEN
Write-Host "deployed: $base"
Stop-Transcript | Out-Null
