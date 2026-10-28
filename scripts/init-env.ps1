# Tạo .env từ .env.example và sinh khoá ngẫu nhiên (mật khẩu DB, khoá MCP, khoá nhân viên). Không ghi đè .env đã có.
# Dùng:  powershell -File scripts\init-env.ps1   rồi   docker compose up -d --build
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .env) { Write-Host ".env đã tồn tại: giữ nguyên (xoá file này nếu muốn tạo lại)"; exit 0 }

function New-Secret { -join ((1..24) | ForEach-Object { "{0:x2}" -f (Get-Random -Maximum 256) }) }
$lines = Get-Content .env.example -Encoding UTF8
foreach ($key in "POSTGRES_PASSWORD", "MCP_API_KEY", "STAFF_API_KEY", "AUTH_SECRET_KEY") {
  $value = New-Secret
  $lines = $lines | ForEach-Object { if ($_ -match "^$key=") { "$key=$value" } else { $_ } }
}
[System.IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Đã tạo .env với khoá ngẫu nhiên."
Write-Host ("Khoá nhân viên (đăng nhập /nhan-vien): " + (($lines | Where-Object { $_ -match "^STAFF_API_KEY=" }) -replace "^STAFF_API_KEY=", ""))
Write-Host "Nếu LLM/embedding/reranker chạy ở địa chỉ khác, sửa các dòng *_API_URL trong .env."
