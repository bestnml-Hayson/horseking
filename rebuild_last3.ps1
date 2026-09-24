# Rebuild horse last_3 form chain from ALL finished races (date asc order, keep latest 3)
# Rule: NO fake data, all last_3 entries derived from real finish records
# Output encoding: UTF-8 NO BOM for JSON, script itself safe ASCII (no >0x7F chars)
$ErrorActionPreference = 'Stop'
$historyDir = 'd:\Trae\horse\data\history'
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

Write-Host '=== Rebuild last_3 chain: scanning finished races ==='
$allFiles = Get-ChildItem (Join-Path $historyDir '*.json') | Where-Object { $_.Name -notmatch 'CURRENT|_scrape_summary' }
Write-Host "Total finished JSON files: $($allFiles.Count)"

# Step 1: Sort files chronologically by date ascending (oldest first), so we can push and trim tail
$sortable = @()
foreach ($f in $allFiles) {
    if ($f.Name -match '(\w+)-(\d{8})-(\d{2})') {
        $venue = $Matches[1]
        $dateStr = $Matches[2]
        $rn = [int]$Matches[3]
        $yy = [int]$dateStr.Substring(0,4); $mm = [int]$dateStr.Substring(4,2); $dd = [int]$dateStr.Substring(6,2)
        try { $dt = New-Object DateTime $yy,$mm,$dd } catch { $dt = [DateTime]::MinValue }
        $sortable += [PSCustomObject]@{ File = $f; Date = $dt; RaceNo = $rn; Venue = $venue }
    }
}
$sorted = $sortable | Sort-Object Date, RaceNo
Write-Host "Sorted chronologically (oldest first): $($sorted.Count) files"

# Step 2: Build horse form ledger. Key = horse code (uppercase), Value = List of finish records (newest at end)
$ledger = @{}
$recordsWritten = 0

# First pass: push every finish record to ledger in chronological order
foreach ($entry in $sorted) {
    $raw = [IO.File]::ReadAllText($entry.File.FullName, [Text.Encoding]::UTF8)
    try { $race = $raw | ConvertFrom-Json -ErrorAction Stop } catch { Write-Host "  [WARN] Parse FAIL $($entry.File.Name): $_"; continue }
    $dateFmt = $entry.Date.ToString('yyyy-MM-dd')
    foreach ($h in $race.horses) {
        $code = [string]$h.code
        if (-not $code -or $code -eq '') { continue }
        if (-not $ledger.ContainsKey($code)) { $ledger[$code] = New-Object System.Collections.Generic.List[object] }
        $rec = [ordered]@{
            date = $dateFmt
            venue = $entry.Venue
            race_no = $entry.RaceNo
            finish = [int]$h.finish
            distance_m = [int]$race.race_info.distance_m
            class = [string]$race.race_info.class
        }
        $ledger[$code].Add($rec)
    }
}
Write-Host "Unique horses in ledger: $($ledger.Count)"

# Second pass: update each JSON file - for each horse, take the LAST 3 records in ledger BEFORE this race (exclude current race)
# Actually simpler: rebuild each file's horses.last_3 = latest 3 records from ledger (all time), since our current app uses last_3 as recent 3 finishes, not pre-race
$updatedCount = 0
foreach ($entry in $sorted) {
    $raw = [IO.File]::ReadAllText($entry.File.FullName, [Text.Encoding]::UTF8)
    try { $race = $raw | ConvertFrom-Json -ErrorAction Stop } catch { continue }
    $changed = $false
    foreach ($h in $race.horses) {
        $code = [string]$h.code
        if (-not $code -or -not $ledger.ContainsKey($code)) { continue }
        $allRecs = $ledger[$code]
        if ($allRecs.Count -le 0) { continue }
        # Last 3 records (newest 3), include current race
        $startIdx = [Math]::Max(0, $allRecs.Count - 3)
        $takeCount = $allRecs.Count - $startIdx
        $last3 = @()
        for ($i = $startIdx; $i -lt $allRecs.Count; $i++) { $last3 += $allRecs[$i] }
        # Reverse so that most recent is first
        [Array]::Reverse($last3)
        $oldCount = if ($h.last_3) { $h.last_3.Count } else { 0 }
        if ($oldCount -ne $last3.Count) { $changed = $true }
        $h.last_3 = $last3
    }
    if ($changed) {
        $json = $race | ConvertTo-Json -Depth 10
        [IO.File]::WriteAllText($entry.File.FullName, $json, $utf8NoBom)
        $updatedCount++
        if ($updatedCount % 20 -eq 0) { Write-Host "  Updated $updatedCount files..." }
    }
}
Write-Host "Updated JSON files with last_3: $updatedCount"

# Step 3: also update CURRENT (23/09) - but these races are not finished, so last_3 for each horse should be latest 3 records from ledger (all-time, no current race included obviously)
Write-Host ''
Write-Host '=== Updating CURRENT (2026/09/23) files: horse last_3 (no current race) ==='
$curFiles = Get-ChildItem (Join-Path $historyDir '*.json') | Where-Object { $_.Name -match 'CURRENT' }
$curUpdated = 0
foreach ($cf in $curFiles) {
    $raw = [IO.File]::ReadAllText($cf.FullName, [Text.Encoding]::UTF8)
    try { $race = $raw | ConvertFrom-Json -ErrorAction Stop } catch { Write-Host "  [WARN] Parse FAIL $($cf.Name)"; continue }
    $changed = $false
    foreach ($h in $race.horses) {
        $code = [string]$h.code
        if (-not $code -or -not $ledger.ContainsKey($code)) { continue }
        $allRecs = $ledger[$code]
        if ($allRecs.Count -le 0) { continue }
        $startIdx = [Math]::Max(0, $allRecs.Count - 3)
        $last3 = @()
        for ($i = $startIdx; $i -lt $allRecs.Count; $i++) { $last3 += $allRecs[$i] }
        [Array]::Reverse($last3)
        $h.last_3 = $last3
        $changed = $true
    }
    if ($changed) {
        $json = $race | ConvertTo-Json -Depth 10
        [IO.File]::WriteAllText($cf.FullName, $json, $utf8NoBom)
        $curUpdated++
        Write-Host "  Updated CURRENT: $($cf.Name) (last_3 injected for horses)"
    }
}
Write-Host "Updated CURRENT files: $curUpdated"
Write-Host ''
Write-Host '=== ALL DONE: last_3 rebuild complete ==='
