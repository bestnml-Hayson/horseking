$ErrorActionPreference = "Stop"
$syncScript = Join-Path $PSScriptRoot "sync_data.ps1"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
function ExtractJson([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $lastOpen = $text.LastIndexOf('{')
    $lastClose = $text.LastIndexOf('}')
    if ($lastOpen -lt 0 -or $lastClose -lt 0 -or $lastClose -le $lastOpen) { return $null }
    return $text.Substring($lastOpen, ($lastClose - $lastOpen + 1))
}
try {
    $rawOutput = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $syncScript
    $sw.Stop()
    $elapsed = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
    $parseOk = $false
    $outObj = $null
    $fullText = $null
    if ($rawOutput) {
        $fullText = ($rawOutput | Out-String).Trim()
        $jsonPart = ExtractJson $fullText
        if ($jsonPart) {
            try {
                $outObj = $jsonPart | ConvertFrom-Json -ErrorAction Stop
                if ($outObj) { $parseOk = $true }
            } catch {
                $parseOk = $false
            }
        }
    }
    if (-not $parseOk) {
        $outObj = New-Object PSObject
        $outObj | Add-Member NoteProperty ok $false
        $outObj | Add-Member NoteProperty message "sync_data.ps1 parse failed"
        if ($fullText) {
            $snippet = $fullText.Substring(0, [Math]::Min(600, $fullText.Length))
            $outObj | Add-Member NoteProperty raw_output $snippet
        }
    }
    try {
        $outObj | Add-Member NoteProperty duration_sec $elapsed -Force
    } catch {}
    $outObj | ConvertTo-Json -Depth 10 -Compress
    exit 0
} catch {
    $sw.Stop()
    $elapsed = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
    $errObj = New-Object PSObject
    $errObj | Add-Member NoteProperty ok $false
    $errObj | Add-Member NoteProperty error $_.Exception.Message
    $errObj | Add-Member NoteProperty duration_sec $elapsed
    $errObj | ConvertTo-Json -Depth 5 -Compress
    exit 1
}
