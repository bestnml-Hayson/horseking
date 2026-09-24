$ErrorActionPreference = "Stop"

$histDir = Join-Path $PSScriptRoot "data\history"
$profilesDir = Join-Path $PSScriptRoot "data\profiles"
$statsDir = Join-Path $PSScriptRoot "data\stats"

if (-not (Test-Path $profilesDir)) { New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null }
if (-not (Test-Path $statsDir)) { New-Item -ItemType Directory -Path $statsDir -Force | Out-Null }

$utf8NoBom = New-Object System.Text.UTF8Encoding $false

# Load all finished races (exclude CURRENT and summary)
$allFiles = Get-ChildItem (Join-Path $histDir "*.json") | Where-Object { $_.Name -notmatch "_CURRENT\.json$" -and $_.Name -notmatch "_scrape_summary\.json$" } | Sort-Object Name
Write-Host ("Total JSON files found: {0}" -f $allFiles.Count)

$finished = @()
foreach ($f in $allFiles) {
    try {
        $raw = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
        $d = $raw | ConvertFrom-Json
        if ($d.race_info -and $d.race_info.result_available -eq $true -and $d.race_info.official_result.Count -gt 0) {
            $finished += $d
        }
    } catch {
        Write-Host ("  SKIP bad JSON: {0}" -f $f.Name)
    }
}

# Sort chronologically by date asc, race_number asc
$finished = $finished | Sort-Object { $_.race_info.race_date }, { [int]$_.race_info.race_number }
Write-Host ("Valid finished races with results: {0}" -f $finished.Count)

# Aggregate dictionaries
$jockeys = @{}
$trainers = @{}
$horses = @{}
$horseDist = @{}
$jockeyHorse = @{}

function GetOrAdd($dict, $key, $default) {
    if (-not $dict.ContainsKey($key)) { $dict[$key] = & $default }
    return $dict[$key]
}

foreach ($race in $finished) {
    $ri = $race.race_info
    $dist = [int]$ri.distance_m
    $date = $ri.race_date
    $rn = [int]$ri.race_number
    # Build lookup from official_result: code -> finish
    $resLookup = @{}
    $minOfficialFinish = 99
    $winnerByOfficial = $null
    foreach ($r in $ri.official_result) {
        try { $fc = [int]$r.finish } catch { $fc = 99 }
        $key = [string]$r.code
        if ($key -and $key -ne "") { $resLookup[$key] = [PSCustomObject]@{ finish = $fc } }
        if ($fc -lt $minOfficialFinish) { $minOfficialFinish = $fc; $winnerByOfficial = $key }
    }
    # Find winner from horses[] finish (if official_result missing finish=1)
    $minHorseFinish = 99
    $winnerByHorse = $null
    foreach ($h in $race.horses) {
        $hcT = [string]$h.code
        if (-not $hcT -or $hcT -eq "") { continue }
        $finH = 99
        if ($h.PSObject.Properties["finish"] -and $h.finish) {
            try { $finH = [int]$h.finish } catch { $finH = 99 }
        }
        if ($finH -lt $minHorseFinish) { $minHorseFinish = $finH; $winnerByHorse = $hcT }
    }
    $winnerCode = $null
    if ($minOfficialFinish -eq 1 -and $winnerByOfficial) {
        $winnerCode = [string]$winnerByOfficial
    } elseif ($minHorseFinish -eq 1 -and $winnerByHorse) {
        $winnerCode = [string]$winnerByHorse
    } elseif ($minOfficialFinish -ge 2 -and $winnerByOfficial) {
        $winnerCode = [string]$winnerByOfficial
    }
    # Iterate horses array (has jockey/trainer/best_time/finish)
    foreach ($h in $race.horses) {
        $hc = [string]$h.code
        $hname = [string]$h.name
        $jok = [string]$h.jockey
        $trn = [string]$h.trainer
        if (-not $hc -or $hc -eq "") { continue }
        $finish = 99
        # Priority 1: horses.finish (direct field from scraper)
        if ($h.PSObject.Properties["finish"] -and $h.finish) {
            try { $finish = [int]$h.finish } catch {}
        }
        # Priority 2: official_result lookup (fallback)
        if ($finish -ge 99 -and $resLookup.ContainsKey($hc)) {
            $finish = $resLookup[$hc].finish
        }
        $won = ($finish -eq 1)
        if (-not $won -and $winnerCode -and ($hc -eq $winnerCode)) {
            $won = $true
            if ($finish -ge 99) { $finish = 1 }
        }
        $inq = ($finish -ge 1 -and $finish -le 4)

        # Jockey
        if ($jok -and $jok -ne "") {
            $j = GetOrAdd $jockeys $jok { [PSCustomObject]@{ starts=0; wins=0; q_count=0 } }
            $j.starts++
            if ($won) { $j.wins++ }
            if ($inq) { $j.q_count++ }
        }

        # Trainer
        if ($trn -and $trn -ne "") {
            $t = GetOrAdd $trainers $trn { [PSCustomObject]@{ starts=0; wins=0; q_count=0 } }
            $t.starts++
            if ($won) { $t.wins++ }
            if ($inq) { $t.q_count++ }
        }

        # Horse
        $hs = GetOrAdd $horses $hc { [PSCustomObject]@{ name=$hname; starts=0; wins=0; q_count=0; sum_finish=0; best_time=[double]::MaxValue; ratings=@(); last_run=""; last_place=0 } }
        if (-not $hs.name -or $hs.name -eq "") { $hs.name = $hname }
        $hs.starts++
        if ($won) { $hs.wins++ }
        if ($inq) { $hs.q_count++ }
        if ($finish -lt 99) { $hs.sum_finish += $finish }
        if ($h.best_time_sec -and [double]$h.best_time_sec -gt 0 -and [double]$h.best_time_sec -lt $hs.best_time) { $hs.best_time = [double]$h.best_time_sec }
        if ($h.rating) { $hs.ratings += [int]$h.rating }
        $hs.last_run = $date
        if ($finish -lt 99) { $hs.last_place = $finish }

        # Horse x Distance
        $hd = GetOrAdd $horseDist $hc { @{} }
        $dk = [string]$dist
        $dobj = GetOrAdd $hd $dk { [PSCustomObject]@{ starts=0; sum_finish=0; wins=0 } }
        $dobj.starts++
        if ($finish -lt 99) { $dobj.sum_finish += $finish }
        if ($won) { $dobj.wins++ }

        # Jockey x Horse
        if ($jok -and $jok -ne "") {
            $jk = "{0}|{1}" -f $jok, $hc
            $jh = GetOrAdd $jockeyHorse $jk { [PSCustomObject]@{ starts=0; wins=0 } }
            $jh.starts++
            if ($won) { $jh.wins++ }
        }
    }
}

# Post-process: compute rates (copy keys to array first - avoid Collection modified error)
$jkeys = @($jockeys.Keys)
foreach ($k in $jkeys) {
    $j = $jockeys[$k]
    $wr = if ($j.starts -gt 0) { [double]$j.wins / $j.starts } else { 0.0 }
    $qr = if ($j.starts -gt 0) { [double]$j.q_count / $j.starts } else { 0.0 }
    $jockeys[$k] = [PSCustomObject]@{ starts=$j.starts; wins=$j.wins; q_count=$j.q_count; win_rate=[math]::Round($wr,6); q_rate=[math]::Round($qr,6) }
}

$tkeys = @($trainers.Keys)
foreach ($k in $tkeys) {
    $t = $trainers[$k]
    $wr = if ($t.starts -gt 0) { [double]$t.wins / $t.starts } else { 0.0 }
    $qr = if ($t.starts -gt 0) { [double]$t.q_count / $t.starts } else { 0.0 }
    $trainers[$k] = [PSCustomObject]@{ starts=$t.starts; wins=$t.wins; q_count=$t.q_count; win_rate=[math]::Round($wr,6); q_rate=[math]::Round($qr,6) }
}

$hkeys = @($horses.Keys)
foreach ($k in $hkeys) {
    $h = $horses[$k]
    $avgF = if ($h.starts -gt 0 -and $h.sum_finish -gt 0) { [math]::Round([double]$h.sum_finish / $h.starts, 3) } else { 0.0 }
    $bt = if ($h.best_time -lt [double]::MaxValue) { [math]::Round($h.best_time, 3) } else { 0.0 }
    $rAvg = 0.0; if ($h.ratings.Count -gt 0) { $sumR = 0; foreach ($r in $h.ratings) { $sumR += $r }; $rAvg = [math]::Round([double]$sumR / $h.ratings.Count, 1) }
    $horses[$k] = [PSCustomObject]@{ name=$h.name; starts=$h.starts; wins=$h.wins; q_count=$h.q_count; avg_finish=$avgF; best_time=$bt; rating_avg=$rAvg; last_run=$h.last_run; last_place=$h.last_place }
}

$hdkeys = @($horseDist.Keys)
foreach ($hc in $hdkeys) {
    $dk = $horseDist[$hc]
    $outObj = @{}
    $dkeys = @($dk.Keys)
    foreach ($d in $dkeys) {
        $o = $dk[$d]
        $af = if ($o.starts -gt 0 -and $o.sum_finish -gt 0) { [math]::Round([double]$o.sum_finish / $o.starts, 3) } else { 0.0 }
        $outObj[$d] = [PSCustomObject]@{ starts=$o.starts; avg_finish=$af; wins=$o.wins }
    }
    $horseDist[$hc] = [PSCustomObject]$outObj
}

$jhkeys = @($jockeyHorse.Keys)
foreach ($k in $jhkeys) {
    $o = $jockeyHorse[$k]
    $wr = if ($o.starts -gt 0) { [math]::Round([double]$o.wins / $o.starts, 6) } else { 0.0 }
    $jockeyHorse[$k] = [PSCustomObject]@{ starts=$o.starts; wins=$o.wins; win_rate=$wr }
}

# Wrap in structure matching app.js expectations: {jockeys:...} / {trainers:...} / {horses:...}
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$jockeysFinal = [PSCustomObject]@{ meta=[PSCustomObject]@{ generated_at=$ts; source_races=$finished.Count }; jockeys=[PSCustomObject]$jockeys }
$trainersFinal = [PSCustomObject]@{ meta=[PSCustomObject]@{ generated_at=$ts; source_races=$finished.Count }; trainers=[PSCustomObject]$trainers }
$horsesFinal = [PSCustomObject]@{ meta=[PSCustomObject]@{ generated_at=$ts; source_races=$finished.Count }; horses=[PSCustomObject]$horses }
$hdFinal = [PSCustomObject]@{ meta=[PSCustomObject]@{ generated_at=$ts; source_races=$finished.Count }; horseDistance=[PSCustomObject]$horseDist }
$jhFinal = [PSCustomObject]@{ meta=[PSCustomObject]@{ generated_at=$ts; source_races=$finished.Count }; jockeyHorse=[PSCustomObject]$jockeyHorse }

function Write-JsonSafe($path, $obj) {
    $json = $obj | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($path, $json, $utf8NoBom)
    $sz = (Get-Item $path).Length
    Write-Host ("  WROTE {0} ({1} bytes)" -f [System.IO.Path]::GetFileName($path), $sz)
}

Write-Host "Writing aggregate DBs..."
Write-JsonSafe (Join-Path $statsDir "jockeys_db.json") $jockeysFinal
Write-JsonSafe (Join-Path $statsDir "trainers_db.json") $trainersFinal
Write-JsonSafe (Join-Path $profilesDir "horses_db.json") $horsesFinal
Write-JsonSafe (Join-Path $statsDir "horse_distance_stats.json") $hdFinal
Write-JsonSafe (Join-Path $statsDir "jockey_horse_stats.json") $jhFinal

# Verify summary
Write-Host ""
Write-Host ("Jockeys: {0}" -f $jockeys.Count)
Write-Host ("Trainers: {0}" -f $trainers.Count)
Write-Host ("Horses: {0}" -f $horses.Count)
$topJ = $jockeys.GetEnumerator() | Sort-Object { $_.Value.starts } -Descending | Select-Object -First 3
foreach ($t in $topJ) { Write-Host ("  J {0}: starts={1}, WR={2}%" -f $t.Key, $t.Value.starts, [math]::Round($t.Value.win_rate*100,1)) }
$topH = $horses.GetEnumerator() | Sort-Object { $_.Value.starts } -Descending | Select-Object -First 3
foreach ($t in $topH) { Write-Host ("  H {0} ({1}): starts={2}" -f $t.Key, $t.Value.name, $t.Value.starts) }

Write-Host "Done."
exit 0