# Cổng kiểm tra chạy tay (chưa dùng CI): chạy trước mỗi mốc / mỗi lần merge.
# Dùng:  powershell -File scripts/check.ps1 [-SkipAudit] [-SkipFrontend]
param([switch]$SkipAudit, [switch]$SkipFrontend)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$failed = @()
$skippedDb = $false
function Run($name, [scriptblock]$cmd) {
  Write-Host "`n=== $name"
  & $cmd
  if ($LASTEXITCODE -eq 0) { Write-Host "OK   $name" } else { Write-Host "FAIL $name"; $script:failed += $name }
}

docker info *> $null; if ($LASTEXITCODE -ne 0) { Write-Host "CANH BAO: Docker khong chay; test can Postgres se khong chay duoc (Windows 11 Home can WSL2)" }
Run "backend lint (ruff)" { uv run --python 3.12 ruff check backend scripts }
Run "backend tests (pytest)" { uv run --python 3.12 pytest -q }
# alembic check can Postgres da migrate. ALEMBIC_DATABASE_URL (DSN role migrator) -> chay truc tiep;
# TEST_DATABASE_URL (superuser) -> test_migrations.py chay alembic check tren DB tam (da nam trong pytest o tren).
if ($env:ALEMBIC_DATABASE_URL) { Run "alembic check (model khop migration)" { Push-Location backend; uv run --python 3.12 python -m alembic check; Pop-Location } }
elseif ($env:TEST_DATABASE_URL) { Write-Host "alembic check: da chay trong backend/tests/db/test_migrations.py" }
elseif ($env:SKIP_DB_CHECKS -eq "1") {
  $skippedDb = $true
  Write-Host "!!! SKIPPED-DB-CHECKS: SKIP_DB_CHECKS=1, bo qua alembic check va test DB (khong chan duoc model lech migration)"
} else {
  Write-Host "FAIL: chua dat TEST_DATABASE_URL (Postgres pgvector) hay ALEMBIC_DATABASE_URL nen khong chay duoc alembic check va test DB."
  Write-Host "      Dat mot trong hai, hoac SKIP_DB_CHECKS=1 de co y bo qua (ket qua se khong duoc coi la dat toan bo)."
  $failed += "thieu cau hinh DB cho alembic check/test DB"
}
if (-not $SkipAudit) { Run "pip-audit" { uv run --python 3.12 python -m pip_audit } }
if (-not $SkipFrontend -and (Test-Path frontend/package.json)) {
  Run "frontend typecheck" { Push-Location frontend; npm run --silent typecheck; Pop-Location }
  if (Select-String -Path frontend/package.json -Pattern '"test"' -Quiet) { Run "frontend tests" { Push-Location frontend; npm test --silent; Pop-Location } }
  if (-not $SkipAudit) { Run "npm audit (high)" { Push-Location frontend; npm audit --audit-level=high; Pop-Location } }
}

if ($failed.Count -eq 0) {
  if ($skippedDb) { Write-Host "`n!!! SKIPPED-DB-CHECKS: cac buoc con lai dat, NHUNG alembic check va test DB CHUA chay (khong phai TAT CA DAT)"; exit 0 }
  Write-Host "`nTẤT CẢ ĐẠT"; exit 0
}
Write-Host "`nTHẤT BẠI: $($failed -join ', ')"; exit 1
