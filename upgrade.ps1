# ==========================================================
# Odoo Custom Module Upgrader (x_*)
# Version: 2.0
#
# Cara pakai (jalankan dari folder mana pun):
#   .\upgrade.ps1                 -> upgrade hanya module x_ yang BERUBAH di git (cepat, buat review harian)
#   .\upgrade.ps1 -All            -> upgrade SEMUA module x_ (1 klik, semua modul coworker)
#   .\upgrade.ps1 x_spk,x_disposal-> upgrade module tertentu saja
#   .\upgrade.ps1 -All -Yes       -> -Yes = skip konfirmasi (buat dijalanin otomatis)
# ==========================================================

param(
    [Parameter(Position = 0)]
    [string]$Modules = "",      # daftar module manual, pisah koma. mis: x_spk,x_disposal

    [switch]$All,               # upgrade semua module x_
    [switch]$Yes                # skip konfirmasi
)

# ---------------- CONFIG ----------------
$ConfigFile = "E:\Odoo\odoo\odoo.conf"
# WAJIB tunjuk ke python venv Odoo (Python 3.12). Jangan pakai "python" doang,
# karena di PC ini ada banyak Python (3.7/3.8/3.10) & bisa kepilih yg salah.
$Python     = "E:\Odoo\odoo\venv\Scripts\python.exe"
$OdooBin    = "E:\Odoo\odoo\odoo-bin"
$RepoRoot   = "E:\Odoo\custom_cakrawala\cakrawala"   # tempat module x_ berada
$LogDir     = Join-Path $RepoRoot "_upgrade_logs"
# ----------------------------------------

# Continue (bukan Stop): Odoo nulis log ke stderr, jadi Stop bikin script salah
# nganggep log biasa sebagai error fatal. Validasi manual pakai if/exit di bawah.
$ErrorActionPreference = "Continue"
Clear-Host

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "     Odoo Custom Module Upgrader (x_*)"
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# --- Validasi config ---
if (-not (Test-Path $ConfigFile)) {
    Write-Host "ERROR : Config tidak ditemukan: $ConfigFile" -ForegroundColor Red
    pause; exit 1
}
if (-not (Test-Path $OdooBin)) {
    Write-Host "ERROR : odoo-bin tidak ditemukan: $OdooBin" -ForegroundColor Red
    pause; exit 1
}
if (-not (Test-Path $Python)) {
    Write-Host "ERROR : Python venv tidak ditemukan: $Python" -ForegroundColor Red
    Write-Host "Betulkan variabel `$Python di bagian CONFIG script ini." -ForegroundColor Yellow
    pause; exit 1
}

# --- Ambil db_name & http_port dari odoo.conf ---
$db = (Select-String '^\s*db_name\s*=' $ConfigFile).Line.Split("=", 2)[1].Trim()
$portLine = Select-String '^\s*http_port\s*=' $ConfigFile
$httpPort = if ($portLine) { $portLine.Line.Split("=", 2)[1].Trim() } else { "8069" }

Write-Host "Database : $db"
Write-Host "Mode     : $(if ($All) {'SEMUA module x_'} elseif ($Modules) {'Module manual'} else {'Hanya yang berubah di git'})"
Write-Host ""

# --- Guard: jangan upgrade kalau server dev masih jalan (bisa corrupt registry) ---
$portBusy = Get-NetTCPConnection -LocalPort $httpPort -State Listen -ErrorAction SilentlyContinue
if ($portBusy) {
    Write-Host "PERINGATAN : Ada server yang jalan di port $httpPort." -ForegroundColor Yellow
    Write-Host "Upgrade sambil server hidup bisa bikin registry error. Stop dulu server Odoo." -ForegroundColor Yellow
    if (-not $Yes) {
        $ans = Read-Host "Tetap lanjut? (y/N)"
        if ($ans -ne "y") { Write-Host "Dibatalkan." -ForegroundColor Yellow; exit }
    }
    Write-Host ""
}

# --- Kumpulkan daftar module yang mau di-upgrade ---
$targets = @()

if ($Modules) {
    # Mode manual: dari argumen
    $targets = $Modules -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
elseif ($All) {
    # Mode -All: scan semua folder x_* yang punya __manifest__.py
    $targets = Get-ChildItem -Path $RepoRoot -Directory -Filter "x_*" |
        Where-Object { Test-Path (Join-Path $_.FullName "__manifest__.py") } |
        Select-Object -ExpandProperty Name
}
else {
    # Mode default: hanya module x_ yang berubah di git
    Push-Location $RepoRoot
    git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR : $RepoRoot bukan Git repository." -ForegroundColor Red
        Pop-Location; pause; exit 1
    }
    $changed = git status --porcelain
    Pop-Location

    foreach ($line in $changed) {
        $path = $line.Substring(3).Trim().Trim('"')
        foreach ($folder in ($path -split "[/\\]")) {
            if ($folder.StartsWith("x_")) { $targets += $folder; break }
        }
    }
}

$targets = $targets | Sort-Object -Unique

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host "Tidak ada module x_ yang perlu di-upgrade." -ForegroundColor Yellow
    if (-not $All -and -not $Modules) {
        Write-Host "(Tidak ada perubahan di git. Pakai -All untuk upgrade semua.)" -ForegroundColor DarkGray
    }
    pause; exit
}

# --- Tampilkan daftar & konfirmasi ---
Write-Host "=============================================="
Write-Host "Module yang akan di-upgrade ($($targets.Count)) :"
Write-Host "=============================================="
$targets | ForEach-Object { Write-Host " - $_" -ForegroundColor Green }
Write-Host ""

if ($All -and -not $Yes) {
    $ans = Read-Host "Upgrade SEMUA $($targets.Count) module? (y/N)"
    if ($ans -ne "y") { Write-Host "Dibatalkan." -ForegroundColor Yellow; exit }
    Write-Host ""
}

# --- Jalankan upgrade ---
$list = $targets -join ","
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $LogDir "upgrade_$stamp.log"

Write-Host "Menjalankan upgrade... (log: $logFile)" -ForegroundColor Cyan
Write-Host ""
$start = Get-Date

# --stop-after-init : upgrade lalu keluar (tidak menjalankan server)
# Dibungkus cmd /c "... 2>&1" supaya penggabungan stderr dilakukan cmd (OS level),
# jadi PowerShell terima teks biasa -> tidak salah menganggap log Odoo sbg error.
# Hasilnya: output tampil live di console SEKALIGUS tersimpan ke log file.
$runCmd = "$Python `"$OdooBin`" -c `"$ConfigFile`" -d $db -u $list --stop-after-init 2>&1"
cmd /c $runCmd | Tee-Object -FilePath $logFile

$code = $LASTEXITCODE
$end  = Get-Date

Write-Host ""
if ($code -eq 0) {
    Write-Host "==============================================" -ForegroundColor Green
    Write-Host "Upgrade SELESAI (sukses)." -ForegroundColor Green
} else {
    Write-Host "==============================================" -ForegroundColor Red
    Write-Host "Upgrade GAGAL (exit code $code). Cek log di atas / $logFile" -ForegroundColor Red
}
Write-Host "Durasi : $([math]::Round(($end - $start).TotalSeconds, 2)) detik"
Write-Host "==============================================" -ForegroundColor $(if ($code -eq 0) {'Green'} else {'Red'})

pause
