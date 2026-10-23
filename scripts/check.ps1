# Cổng kiểm tra chạy tay (chưa dùng CI): chạy trước mỗi mốc / mỗi lần merge.
# Dùng:  powershell -File scripts/check.ps1 [-SkipAudit] [-SkipFrontend]
param([switch]$SkipAudit, [switch]$SkipFrontend)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$failed = @()
function Run($name, [scriptblock]$cmd) {
  Write-Host "`n=== $name"
  & $cmd
  if ($LASTEXITCODE -eq 0) { Write-Host "OK   $name" } else { Write-Host "FAIL $name"; $script:failed += $name }
}

docker info *> $null; if ($LASTEXITCODE -ne 0) { Write-Host "CANH BAO: Docker khong chay; test can Postgres se khong chay duoc (Windows 11 Home can WSL2)" }
Run "backend lint (ruff)" { uv run --python 3.12 ruff check backend scripts }
Run "backend tests (pytest)" { uv run --python 3.12 pytest -q }
if (Test-Path backend/alembic.ini) { Run "alembic check (model khop migration)" { Push-Location backend; uv run --python 3.12 alembic check; Pop-Location } } else { Write-Host "SKIP alembic check (chua co backend/alembic.ini)" }
if (-not $SkipAudit) { Run "pip-audit" { uv run --python 3.12 python -m pip_audit } }
if (-not $SkipFrontend -and (Test-Path frontend/package.json)) {
  Run "frontend typecheck" { Push-Location frontend; npm run --silent typecheck; Pop-Location }
  if (Select-String -Path frontend/package.json -Pattern '"test"' -Quiet) { Run "frontend tests" { Push-Location frontend; npm test --silent; Pop-Location } }
  if (-not $SkipAudit) { Run "npm audit (high)" { Push-Location frontend; npm audit --audit-level=high; Pop-Location } }
}

if ($failed.Count -eq 0) { Write-Host "`nTẤT CẢ ĐẠT"; exit 0 }
Write-Host "`nTHẤT BẠI: $($failed -join ', ')"; exit 1
