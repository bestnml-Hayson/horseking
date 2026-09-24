$headers = @{
    "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    "Accept" = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    "Accept-Language" = "zh-HK,zh;q=0.9,en;q=0.8"
    "Referer" = "https://bet.hkjc.com/ch/racing/"
}
Write-Host "=== bet.hkjc.com HV-R1 HTML (full 4830 bytes) ==="
$u = "https://bet.hkjc.com/ch/racing/wp/2026-09-23/HV/1"
$r = Invoke-WebRequest -Uri $u -Headers $headers -TimeoutSec 30 -UseBasicParsing
$r.Content
Write-Host ""
Write-Host "=== Try racing.hkjc.com OLD odds page (R1) ==="
$u2 = "https://racing.hkjc.com/racing/information/Chinese/Racing/RaceCard.aspx?RaceDate=2026/09/23&Racecourse=HV&RaceNo=1"
try {
    $r2 = Invoke-WebRequest -Uri $u2 -Headers $headers -TimeoutSec 30 -UseBasicParsing
    Write-Host ("Status=" + $r2.StatusCode + " Len=" + $r2.RawContentLength)
    # Save for parse
    [System.IO.File]::WriteAllText("D:\Trae\horse\data\references\_debug_hkjc_wp_r1.html", $r2.Content, [System.Text.Encoding]::UTF8)
    if ($r2.Content -match "odds|winOdds|WIN.*ODDS|獨贏|現金") {
        Write-Host "✅ racing.hkjc.com odds FOUND!"
        $scripts = [regex]::Matches($r2.Content, "<script[^>]*>(.*?)</script>", [System.Text.RegularExpressions.RegexOptions]::Singleline)
        $fi = 0
        foreach ($s in $scripts) {
            $txt = $s.Groups[1].Value
            if ($txt.Length -gt 50 -and ($txt -match "odds|winOdds|獨贏|JSON")) {
                Write-Host ("--- script #" + $fi + " len=" + $txt.Length + " ---")
                if ($txt.Length -lt 3000) { Write-Host $txt } else { Write-Host $txt.Substring(0, 3000) }
                $fi++
                if ($fi -ge 3) { break }
            }
        }
        $idx = $r2.Content.IndexOf("odds")
        if ($idx -lt 0) { $idx = $r2.Content.IndexOf("獨贏") }
        if ($idx -lt 0) { $idx = $r2.Content.IndexOf("WIN ODDS") }
        if ($idx -gt 0) {
            $st = [Math]::Max(0, $idx - 100)
            $ed = [Math]::Min($r2.Content.Length - 1, $idx + 4000)
            Write-Host "--- odds context range ---"
            Write-Host $r2.Content.Substring($st, $ed - $st)
        }
    } else {
        Write-Host "ℹ️ No odds text visible. Save file to _debug_hkjc_wp_r1.html"
    }
} catch { Write-Host ("racing.hkjc.com EX: " + $_.Exception.Message) }

Write-Host ""
Write-Host "=== Try HKJC official JSON odds API (classic endpoint) ==="
try {
    $api = "https://bet.hkjc.com/racing/pages/odds_wp.aspx?date=23-09-2026&venue=HV&raceno=1&lang=zh-HK"
    $r3 = Invoke-WebRequest -Uri $api -Headers $headers -TimeoutSec 30 -UseBasicParsing
    Write-Host ("odds_wp.aspx Status=" + $r3.StatusCode + " Len=" + $r3.RawContentLength)
    [System.IO.File]::WriteAllText("D:\Trae\horse\data\references\_debug_odds_wp_r1.html", $r3.Content, [System.Text.Encoding]::UTF8)
} catch { Write-Host ("odds_wp EX: " + $_.Exception.Message) }
