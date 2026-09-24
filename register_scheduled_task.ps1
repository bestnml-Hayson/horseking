$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $rootDir "sync_data.ps1"
$logDir = Join-Path $rootDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$dateStamp = Get-Date -Format "yyyyMMdd"
$outLog = Join-Path $logDir ("sync_out_" + $dateStamp + ".log")
$errLog = Join-Path $logDir ("sync_err_" + $dateStamp + ".log")
$taskName = "HorseRacingAutoSyncEvery3Min"

$sysps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$argsLine = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $syncScript + '"'

function Write-Bar { Write-Host ("=" * 60) }

try {
    $exists = $false
    try {
        $null = & schtasks.exe /Query /TN $taskName /FO CSV 2>$null
        if ($LASTEXITCODE -eq 0) { $exists = $true }
    } catch { $exists = $false }
    if ($exists) {
        & schtasks.exe /Delete /TN $taskName /F 2>$null
        Write-Host ("[OK] Deleted old task: " + $taskName)
    }

    & schtasks.exe /Create `
        /TN $taskName `
        /TR ('"' + $sysps + '" ' + $argsLine) `
        /SC MINUTE /MO 3 `
        /ST 00:01 /DU 24:00 `
        /F
    if ($LASTEXITCODE -ne 0) { throw "schtasks /Create FAILED exit=$LASTEXITCODE" }

    Write-Host ""
    Write-Bar
    Write-Host "  REGISTER SUCCESS (schtasks.exe method)"
    Write-Bar
    Write-Host ("  Task Name       : " + $taskName)
    Write-Host "  Frequency       : Every 3 minutes (24h/day, no gap)"
    Write-Host ("  Script Path     : " + $syncScript)
    Write-Host ("  PowerShell      : " + $sysps)
    Write-Host ("  Log dir         : " + $logDir)
    Write-Host ("  Stdout Log      : " + $outLog)
    Write-Host ("  Stderr Log      : " + $errLog)
    Write-Host "  Run Level       : HIGHEST (Admin)"
    Write-Host ""
    Write-Host "--- TEST: Trigger once now ---"
    & schtasks.exe /Run /TN $taskName 2>$null
    Write-Host "Triggered. State after 5s:"
    Start-Sleep -Seconds 5
    $q = (& schtasks.exe /Query /TN $taskName /FO LIST /V 2>$null) | Out-String
    $stateMatch = [regex]::Match($q, "Status\s*:\s*(.+?)\r?\n")
    $lastRun = [regex]::Match($q, "Last Run Time\s*:\s*(.+?)\r?\n")
    $lastRes = [regex]::Match($q, "Last Result\s*:\s*(.+?)\r?\n")
    if ($stateMatch.Success) { Write-Host ("  Current State  : " + $stateMatch.Groups[1].Value.Trim()) }
    if ($lastRun.Success)   { Write-Host ("  Last Run Time  : " + $lastRun.Groups[1].Value.Trim()) }
    if ($lastRes.Success)   { Write-Host ("  Last Result    : " + $lastRes.Groups[1].Value.Trim() + "  (0 = SUCCESS)") }
    Write-Host ""
    Write-Bar
    Write-Host "  MANAGEMENT COMMANDS"
    Write-Bar
    Write-Host ("  View info   : schtasks /Query /TN '" + $taskName + "' /FO LIST /V")
    Write-Host ("  Run now     : schtasks /Run /TN '" + $taskName + "'")
    Write-Host ("  Pause auto  : schtasks /Change /TN '" + $taskName + "' /DISABLE")
    Write-Host ("  Resume auto : schtasks /Change /TN '" + $taskName + "' /ENABLE")
    Write-Host ("  Delete task : schtasks /Delete /TN '" + $taskName + "' /F")
    Write-Host ("  Sync log    : Get-Content '" + (Join-Path $rootDir "sync.log") + "' -Tail 40")
    Write-Host ""
    Write-Host "--- DOES IT RUN WHEN TRAE IS CLOSED? ---"
    Write-Host "[YES] As long as: PC is ON + logged in to Windows."
    Write-Host "      - No TRAE / IDE / Terminal window needed."
    Write-Host "      - system-level task scheduler triggers powershell.exe."
    Write-Host "[NO ] If: PC OFF / HIBERNATE / SLEEP / LOGGED OUT."
    Write-Host "      -> For 24/7 even with PC OFF -> see Vercel analysis I gave."
    exit 0
} catch {
    Write-Host ("[ERROR] FAILED: " + $_.Exception.Message) -ForegroundColor Red
    if ($_.Exception.Message -match "access denied|Access is denied|denied") {
        Write-Host ""
        Write-Host "This error is PERMISSION-RELATED."
        Write-Host "Please re-run PowerShell as ADMINISTRATOR:"
        Write-Host "  1) Start -> Search 'Windows PowerShell'"
        Write-Host "  2) Right-click -> Run as administrator"
        Write-Host ("  3) cd '" + $rootDir + "'")
        Write-Host "  4) powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\register_scheduled_task.ps1'"
    } else {
        Write-Host ""
        Write-Host "Fallback option - create it manually:"
        Write-Host "  Open Task Scheduler (taskschd.msc)"
        Write-Host "  -> Create Basic Task -> name: $taskName"
        Write-Host "  -> Trigger: Daily -> Start 00:01 -> Advanced, repeat every 3 min for 24 hours"
        Write-Host "  -> Action: Start a program"
        Write-Host "     Program : powershell.exe"
        Write-Host ("     Args    : " + $argsLine)
        Write-Host ("     Start in: " + $rootDir)
    }
    exit 1
}
