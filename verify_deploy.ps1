$base = "http://localhost:9000"
$u = $base
$utf8 = [Text.UTF8Encoding]::new($false)
Write-Host "=== Local static file verification (port 9000) ==="
""

$files = @(
    @("index",           "/",                      "text/html",                  8000),
    @("manifest",        "/manifest.webmanifest",  "application/manifest+json",  2000),
    @("sw.js",           "/sw.js",                 "application/javascript",     2000),
    @("app.js",          "/app.js",                "application/javascript",     30000),
    @("style.css",       "/style.css",             "text/css",                   1000),
    @("icon-192",        "/data/icons/icon-192.png","image/png",                 4000),
    @("icon-512",        "/data/icons/icon-512.png","image/png",                 12000),
    @("api/list",        "/api/list.json",         "application/json",           4000),
    @("api/refresh",     "/api/refresh_static.json","application/json",          100),
    @("history #1",      "/api/history/HV-20260610-01_race1_1800m_cls5.json","application/json", 50000),
    @("history CURRENT", "/api/history/HV-20260923-09_race9_1800m_cls3_CURRENT.json","application/json", 5000),
    @("jockeys_db",      "/api/stats/jockeys_db.json","application/json",       20000),
    @("trainers_db",     "/api/stats/trainers_db.json","application/json",      10000),
    @("horses_db",       "/api/profiles/horses_db.json","application/json",    150000)
)

$allOk = $true
foreach ($f in $files) {
    $name, $path, $expectedType, $minSize = $f[0], $f[1], $f[2], $f[3]
    try {
        $resp = Invoke-WebRequest ($u + $path) -UseBasicParsing -TimeoutSec 15
        $code = [int]$resp.StatusCode
        $ctype = $resp.Headers["Content-Type"]
        if ($ctype -is [Array]) { $ctype = $ctype[0] }
        $size = [int]$resp.RawContentLength
        $sizeMatch = $size -ge $minSize
        $ctypeMatch = ($ctype -like "$expectedType*")
        $ok = ($code -eq 200) -and $sizeMatch -and $ctypeMatch
        if (-not $ok) { $allOk = $false }
        $mark = if ($ok) { "[OK ]" } else { "[FAIL]" }
        Write-Host ("{0} code={1,-3} size={2,-8} type={3,-40} → {4}" -f $mark, $code, $size, $ctype, $name)
    } catch {
        $allOk = $false
        Write-Host ("[FAIL] exception: " + $_.Exception.Message + " → " + $name)
    }
}

""
Write-Host ("APP.RACE_FILES count: verify via app.js...")
try {
    $appJs = [IO.File]::ReadAllText("D:\Trae\horse\public\app.js", $utf8)
    $m = [regex]::Match($appJs, "(?s)const\s+RACE_FILES\s*=\s*\[(.*?)\]\s*;")
    $cnt = 0
    if ($m.Success) { $cnt = ([regex]::Matches($m.Groups[1].Value, "'[^']+'")).Count }
    Write-Host ("  app.js RACE_FILES count = " + $cnt + " (should be 134)")
    if ($cnt -lt 130) { $allOk = $false; Write-Host "  ❌ RACE_FILES too few!" }
} catch {
    Write-Host ("  FAIL app.js read: " + $_.Exception.Message); $allOk = $false
}

Write-Host ""
if ($allOk) {
    Write-Host "✅  ALL CHECKS PASSED → Ready for Vercel deploy!"
    exit 0
} else {
    Write-Host "❌  SOME CHECKS FAILED → Please fix before deploy"
    exit 1
}
