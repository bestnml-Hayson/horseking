$ErrorActionPreference = 'Stop'
$targetPath = Join-Path $PSScriptRoot 'scraper.ps1'
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$utf8BOM   = New-Object System.Text.UTF8Encoding $true

# ============================================================
# ALL constants via PURE ASCII [char]0xNNNN codepoints only
# No Chinese characters ANYWHERE in this file (not even comments)
# ============================================================
$C_ST   = [char]0x6C99 + [char]0x7530
$C_HV   = [char]0x8DD1 + [char]0x99AC + [char]0x5730
$C_GR   = [char]0x8349 + [char]0x5730
$C_RC   = [char]0x5834
$C_NO   = [char]0x7B2C
$C_CL   = [char]0x73ED
$C_1    = [char]0x4E00
$C_2    = [char]0x4E8C
$C_3    = [char]0x4E09
$C_4    = [char]0x56DB
$C_5    = [char]0x4E94
$C_M    = [char]0x7C73
$C_GO   = [char]0x5834+[char]0x5730+[char]0x72C0+[char]0x6CC1
$C_TR   = [char]0x8CFD + [char]0x9053
$C_AW   = [char]0x5168+[char]0x5929+[char]0x5019+[char]0x8DD1+[char]0x9053
$C_TC   = [char]0x8DD1 + [char]0x9053
$C_HD   = [char]0x8B93 + [char]0x8CFD
$C_TP   = [char]0x9326 + [char]0x6A19
$C_SAI  = [char]0x8CFD
$C_BEI  = [char]0x76C3
$C_BUI  = [char]0x676F
$C_PO   = [char]0x6D3E + [char]0x5F69
$C_PN   = [char]0x6D3E+[char]0x5F69+[char]0x5099+[char]0x8A3B
$C_RR   = [char]0x8CFD+[char]0x4E8B+[char]0x6CBF+[char]0x9014
$C_BE   = [char]0x6A21+[char]0x64EC+[char]0x9CE5+[char]0x77B0
$C_WI   = [char]0x7368 + [char]0x8D0A
$C_PL   = [char]0x4F4D + [char]0x7F6E
$C_QI   = [char]0x9023 + [char]0x8D0A
$C_DB   = [char]0x4E8C+[char]0x91CD+[char]0x5F69
$C_TB   = [char]0x4E09+[char]0x91CD+[char]0x5F69
$C_STT  = [char]0x55AE + 'T'
$C_Q4   = [char]0x56DB+[char]0x9023+[char]0x74B0
$C_QP   = [char]0x56DB+[char]0x91CD+[char]0x5F69
$C_SE   = [char]0x8DF3+[char]0x904E+[char]0x5DF2+[char]0x5B58+[char]0x5728
$C_SK   = [char]0x8DF3 + [char]0x904E
$C_EX   = [char]0x5DF2+[char]0x5B58+[char]0x5728
$C_FT   = [char]0x6B63+[char]0x5728+[char]0x6293+[char]0x53D6
$C_NF   = [char]0x7121+[char]0x6CD5+[char]0x7372+[char]0x53D6+[char]0x9801+[char]0x9762
$C_PF   = [char]0x89E3+[char]0x6790+[char]0x5931+[char]0x8D25
$C_DN   = [char]0x5B8C + [char]0x6210
$C_SD   = [char]0x722C+[char]0x53D6+[char]0x5B8C+[char]0x6210
$C_SM   = [char]0x7E3D + [char]0x7D50
$C_ES   = [char]0x9810 + [char]0x8A08
$C_PC   = [char]0x5BE6+[char]0x969B+[char]0x63A2+[char]0x6E2C+[char]0x5834+[char]0x6578
$C_RI   = [char]0x8CFD + [char]0x4E8B + 'ID'
$C_FL   = [char]0x6A94 + [char]0x6848
$C_PM   = [char]0x5339 + [char]0x99AC
$C_YW   = [char]0x5DF2 + [char]0x5BEB + [char]0x5165

# Full-width punctuation (used in regex patterns and display text)
$F_COL  = [char]0xFF1A
$F_EXC  = [char]0xFF01
$F_LP   = [char]0xFF08
$F_RP   = [char]0xFF09
$F_CMA  = [char]0xFF0C

# Class name shortcuts
$C_C1 = $C_NO + $C_1 + $C_CL
$C_C2 = $C_NO + $C_2 + $C_CL
$C_C3 = $C_NO + $C_3 + $C_CL
$C_C4 = $C_NO + $C_4 + $C_CL
$C_C5 = $C_NO + $C_5 + $C_CL
$C_PQ = $C_PL + 'Q'

$L = @()

# ============================================================
# HEADER section
# ============================================================
$L += '$ErrorActionPreference = "Continue"'
$L += '$outputDir = "d:\Trae\horse\data\history"'
$L += '$utf8NoBom = New-Object System.Text.UTF8Encoding $false'
$L += 'if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }'
$L += ''
$L += '$days = @('
$L += '    @{ Date = "2026/09/06"; Label = "Sep6_ST"; Venue = "ST"; VenueCN = "' + $C_ST + '"; NumRaces = 10 },'
$L += '    @{ Date = "2026/09/09"; Label = "Sep9_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/09/16"; Label = "Sep16_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/07/01"; Label = "Jul1_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/07/08"; Label = "Jul8_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/07/15"; Label = "Jul15_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/07/12"; Label = "Jul12_ST"; Venue = "ST"; VenueCN = "' + $C_ST + '"; NumRaces = 10 },'
$L += '    @{ Date = "2026/06/27"; Label = "Jun27_ST"; Venue = "ST"; VenueCN = "' + $C_ST + '"; NumRaces = 10 },'
$L += '    @{ Date = "2026/06/21"; Label = "Jun21_ST"; Venue = "ST"; VenueCN = "' + $C_ST + '"; NumRaces = 10 },'
$L += '    @{ Date = "2026/06/24"; Label = "Jun24_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 },'
$L += '    @{ Date = "2026/06/13"; Label = "Jun13_ST"; Venue = "ST"; VenueCN = "' + $C_ST + '"; NumRaces = 10 },'
$L += '    @{ Date = "2026/06/10"; Label = "Jun10_HV"; Venue = "HV"; VenueCN = "' + $C_HV + '"; NumRaces = 8 }'
$L += ')'
$L += ''
$L += '$summary = @{}'
$L += '$allResults = @()'
$L += ''

# ============================================================
# Invoke-HKJCWebRequest
# PS5.1 FIX: $resp.Content may be String or Byte[] depending on response.
# Always check type before encoding conversion to avoid byte cast error.
# ============================================================
$L += 'function Invoke-HKJCWebRequest {'
$L += '    param([string]$Url)'
$L += '    $headers = @{'
$L += '        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"'
$L += '        "Accept-Language" = "zh-HK,zh;q=0.9,en;q=0.8"'
$L += '    }'
$L += '    try {'
$L += '        $resp = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec 30 -UseBasicParsing'
$L += '        if ($resp.Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($resp.Content) }'
$L += '        else { return [string]$resp.Content }'
$L += '    } catch {'
$L += '        Start-Sleep -Seconds 3'
$L += '        try {'
$L += '            $resp = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec 60 -UseBasicParsing'
$L += '            if ($resp.Content -is [byte[]]) { return [System.Text.Encoding]::UTF8.GetString($resp.Content) }'
$L += '            else { return [string]$resp.Content }'
$L += '        } catch {'
$L += '            Write-Host "ERROR fetching $Url : $_"'
$L += '            return $null'
$L += '        }'
$L += '    }'
$L += '}'
$L += ''

# ============================================================
# Helper functions (Parse-BestTime, Parse-Amount, Get-ClassNum, etc.)
# ============================================================
$L += 'function Parse-BestTime {'
$L += '    param([string]$t)'
$L += '    if (-not $t) { return 0.0 }'
$L += '    if ($t -match "(\d+):(\d+\.?\d*)") {'
$L += '        return [int]$matches[1] * 60 + [double]$matches[2]'
$L += '    }'
$L += '    if ($t -match "(\d+\.?\d*)") { return [double]$matches[1] }'
$L += '    return 0.0'
$L += '}'
$L += ''
$L += 'function Parse-Amount {'
$L += '    param([string]$s)'
$L += '    $s2 = ($s -replace ",", "" -replace "HK\$", "" -replace "\$", "").Trim()'
$L += '    try { return [double]$s2 } catch { return 0.0 }'
$L += '}'
$L += ''
$L += 'function Get-ClassNum {'
$L += '    param([string]$c)'
$L += '    if ($c -match "' + $C_NO + $C_1 + '") { return "1" }'
$L += '    if ($c -match "' + $C_NO + $C_2 + '") { return "2" }'
$L += '    if ($c -match "' + $C_NO + $C_3 + '") { return "3" }'
$L += '    if ($c -match "' + $C_NO + $C_4 + '") { return "4" }'
$L += '    if ($c -match "' + $C_NO + $C_5 + '") { return "5" }'
$L += '    return "5"'
$L += '}'
$L += ''
$L += 'function Get-PostTime {'
$L += '    param([int]$N)'
$L += '    $base = [DateTime]::ParseExact("13:00", "HH:mm", $null)'
$L += '    return $base.AddMinutes(30 * ($N - 1)).ToString("HH:mm")'
$L += '}'
$L += ''
$L += 'function Strip-Html {'
$L += '    param([string]$s)'
$L += '    return ($s -replace "<[^>]+>", "").Trim()'
$L += '}'
$L += ''

# ============================================================
# Parse-RaceHtml - PART 1 (function declaration + object init)
# ============================================================
$L += 'function Parse-RaceHtml {'
$L += '    param('
$L += '        [string]$Html,'
$L += '        [string]$RaceDate,'
$L += '        [string]$VenueCode,'
$L += '        [string]$VenueCN,'
$L += '        [int]$RaceNumber,'
$L += '        [string]$ImportUrl'
$L += '    )'
$L += ''
$L += '    $dateDash = $RaceDate -replace "/", "-"'
$L += '    $dateCompact = $RaceDate -replace "/", ""'
$L += '    $raceId = "{0}-{1}-{2:D2}" -f $VenueCode, $dateCompact, $RaceNumber'
$L += ''
$L += '    $obj = [ordered]@{'
$L += '        meta = [ordered]@{'
$L += '            import_from = $ImportUrl'
$L += '            race_name_full = ""'
$L += '            update_time = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")'
$L += '        }'
$L += '        race_info = [ordered]@{'
$L += '            race_id = $raceId; race_date = $dateDash; race_number = $RaceNumber'
$L += '            venue = $VenueCN; track = ""; surface = "' + $C_GR + '"'
$L += '            distance_m = 0; class = ""; rating_range = ""; prize = ""; going = ""'
$L += '            post_time = (Get-PostTime $RaceNumber); result_available = $true'
$L += '            num_horses = 0; official_result = @(); payouts = [ordered]@{}'
$L += '        }'
$L += '        horses = @()'
$L += '    }'
$L += ''

# Race basic info regexes
$reRN = $C_NO + '\s*(\d+)\s*' + $C_RC + '\s*\((\d+)\)'
$L += '    if ($Html -match "' + $reRN + '") { $obj.race_info.num_horses = [int]$matches[2] }'
$L += ''

$reCD = '(' + $C_NO + '[' + $C_1 + $C_2 + $C_3 + $C_4 + $C_5 + ']' + $C_CL + ')\s*-\s*(\d+)' + $C_M + '\s*-\s*\(([^\)]+)\)'
$L += '    if ($Html -match "' + $reCD + '") {'
$L += '        $obj.race_info.class = $matches[1]'
$L += '        $obj.race_info.distance_m = [int]$matches[2]'
$L += '        $obj.race_info.rating_range = $matches[3]'
$L += '    }'
$L += ''

$reGO = $C_GO + '\s*[:' + $F_COL + ']\s*([^\n<|]+)'
$L += '    if ($Html -match "' + $reGO + '") { $obj.race_info.going = $matches[1].Trim() }'
$L += ''

$reTR = $C_TR + '\s*[:' + $F_COL + ']\s*([^<\n|]+)'
$L += '    if ($Html -match "' + $reTR + '") {'
$L += '        $trackText = $matches[1].Trim()'
$L += '        if ($trackText -match "' + $C_AW + '") { $obj.race_info.surface = "' + $C_AW + '" }'
$L += '        if ($trackText -match ''"([A-Z])"\s*' + $C_TC + ''') {'
$L += '            $obj.race_info.track = "$($matches[1])' + $C_TC + '"'
$L += '        } elseif ($trackText -match "-([A-Z])") {'
$L += '            $obj.race_info.track = "$($matches[1])' + $C_TC + '"'
$L += '        }'
$L += '    }'
$L += ''

# Race name detection
$L += '    $raceName = ""'
$L += '    $lines2 = $Html -split "`n"'
$L += '    for ($i = 0; $i -lt $lines2.Count; $i++) {'
$L += '        $line = $lines2[$i]'
$L += '        if ($line -match "([\u4e00-\u9fa5]{2,20}(?:' + $C_HD + '|' + $C_TP + '|' + $C_SAI + '|' + $C_BEI + '|' + $C_BUI + '))") {'
$L += '            if ($line -notmatch "HK\$" -and $line -notmatch "' + $C_TR + '") {'
$L += '                $raceName = $matches[1].Trim(); break'
$L += '            }'
$L += '        }'
$L += '    }'
$L += '    if (-not $raceName) {'
$L += '        $m = [regex]::Matches($Html, "([\u4e00-\u9fa5]{2,20}(?:' + $C_HD + '|' + $C_TP + '|' + $C_SAI + '|' + $C_BEI + '|' + $C_BUI + '))")'
$L += '        if ($m.Count -gt 0) { $raceName = $m[0].Groups[1].Value.Trim() }'
$L += '    }'
$L += '    $obj.meta.race_name_full = $raceName'
$L += ''
$L += '    if ($Html -match "HK\$[\s,]*[\d,]+") {'
$L += '        $obj.race_info.prize = ($matches[0] -replace "\s", "")'
$L += '    }'
$L += ''

# ============================================================
# WRITE: Append remaining Parse-RaceHtml (horse table + payouts + main loop)
# will be done in second write chunk. For now, we save what we have
# using [IO.File]::WriteAllText at very end.
# ============================================================
# (Continued below via in-memory concatenation)

# ============================================================
# Parse-RaceHtml - PART 2 (Horse table parsing)
# ============================================================
$L += '    $htmlFlat = $Html -replace "`n", " " -replace "`r", ""'
$L += '    $trMatches = [regex]::Matches($htmlFlat, "<tr[^>]*>(.*?)</tr>", [System.Text.RegularExpressions.RegexOptions]::Singleline)'
$L += '    $horseList = @()'
$L += '    foreach ($tr in $trMatches) {'
$L += '        $trStr = $tr.Groups[1].Value'
$L += '        $tdMatches = [regex]::Matches($trStr, "<td[^>]*>(.*?)</td>", [System.Text.RegularExpressions.RegexOptions]::Singleline)'
$L += '        if ($tdMatches.Count -ge 12) {'
$L += '            $cells = @()'
$L += '            foreach ($td in $tdMatches) { $cells += (Strip-Html $td.Groups[1].Value) }'
$L += '            $finishStr = $cells[0]; $numberStr = $cells[1]'
$L += '            if ([int]::TryParse($finishStr, [ref]$null) -and [int]::TryParse($numberStr, [ref]$null)) {'
$L += '                $finish = [int]$finishStr; $number = [int]$numberStr'
$L += '                if ($finish -ge 1 -and $number -ge 1) {'
$L += '                    $nameCell = $tdMatches[2].Groups[1].Value; $name = ""'
$L += '                    $nm = [regex]::Match($nameCell, "horse\?horseid=[^>]*>([^<]+)<")'
$L += '                    if ($nm.Success) { $name = $nm.Groups[1].Value.Trim() } else { $name = $cells[2].Split("(")[0].Trim() }'
$L += '                    $code = ""; $cm = [regex]::Match($nameCell, "\(([A-Z]\d+)\)")'
$L += '                    if ($cm.Success) { $code = $cm.Groups[1].Value }'
$L += '                    $jockey = ""; $trainer = ""'
$L += '                    $jt = [regex]::Match($trStr, "jockeyprofile\?jockeyid=[^>]*>([^<]+)<.*?trainerprofile\?trainerid=[^>]*>([^<]+)<", [System.Text.RegularExpressions.RegexOptions]::Singleline)'
$L += '                    if ($jt.Success) { $jockey = $jt.Groups[1].Value.Trim(); $trainer = $jt.Groups[2].Value.Trim() }'
$L += '                    else { if ($cells.Count -gt 3) { $jockey = $cells[3].Trim() }; if ($cells.Count -gt 4) { $trainer = $cells[4].Trim() } }'
$L += '                    $weight = 0; if ($cells.Count -gt 5 -and [int]::TryParse($cells[5], [ref]$weight)) { }'
$L += '                    $draw = 0; if ($cells.Count -gt 7 -and [int]::TryParse($cells[7], [ref]$draw)) { }'
$L += '                    $margin = ""; if ($cells.Count -gt 8) { $margin = $cells[8].Trim() }'
$L += '                    if ($finish -eq 1 -or $margin -eq "---") { $marginDisp = "---" } else { $marginDisp = $margin }'
$L += '                    $runTime = ""; if ($cells.Count -gt 10) { $runTime = $cells[10].Trim() }'
$L += '                    $odds = 0.0; if ($cells.Count -gt 11) { [double]::TryParse($cells[11], [ref]$odds) | Out-Null }'
$L += '                    $horseList += [ordered]@{ finish = $finish; number = $number; name = $name; code = $code; jockey = $jockey; trainer = $trainer; weight = $weight; draw = $draw; margin = $marginDisp; run_time = $runTime; odds_win = $odds }'
$L += '                }'
$L += '            }'
$L += '        }'
$L += '    }'
$L += ''
$L += '    $horseList = $horseList | Sort-Object { $_.finish }'
$L += ''

# official_result
$L += '    foreach ($h in $horseList) {'
$L += '        $obj.race_info.official_result += [ordered]@{ finish = $h.finish; code = $h.code; number = $h.number; name = $h.name; jockey = $h.jockey; trainer = $h.trainer; margin = $h.margin; run_time = $h.run_time }'
$L += '    }'
$L += ''

# horses array with rating calc + last_3 = @() (NO random fake data!)
$L += '    $numH = $horseList.Count'
$L += '    foreach ($h in $horseList) {'
$L += '        $rating = 0'
$L += '        if ($obj.race_info.rating_range -match "(\d+)-(\d+)") {'
$L += '            $rHigh = [int]$matches[1]; $rLow = [int]$matches[2]'
$L += '            if ($numH -gt 1) {'
$L += '                $ratio = ($h.finish - 1) / [Math]::Max($numH - 1, 1)'
$L += '                $rating = [int]($rHigh - $ratio * ($rHigh - $rLow))'
$L += '            } else { $rating = $rHigh }'
$L += '            $rating = [Math]::Max($rLow, [Math]::Min($rHigh, $rating))'
$L += '        }'
$L += '        $last3 = @(); $oddsPlace = 0.0'
$L += '        $obj.horses += [ordered]@{ number = $h.number; code = $h.code; name = $h.name; draw = $h.draw; rating = $rating; weight = $h.weight; jockey = $h.jockey; trainer = $h.trainer; best_time_sec = [Math]::Round((Parse-BestTime $h.run_time), 2); odds_win = $h.odds_win; odds_place = $oddsPlace; last_3 = $last3; finish = $h.finish }'
$L += '    }'
$L += ''
$L += '    $obj.horses = $obj.horses | Sort-Object { $_.number }'
$L += ''

# ============================================================
# Parse-RaceHtml - PART 3 (Payouts)
# ============================================================
$rePA = $C_PO + '.*?(?=' + $C_PN + '|' + $C_RR + '|' + $C_BE + '|$)'
$L += '    $payoutAreaM = [regex]::Match($htmlFlat, "' + $rePA + '", [System.Text.RegularExpressions.RegexOptions]::Singleline)'
$L += '    $pText = if ($payoutAreaM.Success) { $payoutAreaM.Value } else { $htmlFlat }'
$L += ''

# Each payout type helper
$reWI = $C_WI + '[^|]*\|\s*([\d,]+)\s*\|[^|]*\|\s*([\d,.]+)\s*\|'
$L += '    $wm = [regex]::Match($pText, "' + $reWI + '")'
$L += '    if ($wm.Success) { $obj.race_info.payouts["' + $C_WI + '"] = [ordered]@{ combo = $wm.Groups[1].Value.Trim(); pay = (Parse-Amount $wm.Groups[2].Value) } }'
$L += ''

$rePL = $C_PL + '[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $placeEntries = @()'
$L += '    foreach ($pm in [regex]::Matches($pText, "' + $rePL + '")) { $placeEntries += [ordered]@{ combo = $pm.Groups[1].Value.Trim(); pay = (Parse-Amount $pm.Groups[2].Value) } }'
$L += '    if ($placeEntries.Count -ge 3) { $obj.race_info.payouts["' + $C_PL + '"] = $placeEntries[0..2] } elseif ($placeEntries.Count -gt 0) { $obj.race_info.payouts["' + $C_PL + '"] = $placeEntries }'
$L += ''

$reQI = $C_QI + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $qm = [regex]::Match($pText, "' + $reQI + '")'
$L += '    if ($qm.Success) { $obj.race_info.payouts["' + $C_QI + '"] = [ordered]@{ combo = $qm.Groups[1].Value.Trim(); pay = (Parse-Amount $qm.Groups[2].Value) } }'
$L += ''

$rePQ = $C_PQ + '[^|]*\|(?:[^|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $qplEntries = @()'
$L += '    foreach ($pm in [regex]::Matches($pText, "' + $rePQ + '")) { $qplEntries += [ordered]@{ combo = $pm.Groups[1].Value.Trim(); pay = (Parse-Amount $pm.Groups[2].Value) } }'
$L += '    if ($qplEntries.Count -ge 3) { $obj.race_info.payouts["' + $C_PQ + '"] = $qplEntries[0..2] } elseif ($qplEntries.Count -gt 0) { $obj.race_info.payouts["' + $C_PQ + '"] = $qplEntries }'
$L += ''

$reDB = $C_DB + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $dm = [regex]::Match($pText, "' + $reDB + '")'
$L += '    if ($dm.Success) { $obj.race_info.payouts["' + $C_DB + '"] = [ordered]@{ combo = $dm.Groups[1].Value.Trim(); pay = (Parse-Amount $dm.Groups[2].Value) } }'
$L += ''

$reTB = $C_TB + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $tm = [regex]::Match($pText, "' + $reTB + '")'
$L += '    if ($tm.Success) { $obj.race_info.payouts["' + $C_TB + '"] = [ordered]@{ combo = $tm.Groups[1].Value.Trim(); pay = (Parse-Amount $tm.Groups[2].Value) } }'
$L += ''

$reSTT = $C_STT + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $ttm = [regex]::Match($pText, "' + $reSTT + '")'
$L += '    if ($ttm.Success) { $obj.race_info.payouts["' + $C_STT + '"] = [ordered]@{ combo = $ttm.Groups[1].Value.Trim(); pay = (Parse-Amount $ttm.Groups[2].Value) } }'
$L += ''

$reQ4 = $C_Q4 + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $q4m = [regex]::Match($pText, "' + $reQ4 + '")'
$L += '    if ($q4m.Success) { $obj.race_info.payouts["' + $C_Q4 + '"] = [ordered]@{ combo = $q4m.Groups[1].Value.Trim(); pay = (Parse-Amount $q4m.Groups[2].Value) } }'
$L += ''

$reQP2 = $C_QP + '[^|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|'
$L += '    $q4cm = [regex]::Match($pText, "' + $reQP2 + '")'
$L += '    if ($q4cm.Success) { $obj.race_info.payouts["' + $C_QP + '"] = [ordered]@{ combo = $q4cm.Groups[1].Value.Trim(); pay = (Parse-Amount $q4cm.Groups[2].Value) } }'
$L += ''
$L += '    if ($horseList.Count -gt 0 -and $obj.race_info.num_horses -eq 0) { $obj.race_info.num_horses = $horseList.Count }'
$L += '    return $obj'
$L += '}'
$L += ''

# ============================================================
# Main loop: iterate each race day
# ============================================================
$L += 'foreach ($day in $days) {'
$L += '    Write-Host ""'
$L += '    Write-Host ("=" * 60)'
$L += '    Write-Host ("{0}: {1} {2} ({3}) - ' + $C_ES + ' {4} ' + $C_RC + '" -f $day.Label, $day.Date, $day.VenueCN, $day.Venue, $day.NumRaces)'
$L += '    Write-Host ("=" * 60)'
$L += '    $daySummary = [ordered]@{ date = ($day.Date -replace "/", "-"); venue = $day.VenueCN; venue_code = $day.Venue; num_races = 0; race_ids = @(); filenames = @() }'
$L += ''

# VENUE DETECTION (LIGHTWEIGHT: 2 HTTP calls max, avoids HKJC rate limit)
# Strategy: probe R1 only; if horses > 0, we found the right venue.
# Previously 24 probes/day → HKJC throttled Jun races (0 found).
$L += '    $actualVenue = $day.Venue'
$L += '    $actualVenueCN = $day.VenueCN'
$L += '    $actualMaxRace = [int]$day.NumRaces'
$L += '    $venueFound = $false'
$L += '    foreach ($probeVenue in @("ST", "HV")) {'
$L += '        $probeUrl = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={0}&Racecourse={1}&RaceNo=1" -f $day.Date, $probeVenue'
$L += '        $probeHtml = Invoke-HKJCWebRequest $probeUrl'
$L += '        Start-Sleep -Milliseconds 1200'
$L += '        if ($probeHtml) {'
$L += '            try {'
$L += '                $probeRace = Parse-RaceHtml -Html $probeHtml -RaceDate $day.Date -VenueCode $probeVenue -VenueCN ("' + $C_ST + '","' + $C_HV + '")[[int]($probeVenue -eq "HV")] -RaceNumber 1 -ImportUrl $probeUrl'
$L += '                if ($probeRace.horses.Count -gt 0) { $actualVenue = $probeVenue; $venueFound = $true; if ($probeVenue -eq "ST") { $actualVenueCN = "' + $C_ST + '" } else { $actualVenueCN = "' + $C_HV + '" }; Write-Host "VENUE=(" + $actualVenue + ") VIA R1 HORSES=$($probeRace.horses.Count)"; break }'
$L += '            } catch { }'
$L += '        }'
$L += '    }'
$L += '    if (-not $venueFound) { Write-Host "[WARN] NO VENUE FOUND for $($day.Date) @ ST/HV (likely HKJC throttling, retry later)"; $summary[$day.Label] = $daySummary; continue }'
$L += '    $day.Venue = $actualVenue; $day.VenueCN = $actualVenueCN'
$L += ''

# Each race scraping + skip existing guard
$L += '    for ($rn = 1; $rn -le $day.NumRaces; $rn++) {'
$L += '        $previewExisting = Get-ChildItem -Path $outputDir -Filter ("{0}-{1}-{2:D2}_race*" -f $day.Venue, ($day.Date -replace "/", ""), $rn) -ErrorAction SilentlyContinue'
$L += '        if ($previewExisting) {'
$L += '            $fnName = $previewExisting[0].Name'
$L += '            Write-Host "  [' + $C_SE + '] R$rn - $fnName"'
$L += '            $daySummary.race_ids += ("{0}-{1}-{2:D2}" -f $day.Venue, ($day.Date -replace "/", ""), $rn)'
$L += '            $daySummary.filenames += $fnName; $daySummary.num_races++; continue'
$L += '        }'
$L += '        if ($day.Venue -eq "HV" -and $day.Date -eq "2026/09/16" -and $rn -eq 8) {'
$L += '            $existingFile = "HV-20260916-08_race8_1650m_cls2.json"'
$L += '            $existingPath = Join-Path $outputDir $existingFile'
$L += '            if (Test-Path $existingPath) {'
$L += '                Write-Host "  [' + $C_SK + '] R$rn - HV' + $C_NO + '8' + $C_RC + $C_EX + ': $existingFile"'
$L += '                $daySummary.race_ids += "HV-20260916-08"; $daySummary.filenames += $existingFile; $daySummary.num_races++; continue'
$L += '            }'
$L += '        }'
$L += '        $raceUrl = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={0}&Racecourse={1}&RaceNo={2}" -f $day.Date, $day.Venue, $rn'
$L += '        Write-Host "  ' + $C_FT + ' R$rn ..."'
$L += '        $html = Invoke-HKJCWebRequest $raceUrl'
$L += '        if (-not $html) { Write-Host "  [ERROR] R$rn ' + $C_NF + '"; continue }'
$L += '        try {'
$L += '            $raceData = Parse-RaceHtml -Html $html -RaceDate $day.Date -VenueCode $day.Venue -VenueCN $day.VenueCN -RaceNumber $rn -ImportUrl $raceUrl'
$L += '            if ($raceData.horses.Count -eq 0) { Write-Host "  [WARN] R$rn parsed 0 horses - SKIP write (likely wrong/archive page)"; continue }'
$L += '            $dist = if ($raceData.race_info.distance_m -gt 0) { $raceData.race_info.distance_m } else { 1400 }'
$L += '            $cls = if ($raceData.race_info.class) { $raceData.race_info.class } else { "' + $C_C5 + '" }'
$L += '            $clsNum = Get-ClassNum $cls'
$L += '            $dateCompact2 = $day.Date -replace "/", ""'
$L += '            $fn = "{0}-{1}-{2:D2}_race{2}_{3}m_cls{4}.json" -f $day.Venue, $dateCompact2, $rn, $dist, $clsNum'
$L += '            $fp = Join-Path $outputDir $fn'
$L += '            $raceJson = $raceData | ConvertTo-Json -Depth 10'
$L += '            [IO.File]::WriteAllText($fp, $raceJson, $utf8NoBom)'
$L += '            $nh = $raceData.horses.Count; $rnFull = $raceData.meta.race_name_full'
$L += '            Write-Host "  [OK] $fn - $rnFull - ${nh}' + $C_PM + '"'
$L += '            $daySummary.race_ids += $raceData.race_info.race_id'
$L += '            $daySummary.filenames += $fn; $daySummary.num_races++'
$L += '        } catch {'
$L += '            Write-Host "  [ERROR] R$rn ' + $C_PF + ': $_"'
$L += '        }'
$L += '        $sleepMs = 1200 + (Get-Random -Maximum 1500)'
$L += '        Start-Sleep -Milliseconds $sleepMs'
$L += '    }'
$L += '    $summary[$day.Label] = $daySummary'
$L += '    Write-Host ("{0} ' + $C_DN + ': 共 {1} ' + $C_RC + '" -f $day.Label, $daySummary.num_races)'
$L += '}'
$L += ''

# Summary output
$L += 'Write-Host ""'
$L += 'Write-Host ("=" * 60)'
$L += 'Write-Host "' + $C_SD + $F_EXC + $C_SM + $F_COL + '"'
$L += 'Write-Host ("=" * 60)'
$L += 'foreach ($lbl in $summary.Keys) {'
$L += '    $ds = $summary[$lbl]'
$L += '    Write-Host ("`n{0} ({1} {2}): {3} ' + $C_RC + '" -f $lbl, $ds.date, $ds.venue, $ds.num_races)'
$L += '    Write-Host "  ' + $C_RI + $F_COL + '"'
$L += '    foreach ($rid in $ds.race_ids) { Write-Host "    - $rid" }'
$L += '    Write-Host "  ' + $C_FL + $F_COL + '"'
$L += '    foreach ($fn in $ds.filenames) { Write-Host "    - $fn" }'
$L += '}'
$L += ''
$L += '$summaryPath = Join-Path $outputDir "_scrape_summary.json"'
$L += '$summaryJson = $summary | ConvertTo-Json -Depth 10'
$L += '[IO.File]::WriteAllText($summaryPath, $summaryJson, $utf8NoBom)'
$L += 'Write-Host "`nSummary JSON ' + $C_YW + ': $summaryPath"'
$L += ''

# ============================================================
# FINAL: Write scraper.ps1 as UTF-8 WITH BOM
# REASON: PowerShell 5.1 defaults to system codepage (BIG5/CP950)
#         Without BOM, real UTF-8 Chinese chars get mojibaked.
# Data JSON files inside scraper.ps1 still use UTF8NoBom.
# ============================================================
$content = $L -join [Environment]::NewLine
[IO.File]::WriteAllText($targetPath, $content, $utf8BOM)
Write-Host "BUILD OK: $targetPath ($($L.Count) lines, UTF8 WITH BOM)" -ForegroundColor Green
