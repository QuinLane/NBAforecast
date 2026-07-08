# Launch NBAforecast locally (Windows / PowerShell).
#
#   ./scripts/dev.ps1
#
# Brings up the backend stack (Postgres, Redis, MinIO, MLflow, API) in Docker, waits for the API
# to be healthy, then starts the Next.js frontend dev server in the foreground. Ctrl+C stops the
# frontend; the Docker stack keeps running (stop it with `docker compose down`).
#
# Prerequisites: Docker Desktop running, Node 20+, pnpm.

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

Write-Host "==> Starting the backend stack (Docker)..." -ForegroundColor Cyan
docker compose up -d

Write-Host "==> Waiting for the API (http://localhost:8000/health)..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Write-Host "API did not become healthy in time. Check: docker compose logs api" -ForegroundColor Red
    exit 1
}
Write-Host "    API is up." -ForegroundColor Green

# The frontend calls the API through a same-origin /backend proxy (no CORS). .env.local is
# git-ignored, so create it on first run.
$envLocal = Join-Path $repo "frontend/.env.local"
if (-not (Test-Path $envLocal)) {
    Write-Host "==> Creating frontend/.env.local" -ForegroundColor Cyan
    @(
        "API_PROXY_TARGET=http://127.0.0.1:8000",
        "NEXT_PUBLIC_API_URL=http://127.0.0.1:3000/backend"
    ) | Out-File -FilePath $envLocal -Encoding utf8
}

if (-not (Test-Path (Join-Path $repo "frontend/node_modules"))) {
    Write-Host "==> Installing frontend dependencies..." -ForegroundColor Cyan
    pnpm --dir frontend install
}

Write-Host "==> Frontend starting at http://localhost:3000  (Ctrl+C to stop)" -ForegroundColor Green
pnpm --dir frontend dev
