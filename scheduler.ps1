$ErrorActionPreference = "Continue"
$rootDir = $PSScriptRoot
$syncScript = Join-Path $rootDir "sync_data.ps1"
$logFile = Join-Path $rootDir "scheduler.log"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$intervalMinutes = 3
$script:running = $false
function Append-Log {
    param(
        [Parameter(Position=0)]
        [string]$Msg,
        [Parameter(Position=1)]
        [string]$Level = "INFO"
    )
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "][" + $Level + "] " + $Msg
    try { [IO.File]::AppendAllText($logFile, $line + "`r`n", $utf8NoBom) } catch {}
    Write-Host $line
}
function ExtractJson([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $lastOpen = $text.LastIndexOf('{')
    $lastClose = $text.LastIndexOf('}')
    if ($lastOpen -lt 0 -or $lastClose -lt 0 -or $lastClose -le $lastOpen) { return $null }
    try {
        return $text.Substring($lastOpen, ($lastClose - $lastOpen + 1)) | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
}
Append-Log ("=== SCHEDULER START (interval=" + $intervalMinutes + " min) ===")
Write-Host ("Scheduler is running. Sync every " + $intervalMinutes + " minutes.")
Write-Host "Press CTRL+C to stop."
Write-Host ""
while ($true) {
    try {
        if (-not $script:running) {
            $script:running = $true
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            Append-Log "START sync_data.ps1"
            try {
                $rawOut = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $syncScript
                $sw.Stop()
                $elapsed = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
                $fullText = ($rawOut | Out-String).Trim()
                $parsed = ExtractJson $fullText
                if ($parsed -and $parsed.ok -eq $true) {
                    $parts = @()
                    $parts += "total=" + $parsed.total_races
                    $parts += "new=" + $parsed.new_races
                    if ($parsed.updated -and [int]$parsed.updated -gt 0) { $parts += "upd=" + $parsed.updated }
                    if ($parsed.bootstrapped -and [int]$parsed.bootstrapped -gt 0) {
                        $parts += "boot=" + $parsed.bootstrapped + "(" + $parsed.next_date + "/" + $parsed.next_venue + ")"
                    }
                    if ($parsed.odds_updated -and [int]$parsed.odds_updated -gt 0) { $parts += "odds=" + $parsed.odds_updated }
                    $parts += "copied=" + $parsed.copied_files
                    $parts += "(" + $elapsed + "s)"
                    $m = "SYNC OK: " + ($parts -join " ")
                    Append-Log $m
                } else {
                    $m = "SYNC DONE (uncertain): elapsed=" + $elapsed + "s"
                    if ($parsed -and $parsed.errors -and $parsed.errors.Count -gt 0) {
                        $m += " errors=" + $parsed.errors.Count
                    }
                    Append-Log $m "WARN"
                }
            } catch {
                Append-Log ("SYNC ERROR: " + $_.Exception.Message) "ERROR"
            }
            $script:running = $false
        }
        $next = (Get-Date).AddMinutes($intervalMinutes)
        Append-Log ("Sleep until " + $next.ToString("HH:mm:ss"))
        $sleepUntil = $next
        while ((Get-Date) -lt $sleepUntil) {
            Start-Sleep -Seconds 15
        }
    } catch {
        Append-Log ("SCHEDULER LOOP ERROR: " + $_.Exception.Message) "ERROR"
        Start-Sleep -Seconds 30
    }
}
