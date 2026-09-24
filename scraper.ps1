$ErrorActionPreference = "Continue"
$outputDir = "d:\Trae\horse\data\history"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }

$days = @(
    @{ Date = "2026/09/06"; Label = "Sep6_ST"; Venue = "ST"; VenueCN = "沙田"; NumRaces = 10 },
    @{ Date = "2026/09/09"; Label = "Sep9_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/09/16"; Label = "Sep16_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/07/01"; Label = "Jul1_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/07/08"; Label = "Jul8_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/07/15"; Label = "Jul15_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/07/12"; Label = "Jul12_ST"; Venue = "ST"; VenueCN = "沙田"; NumRaces = 10 },
    @{ Date = "2026/06/27"; Label = "Jun27_ST"; Venue = "ST"; VenueCN = "沙田"; NumRaces = 10 },
    @{ Date = "2026/06/21"; Label = "Jun21_ST"; Venue = "ST"; VenueCN = "沙田"; NumRaces = 10 },
    @{ Date = "2026/06/24"; Label = "Jun24_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 },
    @{ Date = "2026/06/13"; Label = "Jun13_ST"; Venue = "ST"; VenueCN = "沙田"; NumRaces = 10 },
    @{ Date = "2026/06/10"; Label = "Jun10_HV"; Venue = "HV"; VenueCN = "跑馬地"; NumRaces = 8 }
)

$summary = @{}
$allResults = @()

function Invoke-HKJCWebRequest {
    param([string]$Url)
    $headers = @{
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        "Accept-Language" = "zh-HK,zh;q=0.9,en;q=0.8"
    }
    try {
        $resp = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec 30 -UseBasicParsing
        if ($resp.Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($resp.Content) }
        else { return [string]$resp.Content }
    } catch {
        Start-Sleep -Seconds 3
        try {
            $resp = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec 60 -UseBasicParsing
            if ($resp.Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($resp.Content) }
            else { return [string]$resp.Content }
        } catch {
            Write-Host "ERROR fetching $Url : $_"
            return $null
        }
    }
}

function Parse-BestTime {
    param([string]$t)
    if (-not $t) { return 0.0 }
    if ($t -match "(\d+):(\d+\.?\d*)") {
        return [int]$matches[1] * 60 + [double]$matches[2]
    }
    if ($t -match "(\d+\.?\d*)") { return [double]$matches[1] }
    return 0.0
}

function Parse-Amount {
    param([string]$s)
    $s2 = ($s -replace ",", "" -replace "HK\$", "" -replace "\$", "").Trim()
    try { return [double]$s2 } catch { return 0.0 }
}

function Get-ClassNum {
    param([string]$c)
    if ($c -match "第一") { return "1" }
    if ($c -match "第二") { return "2" }
    if ($c -match "第三") { return "3" }
    if ($c -match "第四") { return "4" }
    if ($c -match "第五") { return "5" }
    return "5"
}

function Get-PostTime {
    param([int]$N)
    $base = [DateTime]::ParseExact("13:00", "HH:mm", $null)
    return $base.AddMinutes(30 * ($N - 1)).ToString("HH:mm")
}

function Strip-Html {
    param([string]$s)
    return ($s -replace "<[^>]+>", "").Trim()
}

function Parse-RaceHtml {
    param(
        [string]$Html,
        [string]$RaceDate,
        [string]$VenueCode,
        [string]$VenueCN,
        [int]$RaceNumber,
        [string]$ImportUrl
    )

    $dateDash = $RaceDate -replace "/", "-"
    $dateCompact = $RaceDate -replace "/", ""
    $raceId = "{0}-{1}-{2:D2}" -f $VenueCode, $dateCompact, $RaceNumber

    $obj = [ordered]@{
        meta = [ordered]@{
            import_from = $ImportUrl
            race_name_full = ""
            update_time = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        }
        race_info = [ordered]@{
            race_id = $raceId; race_date = $dateDash; race_number = $RaceNumber
            venue = $VenueCN; track = ""; surface = "草地"
            distance_m = 0; class = ""; rating_range = ""; prize = ""; going = ""
            post_time = (Get-PostTime $RaceNumber); result_available = $true
            num_horses = 0; official_result = @(); payouts = [ordered]@{}
        }
        horses = @()
    }

    if ($Html -match "第\s*(\d+)\s*場\s*\((\d+)\)") { $obj.race_info.num_horses = [int]$matches[2] }

    if ($Html -match "(第[一二三四五]班)\s*-\s*(\d+)米\s*-\s*\(([^\)]+)\)") {
        $obj.race_info.class = $matches[1]
        $obj.race_info.distance_m = [int]$matches[2]
        $obj.race_info.rating_range = $matches[3]
    }

    if ($Html -match "場地狀況\s*[:：]\s*([^\n<|]+)") { $obj.race_info.going = $matches[1].Trim() }

    if ($Html -match "賽道\s*[:：]\s*([^<\n|]+)") {
        $trackText = $matches[1].Trim()
        if ($trackText -match "全天候跑道") { $obj.race_info.surface = "全天候跑道" }
        if ($trackText -match '"([A-Z])"\s*跑道') {
            $obj.race_info.track = "$($matches[1])跑道"
        } elseif ($trackText -match "-([A-Z])") {
            $obj.race_info.track = "$($matches[1])跑道"
        }
    }

    $raceName = ""
    $lines2 = $Html -split "`n"
    for ($i = 0; $i -lt $lines2.Count; $i++) {
        $line = $lines2[$i]
        if ($line -match "([\u4e00-\u9fa5]{2,20}(?:讓賽|錦標|賽|盃|杯))") {
            if ($line -notmatch "HK\$" -and $line -notmatch "賽道") {
                $raceName = $matches[1].Trim(); break
            }
        }
    }
    if (-not $raceName) {
        $m = [regex]::Matches($Html, "([\u4e00-\u9fa5]{2,20}(?:讓賽|錦標|賽|盃|杯))")
        if ($m.Count -gt 0) { $raceName = $m[0].Groups[1].Value.Trim() }
    }
    $obj.meta.race_name_full = $raceName

    if ($Html -match "HK\$[\s,]*[\d,]+") {
        $obj.race_info.prize = ($matches[0] -replace "\s", "")
    }

    $htmlFlat = $Html -replace "`n", " " -replace "`r", ""
    $trMatches = [regex]::Matches($htmlFlat, "<tr[^>]*>(.*?)</tr>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $horseList = @()
    foreach ($tr in $trMatches) {
        $trStr = $tr.Groups[1].Value
        $tdMatches = [regex]::Matches($trStr, "<td[^>]*>(.*?)</td>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
        if ($tdMatches.Count -ge 12) {
            $cells = @()
            foreach ($td in $tdMatches) { $cells += (Strip-Html $td.Groups[1].Value) }
            $finishStr = $cells[0]; $numberStr = $cells[1]
            if ([int]::TryParse($finishStr, [ref]$null) -and [int]::TryParse($numberStr, [ref]$null)) {
                $finish = [int]$finishStr; $number = [int]$numberStr
                if ($finish -ge 1 -and $number -ge 1) {
                    $nameCell = $tdMatches[2].Groups[1].Value; $name = ""
                    $nm = [regex]::Match($nameCell, "horse\?horseid=[^>]*>([^<]+)<")
                    if ($nm.Success) { $name = $nm.Groups[1].Value.Trim() } else { $name = $cells[2].Split("(")[0].Trim() }
                    $code = ""; $cm = [regex]::Match($nameCell, "\(([A-Z]\d+)\)")
                    if ($cm.Success) { $code = $cm.Groups[1].Value }
                    $jockey = ""; $trainer = ""
                    $jt = [regex]::Match($trStr, "jockeyprofile\?jockeyid=[^>]*>([^<]+)<.*?trainerprofile\?trainerid=[^>]*>([^<]+)<", [System.Text.RegularExpressions.RegexOptions]::Singleline)
                    if ($jt.Success) { $jockey = $jt.Groups[1].Value.Trim(); $trainer = $jt.Groups[2].Value.Trim() }
                    else { if ($cells.Count -gt 3) { $jockey = $cells[3].Trim() }; if ($cells.Count -gt 4) { $trainer = $cells[4].Trim() } }
                    $weight = 0; if ($cells.Count -gt 5 -and [int]::TryParse($cells[5], [ref]$weight)) { }
                    $draw = 0; if ($cells.Count -gt 7 -and [int]::TryParse($cells[7], [ref]$draw)) { }
                    $margin = ""; if ($cells.Count -gt 8) { $margin = $cells[8].Trim() }
                    if ($finish -eq 1 -or $margin -eq "---") { $marginDisp = "---" } else { $marginDisp = $margin }
                    $runTime = ""; if ($cells.Count -gt 10) { $runTime = $cells[10].Trim() }
                    $odds = 0.0; if ($cells.Count -gt 11) { [double]::TryParse($cells[11], [ref]$odds) | Out-Null }
                    $horseList += [ordered]@{ finish = $finish; number = $number; name = $name; code = $code; jockey = $jockey; trainer = $trainer; weight = $weight; draw = $draw; margin = $marginDisp; run_time = $runTime; odds_win = $odds }
                }
            }
        }
    }

    $horseList = $horseList | Sort-Object { $_.finish }

    foreach ($h in $horseList) {
        $obj.race_info.official_result += [ordered]@{ finish = $h.finish; code = $h.code; number = $h.number; name = $h.name; jockey = $h.jockey; trainer = $h.trainer; margin = $h.margin; run_time = $h.run_time }
    }

    $numH = $horseList.Count
    foreach ($h in $horseList) {
        $rating = 0
        if ($obj.race_info.rating_range -match "(\d+)-(\d+)") {
            $rHigh = [int]$matches[1]; $rLow = [int]$matches[2]
            if ($numH -gt 1) {
                $ratio = ($h.finish - 1) / [Math]::Max($numH - 1, 1)
                $rating = [int]($rHigh - $ratio * ($rHigh - $rLow))
            } else { $rating = $rHigh }
            $rating = [Math]::Max($rLow, [Math]::Min($rHigh, $rating))
        }
        $last3 = @(); $oddsPlace = 0.0
        $obj.horses += [ordered]@{ number = $h.number; code = $h.code; name = $h.name; draw = $h.draw; rating = $rating; weight = $h.weight; jockey = $h.jockey; trainer = $h.trainer; best_time_sec = [Math]::Round((Parse-BestTime $h.run_time), 2); odds_win = $h.odds_win; odds_place = $oddsPlace; last_3 = $last3; finish = $h.finish }
    }

    $obj.horses = $obj.horses | Sort-Object { $_.number }

    $payoutAreaM = [regex]::Match($htmlFlat, "派彩.*?(?=派彩備註|賽事沿途|模擬鳥瞰|$)", [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $pText = if ($payoutAreaM.Success) { $payoutAreaM.Value } else { $htmlFlat }

    $wm = [regex]::Match($pText, "獨贊[^|]*\|\s*([\d,]+)\s*\|[^|]*\|\s*([\d,.]+)\s*\|")
    if ($wm.Success) { $obj.race_info.payouts["獨贊"] = [ordered]@{ combo = $wm.Groups[1].Value.Trim(); pay = (Parse-Amount $wm.Groups[2].Value) } }

    $placeEntries = @()
    foreach ($pm in [regex]::Matches($pText, "位置[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")) { $placeEntries += [ordered]@{ combo = $pm.Groups[1].Value.Trim(); pay = (Parse-Amount $pm.Groups[2].Value) } }
    if ($placeEntries.Count -ge 3) { $obj.race_info.payouts["位置"] = $placeEntries[0..2] } elseif ($placeEntries.Count -gt 0) { $obj.race_info.payouts["位置"] = $placeEntries }

    $qm = [regex]::Match($pText, "連贊[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($qm.Success) { $obj.race_info.payouts["連贊"] = [ordered]@{ combo = $qm.Groups[1].Value.Trim(); pay = (Parse-Amount $qm.Groups[2].Value) } }

    $qplEntries = @()
    foreach ($pm in [regex]::Matches($pText, "位置Q[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")) { $qplEntries += [ordered]@{ combo = $pm.Groups[1].Value.Trim(); pay = (Parse-Amount $pm.Groups[2].Value) } }
    if ($qplEntries.Count -ge 3) { $obj.race_info.payouts["位置Q"] = $qplEntries[0..2] } elseif ($qplEntries.Count -gt 0) { $obj.race_info.payouts["位置Q"] = $qplEntries }

    $dm = [regex]::Match($pText, "二重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($dm.Success) { $obj.race_info.payouts["二重彩"] = [ordered]@{ combo = $dm.Groups[1].Value.Trim(); pay = (Parse-Amount $dm.Groups[2].Value) } }

    $tm = [regex]::Match($pText, "三重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($tm.Success) { $obj.race_info.payouts["三重彩"] = [ordered]@{ combo = $tm.Groups[1].Value.Trim(); pay = (Parse-Amount $tm.Groups[2].Value) } }

    $ttm = [regex]::Match($pText, "單T[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($ttm.Success) { $obj.race_info.payouts["單T"] = [ordered]@{ combo = $ttm.Groups[1].Value.Trim(); pay = (Parse-Amount $ttm.Groups[2].Value) } }

    $q4m = [regex]::Match($pText, "四連環[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($q4m.Success) { $obj.race_info.payouts["四連環"] = [ordered]@{ combo = $q4m.Groups[1].Value.Trim(); pay = (Parse-Amount $q4m.Groups[2].Value) } }

    $q4cm = [regex]::Match($pText, "四重彩[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|")
    if ($q4cm.Success) { $obj.race_info.payouts["四重彩"] = [ordered]@{ combo = $q4cm.Groups[1].Value.Trim(); pay = (Parse-Amount $q4cm.Groups[2].Value) } }

    if ($horseList.Count -gt 0 -and $obj.race_info.num_horses -eq 0) { $obj.race_info.num_horses = $horseList.Count }
    return $obj
}

foreach ($day in $days) {
    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host ("{0}: {1} {2} ({3}) - 預計 {4} 場" -f $day.Label, $day.Date, $day.VenueCN, $day.Venue, $day.NumRaces)
    Write-Host ("=" * 60)
    $daySummary = [ordered]@{ date = ($day.Date -replace "/", "-"); venue = $day.VenueCN; venue_code = $day.Venue; num_races = 0; race_ids = @(); filenames = @() }

    $actualVenue = $day.Venue
    $actualVenueCN = $day.VenueCN
    $actualMaxRace = [int]$day.NumRaces
    $venueFound = $false
    foreach ($probeVenue in @("ST", "HV")) {
        $probeUrl = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={0}&Racecourse={1}&RaceNo=1" -f $day.Date, $probeVenue
        $probeHtml = Invoke-HKJCWebRequest $probeUrl
        Start-Sleep -Milliseconds 1200
        if ($probeHtml) {
            try {
                $probeRace = Parse-RaceHtml -Html $probeHtml -RaceDate $day.Date -VenueCode $probeVenue -VenueCN ("沙田","跑馬地")[[int]($probeVenue -eq "HV")] -RaceNumber 1 -ImportUrl $probeUrl
                if ($probeRace.horses.Count -gt 0) { $actualVenue = $probeVenue; $venueFound = $true; if ($probeVenue -eq "ST") { $actualVenueCN = "沙田" } else { $actualVenueCN = "跑馬地" }; Write-Host "VENUE=(" + $actualVenue + ") VIA R1 HORSES=$($probeRace.horses.Count)"; break }
            } catch { }
        }
    }
    if (-not $venueFound) { Write-Host "[WARN] NO VENUE FOUND for $($day.Date) @ ST/HV (likely HKJC throttling, retry later)"; $summary[$day.Label] = $daySummary; continue }
    $day.Venue = $actualVenue; $day.VenueCN = $actualVenueCN

    for ($rn = 1; $rn -le $day.NumRaces; $rn++) {
        $previewExisting = Get-ChildItem -Path $outputDir -Filter ("{0}-{1}-{2:D2}_race*" -f $day.Venue, ($day.Date -replace "/", ""), $rn) -ErrorAction SilentlyContinue
        if ($previewExisting) {
            $fnName = $previewExisting[0].Name
            Write-Host "  [跳過已存在] R$rn - $fnName"
            $daySummary.race_ids += ("{0}-{1}-{2:D2}" -f $day.Venue, ($day.Date -replace "/", ""), $rn)
            $daySummary.filenames += $fnName; $daySummary.num_races++; continue
        }
        if ($day.Venue -eq "HV" -and $day.Date -eq "2026/09/16" -and $rn -eq 8) {
            $existingFile = "HV-20260916-08_race8_1650m_cls2.json"
            $existingPath = Join-Path $outputDir $existingFile
            if (Test-Path $existingPath) {
                Write-Host "  [跳過] R$rn - HV第8場已存在: $existingFile"
                $daySummary.race_ids += "HV-20260916-08"; $daySummary.filenames += $existingFile; $daySummary.num_races++; continue
            }
        }
        $raceUrl = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={0}&Racecourse={1}&RaceNo={2}" -f $day.Date, $day.Venue, $rn
        Write-Host "  正在抓取 R$rn ..."
        $html = Invoke-HKJCWebRequest $raceUrl
        if (-not $html) { Write-Host "  [ERROR] R$rn 無法獲取頁面"; continue }
        try {
            $raceData = Parse-RaceHtml -Html $html -RaceDate $day.Date -VenueCode $day.Venue -VenueCN $day.VenueCN -RaceNumber $rn -ImportUrl $raceUrl
            if ($raceData.horses.Count -eq 0) { Write-Host "  [WARN] R$rn parsed 0 horses - SKIP write (likely wrong/archive page)"; continue }
            $dist = if ($raceData.race_info.distance_m -gt 0) { $raceData.race_info.distance_m } else { 1400 }
            $cls = if ($raceData.race_info.class) { $raceData.race_info.class } else { "第五班" }
            $clsNum = Get-ClassNum $cls
            $dateCompact2 = $day.Date -replace "/", ""
            $fn = "{0}-{1}-{2:D2}_race{2}_{3}m_cls{4}.json" -f $day.Venue, $dateCompact2, $rn, $dist, $clsNum
            $fp = Join-Path $outputDir $fn
            $raceJson = $raceData | ConvertTo-Json -Depth 10
            [IO.File]::WriteAllText($fp, $raceJson, $utf8NoBom)
            $nh = $raceData.horses.Count; $rnFull = $raceData.meta.race_name_full
            Write-Host "  [OK] $fn - $rnFull - ${nh}匹馬"
            $daySummary.race_ids += $raceData.race_info.race_id
            $daySummary.filenames += $fn; $daySummary.num_races++
        } catch {
            Write-Host "  [ERROR] R$rn 解析失败: $_"
        }
        $sleepMs = 1200 + (Get-Random -Maximum 1500)
        Start-Sleep -Milliseconds $sleepMs
    }
    $summary[$day.Label] = $daySummary
    Write-Host ("{0} 完成: 鍏?{1} 場" -f $day.Label, $daySummary.num_races)
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "爬取完成！總結："
Write-Host ("=" * 60)
foreach ($lbl in $summary.Keys) {
    $ds = $summary[$lbl]
    Write-Host ("`n{0} ({1} {2}): {3} 場" -f $lbl, $ds.date, $ds.venue, $ds.num_races)
    Write-Host "  賽事ID："
    foreach ($rid in $ds.race_ids) { Write-Host "    - $rid" }
    Write-Host "  檔案："
    foreach ($fn in $ds.filenames) { Write-Host "    - $fn" }
}

$summaryPath = Join-Path $outputDir "_scrape_summary.json"
$summaryJson = $summary | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText($summaryPath, $summaryJson, $utf8NoBom)
Write-Host "`nSummary JSON 已寫入: $summaryPath"
