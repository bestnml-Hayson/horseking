# Parse _debug_hkjc_wp_r1.html (racing.hkjc.com R1) and extract odds_win / odds_place
$html = [System.IO.File]::ReadAllText("D:\Trae\horse\data\references\_debug_hkjc_wp_r1.html", [System.Text.Encoding]::UTF8)
Write-Host ("File size: " + $html.Length)

# Strategy 1: Find odds table rows with horse number + win odds + place odds
# Pattern: rows with 馬號 (horse number) column + 獨贏 (win odds) column + 位置 (place odds) column
Write-Host ""
Write-Host "=== Strategy 1: Find all td with odds-like numbers near horse numbers ==="

# Remove newlines first for easier regex
$htmlFlat = $html -replace "`r", "" -replace "`n", " "

# Extract all <tr> blocks, look for patterns with horseNo + odds numbers
$trMatches = [regex]::Matches($htmlFlat, "<tr[^>]*>(.*?)</tr>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
$foundHorseRows = 0
foreach ($tr in $trMatches) {
    $trStr = $tr.Groups[1].Value
    # Look for digit patterns: a) horse number (1-N) as digit, b) win odds like 8.5 or 28, c) place odds
    $tdMatches = [regex]::Matches($trStr, "<td[^>]*>(.*?)</td>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($tdMatches.Count -ge 8) {
        $cells = @()
        foreach ($td in $tdMatches) {
            $cells += ($td.Groups[1].Value -replace "<[^>]+>", "").Trim()
        }
        # Now look for cells that look like odds: [digit].[digit] or pure digit
        $oddsCellCount = 0
        $firstOddsIdx = -1
        $hasHorseNameOrCode = $false
        for ($i = 0; $i -lt $cells.Count; $i++) {
            $c = $cells[$i]
            if ($c -match "^[A-Z]\d+$" -and $c.Length -le 5) { $hasHorseNameOrCode = $true }
            if ($c -match "^\d{1,3}(\.\d)?$") {
                $n = [double]$c
                if (($n -ge 1.0 -and $n -le 200.0) -and ($n -ne [Math]::Floor($n) -or [Math]::Floor($n) -le 99)) {
                    $oddsCellCount++
                    if ($firstOddsIdx -lt 0) { $firstOddsIdx = $i }
                }
            }
        }
        if ($oddsCellCount -ge 2) {
            Write-Host ("  Found candidate row (oddsCells=" + $oddsCellCount + ", firstOddsIdx=" + $firstOddsIdx + ", horseCode?=" + $hasHorseNameOrCode + "):")
            for ($i = 0; $i -lt $cells.Count; $i++) {
                Write-Host ("    [" + $i + "] len=" + $cells[$i].Length + " : " + $cells[$i].Substring(0, [Math]::Min(60, $cells[$i].Length)))
            }
            $foundHorseRows++
            Write-Host ""
            if ($foundHorseRows -ge 16) { break }
        }
    }
}

Write-Host ""
Write-Host "=== Strategy 2: Search for win_odds / place_odds JSON keys / explicit odds data in scripts ==="
$scriptMatches = [regex]::Matches($html, "<script[^>]*>(.*?)</script>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
foreach ($sm in $scriptMatches) {
    $s = $sm.Groups[1].Value
    if ($s.Length -lt 500) { continue }
    if ($s -match "odds|winOdds|placeOdds|WIN_ODDS|place_odds|win_odds") {
        Write-Host ("Script block len=" + $s.Length + " contains odds keywords. Extracting odds-containing region:")
        $idx = 0
        $found = 0
        while ($true) {
            $i = $s.IndexOf("odds", $idx, [System.StringComparison]::OrdinalIgnoreCase)
            if ($i -lt 0) { break }
            $st = [Math]::Max(0, $i - 200)
            $ed = [Math]::Min($s.Length - 1, $i + 800)
            Write-Host ("  Region @" + $i + ": " + $s.Substring($st, $ed - $st))
            Write-Host ""
            $idx = $i + 400
            $found++
            if ($found -ge 6) { break }
        }
    }
}

Write-Host ""
Write-Host "=== Strategy 3: Explicitly look for '賠率' or 'odds' HTML table caption with 獨贏/位置 ==="
if ($htmlFlat -match "獨贏.*位置|WIN\s*ODDS.*PLACE|賠率.*獨贏") {
    Write-Host "✅ Found win/place combined odds table header!"
    $i = $htmlFlat.IndexOf("獨贏")
    if ($i -lt 0) { $i = $htmlFlat.IndexOf("WIN ODDS") }
    if ($i -gt 0) {
        $st = [Math]::Max(0, $i - 500)
        $ed = [Math]::Min($htmlFlat.Length - 1, $i + 6000)
        Write-Host $htmlFlat.Substring($st, $ed - $st)
    }
}
