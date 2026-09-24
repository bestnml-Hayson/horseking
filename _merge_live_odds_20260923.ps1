$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$historyDir = "d:\Trae\horse\data\history"

$r123path = "d:\Trae\horse\data\references\_odds_HV_20260923_R123.json"
$r456789path = "d:\Trae\horse\data\references\_odds_HV_20260923_R456789.json"

$r123txt = [System.IO.File]::ReadAllText($r123path, [System.Text.Encoding]::UTF8)
$r456789txt = [System.IO.File]::ReadAllText($r456789path, [System.Text.Encoding]::UTF8)

$PSMin = $PSVersionTable.PSVersion.Major
if ($PSMin -ge 7) {
    $r123 = $r123txt | ConvertFrom-Json -Depth 8
    $r456789 = $r456789txt | ConvertFrom-Json -Depth 8
} else {
    $r123 = $r123txt | ConvertFrom-Json
    $r456789 = $r456789txt | ConvertFrom-Json
}

$list = New-Object System.Collections.ArrayList
foreach ($r in $r123) { [void]$list.Add($r) }
foreach ($r in $r456789) { [void]$list.Add($r) }
$allOdds = $list.ToArray()

Write-Host ("Loaded odds races: " + $allOdds.Count)
foreach ($r in $allOdds) {
    Write-Host ("  R" + $r.raceNumber + "  horses=" + $r.horses.Count + "  updated=" + $r.updateTime)
}
Write-Host ""

$totalUpdated = 0
$racesUpdated = 0
foreach ($oddsRace in $allOdds) {
    $rn = [int]$oddsRace.raceNumber
    $pattern = ("HV-20260923-{0:D2}_race{1}_*_CURRENT.json" -f $rn, $rn)
    $raceFiles = Get-ChildItem -Path $historyDir -Filter $pattern
    if (-not $raceFiles -or $raceFiles.Count -eq 0) {
        Write-Host ("WARN R" + $rn + ": no matching CURRENT JSON, pattern=" + $pattern)
        continue
    }
    $racePath = $raceFiles[0].FullName
    Write-Host ("R" + $rn + " file: " + $raceFiles[0].Name)
    $raceRaw = [System.IO.File]::ReadAllText($racePath, [System.Text.Encoding]::UTF8)
    if ($PSMin -ge 7) { $race = $raceRaw | ConvertFrom-Json -Depth 10 } else { $race = $raceRaw | ConvertFrom-Json }

    $byNumber = @{}
    foreach ($h in $oddsRace.horses) {
        if ($h.number) { $byNumber[[int]$h.number] = $h }
    }
    $byName = @{}
    foreach ($h in $oddsRace.horses) {
        if ($h.name) { $byName[$h.name] = $h }
    }

    $arr = New-Object System.Collections.ArrayList
    foreach ($h in $race.horses) { [void]$arr.Add($h) }

    $upd = 0
    for ($i = 0; $i -lt $arr.Count; $i++) {
        $rh = $arr[$i]
        $matchH = $null
        if ($rh.number -and $byNumber.ContainsKey([int]$rh.number)) {
            $matchH = $byNumber[[int]$rh.number]
        } elseif ($rh.name -and $byName.ContainsKey($rh.name)) {
            $matchH = $byName[$rh.name]
        }
        if ($matchH) {
            try {
                $w = [double]$matchH.odds_win
                $p = [double]$matchH.odds_place
                if (-not [double]::IsNaN($w) -and $w -gt 0) {
                    $arr[$i].odds_win = $w
                }
                if (-not [double]::IsNaN($p) -and $p -gt 0) {
                    $arr[$i].odds_place = $p
                }
                $upd++
            } catch {
                Write-Host ("  WARN R" + $rn + " #" + $rh.number + " odds parse err: " + $_.Exception.Message)
            }
        } else {
            Write-Host ("  WARN no match: R" + $rn + "  #" + $rh.number + " name=" + $rh.name + " code=" + $rh.code)
        }
    }
    $race.horses = $arr.ToArray()

    $meta = $race.meta
    $metaProps = $meta.PSObject.Properties.Name
    if (-not ($metaProps -contains "odds_update_time")) {
        $meta | Add-Member -NotePropertyName "odds_update_time" -NotePropertyValue ([string]$oddsRace.updateTime) -Force
    } else {
        $meta.odds_update_time = [string]$oddsRace.updateTime
    }
    if (-not ($metaProps -contains "odds_source")) {
        $meta | Add-Member -NotePropertyName "odds_source" -NotePropertyValue ("bet.hkjc.com WP live: " + [string]$oddsRace.url) -Force
    } else {
        $meta.odds_source = "bet.hkjc.com WP live: " + [string]$oddsRace.url
    }
    $race.meta.update_time = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $race.race_info.result_available = $false

    if ($PSMin -ge 7) { $outJson = $race | ConvertTo-Json -Depth 10 } else { $outJson = $race | ConvertTo-Json -Depth 10 }
    [System.IO.File]::WriteAllText($racePath, $outJson, $utf8NoBom)
    Write-Host ("  OK R" + $rn + ": updated " + $upd + "/" + $arr.Count + " horses")
    $totalUpdated += $upd
    $racesUpdated++
}

Write-Host ""
Write-Host ("=== DONE: races=" + $racesUpdated + "  horses_updated=" + $totalUpdated + " ===")
