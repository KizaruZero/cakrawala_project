$projectPath = "D:\Odoo\cakrawala_project"
$logDir = "$projectPath\_upgrade_logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "$logDir\upgrade_$timestamp.log"

Write-Host "Mencari modul di $projectPath..."
$modules = @()

foreach ($dir in Get-ChildItem -Path $projectPath -Directory) {
    if (Test-Path (Join-Path $dir.FullName "__manifest__.py")) {
        $modules += $dir.Name
    }
}

if ($modules.Count -eq 0) {
    Write-Host "Tidak ada modul yang ditemukan."
    exit
}

$moduleString = $modules -join ","
Write-Host "Ditemukan $($modules.Count) modul."
Write-Host "Memulai proses upgrade..."
Write-Host "Log akan disimpan di: $logFile"

$pythonPath = "D:\Odoo\venv\Scripts\python.exe"
$odooBin = "D:\Odoo\odoo\odoo-bin"
$confPath = "D:\Odoo\odoo.conf"
$dbName = "cakrawala_dev"

& $pythonPath $odooBin -c $confPath -d $dbName -u $moduleString --stop-after-init 2>&1 | Tee-Object -FilePath $logFile

Write-Host "======================================"
Write-Host "Proses upgrade selesai."

$errors = 0
$warnings = 0

if (Test-Path $logFile) {
    foreach ($line in Get-Content $logFile) {
        if ($line -match "\sERROR\s|\sCRITICAL\s|\sTraceback\s") {
            $errors++
        }
        if ($line -match "\sWARNING\s") {
            $warnings++
        }
    }
}

Write-Host "Total Errors   : $errors" -ForegroundColor $(if($errors -gt 0) {'Red'} else {'Green'})
Write-Host "Total Warnings : $warnings" -ForegroundColor $(if($warnings -gt 0) {'Yellow'} else {'Green'})
Write-Host "======================================"
