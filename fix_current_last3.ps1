$ErrorActionPreference = "Stop"

$histDir = Join-Path $PSScriptRoot "data\history"
$curFiles = Get-ChildItem (Join-Path $histDir "*_CURRENT.json") | Sort-Object Name
Write-Host ("Found {0} CURRENT files to fix" -f $curFiles.Count)

$utf8NoBom = New-Object System.Text.UTF8Encoding $false

foreach ($f in $curFiles) {
    $raw = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    $d = $raw | ConvertFrom-Json
    $fixedCount = 0
    foreach ($h in $d.horses) {
        if (-not $h.last_3) { continue }
        $newLast3 = @()
        $changed = $false
        foreach ($el in $h.last_3) {
            if ($el -is [PSCustomObject]) {
                $newLast3 += $el
            } else {
                try { $fn = [int]$el } catch { $fn = 0 }
                $newLast3 += [PSCustomObject]@{ finish = $fn }
                $changed = $true
            }
        }
        if ($changed) {
            $h.last_3 = $newLast3
            $fixedCount++
        }
    }
    if ($fixedCount -gt 0) {
        $json = $d | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($f.FullName, $json, $utf8NoBom)
        Write-Host ("  FIXED {0}: {1} horses" -f $f.Name, $fixedCount)
    } else {
        Write-Host ("  OK {0}: no changes" -f $f.Name)
    }
}

Write-Host "Done."
exit 0