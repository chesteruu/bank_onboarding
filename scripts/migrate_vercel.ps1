# Run Alembic migrations against the Vercel production Neon database.
# Prerequisites: Neon installed on the project (`vercel integration add neon`).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Pulling production env from Vercel..."
vercel pull --yes --environment=production

$envFile = ".vercel\.env.production.local"
if (-not (Test-Path $envFile)) {
    Write-Error "Missing $envFile — add Neon via: vercel integration add neon"
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"')
        Set-Item -Path "env:$name" -Value $value
    }
}

if (-not $env:DATABASE_URL -and -not $env:POSTGRES_URL) {
    Write-Error @"
No DATABASE_URL in Vercel project. Install Neon:
  vercel integration add neon
Or set DATABASE_URL in Vercel -> Settings -> Environment Variables
"@
}

Write-Host "Running migrations..."
python -m pip install -q -e .
alembic upgrade head
Write-Host "Migrations complete."
