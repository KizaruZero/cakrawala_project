# ====================================================================
# SCRIPT UPGRADE ALL CUSTOM MODULES (DYNAMIC)
# ====================================================================
# Script ini akan mencari semua folder di dalam cakrawala_project
# yang memiliki file __manifest__.py, lalu merangkainya menjadi
# daftar modul untuk di-upgrade sekaligus.
# Log akan otomatis disimpan di folder _upgrade_logs.
# ====================================================================

# Konfigurasi Path
$RepoRoot = "D:\Odoo\cakrawala_project"
$LogDir   = Join-Path $RepoRoot "_upgrade_logs"
$Python   = "D:\Odoo\venv\Scripts\python.exe"
$OdooBin  = "D:\Odoo\odoo\odoo-bin"
$Config   = "D:\Odoo\odoo.conf"
$Database = "cakrawala_dev"

# 1. Pastikan folder log tersedia
if (-Not (Test-Path -Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Buat nama file log berdasarkan timestamp
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile   = Join-Path $LogDir "upgrade_$Timestamp.log"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "       Mencari custom modul Odoo..." -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# 2. Cari semua modul secara dinamis (folder yang ada __manifest__.py)
$Modules = Get-ChildItem -Path $RepoRoot -Directory | Where-Object {
    Test-Path (Join-Path $_.FullName "__manifest__.py")
} | Select-Object -ExpandProperty Name

if ($Modules.Count -eq 0) {
    Write-Host "Tidak ada modul Odoo yang ditemukan di $RepoRoot" -ForegroundColor Red
    exit
}

# Gabungkan nama modul dengan koma
$ModuleList = $Modules -join ","

Write-Host "Ditemukan $($Modules.Count) modul:" -ForegroundColor Yellow
Write-Host $ModuleList -ForegroundColor DarkYellow
Write-Host ""
Write-Host "Menyimpan log ke: $LogFile" -ForegroundColor Cyan
Write-Host "Memulai proses upgrade..." -ForegroundColor Cyan
Write-Host "-----------------------------------------------"

# 3. Jalankan perintah Odoo Upgrade
# Menggunakan 2>&1 agar error stream (stderr) dari Odoo ikut masuk ke Tee-Object
$Args = @(
    $OdooBin,
    "-c", $Config,
    "-d", $Database,
    "-u", $ModuleList,
    "--stop-after-init"
)

# Jalankan proses dan alirkan output ke layar sekaligus ke file log
& $Python $Args 2>&1 | Tee-Object -FilePath $LogFile

# Analisis log untuk mencari jumlah Warning dan Error
$WarningCount = 0
$ErrorCount = 0

if (Test-Path $LogFile) {
    $LogContent = Get-Content $LogFile
    # Odoo log format biasanya berisi level log seperti " WARNING " atau " ERROR "
    $WarningCount = @($LogContent | Where-Object { $_ -cmatch " WARNING " }).Count
    $ErrorCount = @($LogContent | Where-Object { $_ -cmatch " ERROR " -or $_ -cmatch " CRITICAL " -or $_ -match "Traceback \(most recent call last\):" }).Count
}

Write-Host "-----------------------------------------------"
Write-Host "Proses upgrade selesai!" -ForegroundColor Green

if ($ErrorCount -gt 0) {
    Write-Host "STATUS: Ditemukan $ErrorCount ERROR!" -ForegroundColor Red -BackgroundColor Black
} else {
    Write-Host "STATUS: Tidak ada ERROR (Aman)." -ForegroundColor Green
}

if ($WarningCount -gt 0) {
    Write-Host "        Ditemukan $WarningCount WARNING." -ForegroundColor Yellow
} else {
    Write-Host "        Tidak ada WARNING." -ForegroundColor Green
}

Write-Host "-----------------------------------------------"
Write-Host "File Log: $LogFile" -ForegroundColor DarkGray
