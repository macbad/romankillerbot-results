param(
    [ValidateRange(60, 86400)]
    [int]$IntervalSeconds = 300,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$dashboardRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$exporter = Join-Path $dashboardRoot "export_dashboard.py"

if (-not (Test-Path -LiteralPath (Join-Path $dashboardRoot ".git"))) {
    Write-Host "Ten folder nie jest jeszcze repozytorium GitHub." -ForegroundColor Yellow
    Write-Host "Najpierw wykonaj kroki z pliku README.md w folderze public-dashboard."
    exit 1
}

function Publish-Update {
    & py -3 $exporter
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się przygotować danych." }
    & git -C $dashboardRoot add -- "docs/data/dashboard.json"
    & git -C $dashboardRoot diff --cached --quiet
    if ($LASTEXITCODE -eq 0) { Write-Host "Brak nowych danych."; return }
    if ($LASTEXITCODE -ne 1) { throw "Nie udało się sprawdzić zmian." }
    $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss 'UTC'")
    & git -C $dashboardRoot commit -m "Update trading stats $stamp"
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się utworzyć aktualizacji." }
    & git -C $dashboardRoot push
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się wysłać danych do GitHub." }
    Write-Host "Opublikowano: $stamp" -ForegroundColor Green
}

do {
    try { Publish-Update } catch { Write-Warning $_ }
    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
