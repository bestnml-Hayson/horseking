$ErrorActionPreference = "Continue"
$rootDir = "d:\Trae\horse"
$dataDir = Join-Path $rootDir "data"
$statsDir = Join-Path $dataDir "stats"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

function Write-JsonFile {
    param([string]$Path, [object]$Data)
    $json = $Data | ConvertTo-Json -Depth 20 -Compress:$false
    [IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}
function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $text = [IO.File]::ReadAllText($Path, $utf8NoBom)
    return $text | ConvertFrom-Json -Depth 20
}

$raceDate = "20260923"
$venue = "HV"
$baseUrl = "https://racing.on.cc"

Write-Host "[FETCH CC RACING] Date: $raceDate Venue: $venue"
Write-Host "[FETCH CC RACING] This script requires: (1) HTML cache files via Integrated Browser, or (2) pre-parsed JSON from browser evaluate"
Write-Host "[FETCH CC RACING] Running in MERGE mode - using data fetched manually via Integrated Browser..."
Write-Host ""

$outPath = Join-Path $statsDir "jkcstat_$raceDate.json"
$existing = Read-JsonFile $outPath

$base = [ordered]@{
    meta = [ordered]@{
        import_from = "https://racing.on.cc/index.html"
        import_date = $raceDate.Substring(0,4) + "-" + $raceDate.Substring(4,2) + "-" + $raceDate.Substring(6,2)
        venue = "$venue " + ($venue -eq "HV" ? "跑馬地" : "沙田")
        race_date = $raceDate.Substring(0,4) + "-" + $raceDate.Substring(4,2) + "-" + $raceDate.Substring(6,2)
        fetch_script = "_fetch_cc_racing.ps1"
        fetch_mode = "Manual Integrated Browser + PowerShell merge"
        note = "東方日報 racing.on.cc 3 大核心數據：排位表(cc_barrier) / 11名家最後來料(cc_expert_tips) / 晨操(cc_trackwork)；merge key = (race_no + horse_no)"
    }
}

if ($existing -and $existing.jockey_championship) {
    $base.jockey_championship = $existing.jockey_championship
    $base.trainer_championship_top_10 = $existing.trainer_championship_top_10
}
$base.meta.jc_stat_inherited = $true

$base["cc_barrier"] = [ordered]@{}
$base["cc_expert_tips"] = [ordered]@{}
$base["cc_expert_tips_detail"] = [ordered]@{}
$base["cc_hot_horses"] = [ordered]@{}
$base["cc_trackwork"] = [ordered]@{}
$base["cc_sources"] = [ordered]@{
    barrier_index_page = "$baseUrl/racing/ifo/current/rjifoa0001x0.html (1→9 per race)"
    expert_fav_page = "$baseUrl/racing/fav/current/rjfavg0001x0.html (11名家 2場×4匹)"
    trackwork_morning_page = "$baseUrl/racing/mor/current/rjmorc0001x0.html (全場晨操)"
    barrier_notes = "每場獨立頁：rjifoa000{X}x0.html 替換 {X} 為 1-9"
}

Write-Host "[FETCH CC RACING] Built JSON skeleton with 3 sections"
Write-Host "[FETCH CC RACING] Next steps after writing skeleton:"
Write-Host "   1. Use Integrated Browser to EVALUATE expert tips JSON -> paste into cc_expert_tips / cc_hot_horses"
Write-Host "   2. Fetch 9x barrier pages (rjifoa0001-0009x0) -> cc_barrier.race_X"
Write-Host "   3. Fetch full trackwork page rjmorc0001x0 -> cc_trackwork.race_X"
Write-Host "   4. Run _merge_cc_stats.ps1 -> writes cc_* to each CURRENT race JSON"
Write-Host ""

Write-JsonFile $outPath $base
Write-Host "[FETCH CC RACING] Skeleton written: $outPath" -ForegroundColor Green

& "$rootDir\_merge_cc_stats.ps1"

exit 0
